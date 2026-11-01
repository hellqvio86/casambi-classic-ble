"""Tests demonstrating deterministic Classic protocol acceptance and Evolution rejection.

Verifies protocol version boundaries, rejection timing before authentication or command
writes, service UUID validation in CasambiDevice, and secret sanitization in error reporting.
"""

import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakClient

from casambi_classic_ble import Casambi, CasambiDevice
from casambi_classic_ble._client import CasambiClientClassic
from casambi_classic_ble._constants import (
    CLASSIC_AUTH_LEVEL_MANAGER,
    CLASSIC_AUTH_LEVEL_VISITOR,
    FIRST_UNSUPPORTED_PROTOCOL_VERSION,
    MAX_SUPPORTED_CLASSIC_VERSION,
    MIN_SUPPORTED_CLASSIC_VERSION,
    ConnectionState,
    isClassicNetwork,
    isConformantClassicNetwork,
)
from casambi_classic_ble._keystore import KeyStore
from casambi_classic_ble._network import Network
from casambi_classic_ble.constants import CasambiUUIDs
from casambi_classic_ble.exceptions import (
    CasambiDeviceError,
    UnsupportedProtocolVersion,
)


def _make_mock_network(*, version: int = 5) -> MagicMock:
    mock_net = MagicMock(spec=Network)
    mock_net.protocol_version = version
    mock_net.protocolVersion = version
    mock_keystore = MagicMock(spec=KeyStore)
    mock_key = MagicMock()
    mock_key.key = b"\x01" * 16
    mock_keystore.get_legacy_key.side_effect = lambda role: (
        mock_key if role in (CLASSIC_AUTH_LEVEL_VISITOR, CLASSIC_AUTH_LEVEL_MANAGER) else None
    )
    mock_keystore.getLegacyKey.side_effect = lambda level: (
        mock_key if level in (CLASSIC_AUTH_LEVEL_VISITOR, CLASSIC_AUTH_LEVEL_MANAGER) else None
    )
    mock_net.keystore = mock_keystore
    mock_net.keyStore = mock_keystore
    return mock_net


class TestProtocolVersionBoundaries:
    """Tests for protocol version boundaries and Classic-only invariants."""

    def test_constants_boundaries(self):
        assert MIN_SUPPORTED_CLASSIC_VERSION == 5
        assert MAX_SUPPORTED_CLASSIC_VERSION == 9
        assert FIRST_UNSUPPORTED_PROTOCOL_VERSION == 10

    @pytest.mark.parametrize(
        "version,expected_classic,expected_conformant",
        [
            (-1, True, False),
            (0, True, False),
            (1, True, False),
            (4, True, False),
            (5, True, True),  # MIN_SUPPORTED_CLASSIC_VERSION
            (6, True, True),
            (7, True, True),
            (8, True, True),
            (9, True, True),  # MAX_SUPPORTED_CLASSIC_VERSION
            (10, False, False),  # FIRST_UNSUPPORTED_PROTOCOL_VERSION (Evolution)
            (11, False, False),
            (20, False, False),
        ],
    )
    def test_version_helpers(self, version: int, expected_classic: bool, expected_conformant: bool):
        assert isClassicNetwork(version=version) is expected_classic
        assert isConformantClassicNetwork(version=version) is expected_conformant

    @pytest.mark.parametrize("version", [5, 6, 7, 8, 9])
    def test_classic_conformant_versions_accepted_by_client(self, version: int):
        mock_net = _make_mock_network(version=version)

        # Should initialize without raising UnsupportedProtocolVersion
        client = CasambiClientClassic(
            address_or_device="AA:BB:CC:DD:EE:FF",
            dataCallback=MagicMock(),
            disconnected_callback=MagicMock(),
            network=mock_net,
        )
        assert client.address == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.parametrize("version", [-1, 0, 1, 2, 3, 4])
    def test_ancient_versions_rejected_with_clear_error(self, version: int):
        mock_net = _make_mock_network(version=version)

        with pytest.raises(UnsupportedProtocolVersion, match=r"Network version .* is too old"):
            CasambiClientClassic(
                address_or_device="AA:BB:CC:DD:EE:FF",
                dataCallback=MagicMock(),
                disconnected_callback=MagicMock(),
                network=mock_net,
            )

    @pytest.mark.parametrize("version", [10, 11, 15, 99])
    def test_evolution_versions_rejected_with_clear_error(self, version: int):
        mock_net = _make_mock_network(version=version)

        with pytest.raises(
            UnsupportedProtocolVersion, match=r"strictly for Classic firmware \(versions < 10\)"
        ):
            CasambiClientClassic(
                address_or_device="AA:BB:CC:DD:EE:FF",
                dataCallback=MagicMock(),
                disconnected_callback=MagicMock(),
                network=mock_net,
            )


class TestRejectionTimingBeforeAuthenticationOrCommands:
    """Tests confirming that rejection occurs before authentication or command writes."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evolution_version", [10, 11, 25])
    async def test_casambi_connect_rejects_evolution_before_connecting(
        self, evolution_version: int
    ):
        casa = Casambi()
        mock_net = AsyncMock(spec=Network)
        mock_net.protocolVersion = evolution_version
        mock_net._networkRevision = 1

        with (
            patch("casambi_classic_ble._casambi.Network", return_value=mock_net),
            patch("casambi_classic_ble._casambi.CasambiClientClassic") as mock_client_cls,
        ):
            with pytest.raises(
                UnsupportedProtocolVersion, match="strictly for Classic firmware"
            ) as exc_info:
                await casa.connect(
                    address="aabbccddeeff",
                    password="SuperSecretPassword123!",
                    force_offline=False,
                )

            # Verification: CasambiClientClassic was never even instantiated
            mock_client_cls.assert_not_called()
            # Verification: Password was not exposed in the exception
            assert "SuperSecretPassword123!" not in str(exc_info.value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reported_version", [4, 10, 11])
    async def test_exchange_key_rejects_device_reported_unsupported_version_before_notify(
        self, reported_version: int
    ):
        """If a physical device reports an unsupported version during GATT exchangeKey, reject immediately."""
        mock_net = _make_mock_network(version=5)
        client = CasambiClientClassic(
            address_or_device="AA:BB:CC:DD:EE:FF",
            dataCallback=MagicMock(),
            disconnected_callback=MagicMock(),
            network=mock_net,
        )
        mock_gatt = AsyncMock(spec=BleakClient)
        client._gattClient = mock_gatt
        client._connectionState = ConnectionState.CONNECTED

        connhash = b"\x11\x22\x33\x44\x55\x66\x77\x88"
        # First GATT response with unexpected or Evolution version
        resp = struct.pack(">8sBBBBB", connhash, 1, 2, 128, reported_version, 0)
        mock_gatt.read_gatt_char = AsyncMock(return_value=resp)
        mock_gatt.start_notify = AsyncMock()
        mock_gatt.write_gatt_char = AsyncMock()

        with pytest.raises(UnsupportedProtocolVersion):
            await client.exchange_key()

        # Invariant: Rejection happened before start_notify or any write
        mock_gatt.start_notify.assert_not_called()
        mock_gatt.write_gatt_char.assert_not_called()
        assert client._connectionState != ConnectionState.KEY_EXCHANGED
        assert client._connectionState != ConnectionState.AUTHENTICATED


class TestCasambiDeviceEvolutionServiceRejection:
    """Tests confirming CasambiDevice rejects devices lacking Classic GATT services."""

    @pytest.mark.asyncio
    async def test_device_rejects_evolution_or_unknown_gatt_services(
        self, mock_bleak_client, mock_device
    ):
        # Device has non-Classic services (e.g. standard battery service or Evolution service)
        srv_unknown = MagicMock()
        srv_unknown.uuid = "0000180f-0000-1000-8000-00805f9b34fb"  # Battery service
        mock_bleak_client.services = [srv_unknown]

        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        adv = MagicMock()
        adv.manufacturer_data = {}

        with (
            patch("casambi_classic_ble.device.get_device", new=AsyncMock(return_value=None)),
            patch(
                "casambi_classic_ble.device.establish_connection",
                new=AsyncMock(return_value=mock_bleak_client),
            ),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={mock_device.address: (mock_device, adv)}),
            ),
        ):
            with pytest.raises(
                CasambiDeviceError, match="does not support Casambi Classic services"
            ) as exc_info:
                await device.connect()

            assert "Evolution firmware" in str(exc_info.value)
            assert device.is_connected is False
            # Verify no notifications or writes were initiated
            mock_bleak_client.start_notify.assert_not_called()
            mock_bleak_client.write_gatt_char.assert_not_called()

    @pytest.mark.asyncio
    async def test_device_accepts_classic_v1_fe3d(self, mock_bleak_client, mock_device):
        srv_v1 = MagicMock()
        srv_v1.uuid = CasambiUUIDs.SERVICE_V1
        mock_bleak_client.services = [srv_v1]

        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        adv = MagicMock()
        adv.manufacturer_data = {}

        with (
            patch("casambi_classic_ble.device.get_device", new=AsyncMock(return_value=None)),
            patch(
                "casambi_classic_ble.device.establish_connection",
                new=AsyncMock(return_value=mock_bleak_client),
            ),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={mock_device.address: (mock_device, adv)}),
            ),
        ):
            await device.connect()
            assert device.is_connected is True
            assert device._control_uuid == CasambiUUIDs.CONTROL_V1
            assert device._status_uuid == CasambiUUIDs.STATUS_V1

    @pytest.mark.asyncio
    async def test_device_accepts_classic_v2_fe4d(self, mock_bleak_client, mock_device):
        srv_v2 = MagicMock()
        srv_v2.uuid = CasambiUUIDs.SERVICE_V2
        mock_bleak_client.services = [srv_v2]

        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        adv = MagicMock()
        adv.manufacturer_data = {}

        with (
            patch("casambi_classic_ble.device.get_device", new=AsyncMock(return_value=None)),
            patch(
                "casambi_classic_ble.device.establish_connection",
                new=AsyncMock(return_value=mock_bleak_client),
            ),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={mock_device.address: (mock_device, adv)}),
            ),
        ):
            await device.connect()
            assert device.is_connected is True
            assert device._control_uuid == CasambiUUIDs.CONTROL_V2
            assert device._status_uuid == CasambiUUIDs.STATUS_V2
