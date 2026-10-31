"""Tests for CasambiDevice"""

from unittest.mock import AsyncMock, patch

import pytest

from casambi_classic_ble import CasambiDevice


class TestCasambiDevice:
    def test_device_initialization(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", name="MockDevice")

        assert device.address == "AA:BB:CC:DD:EE:FF"
        assert device.name == "MockDevice"
        assert device.is_connected is False

    def test_named_arguments_enforced(self):
        # Calling with positional arguments must raise TypeError
        with pytest.raises(TypeError):
            CasambiDevice("AA:BB:CC:DD:EE:FF")  # type: ignore[misc]

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_bleak_client, mock_device, mock_adv_data):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")

        with (
            patch("casambi_classic_ble.device.BleakClient", return_value=mock_bleak_client),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={mock_device.address: (mock_device, mock_adv_data)}),
            ),
        ):
            result = await device.connect()

            assert result is True
            assert device.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_reversed_and_mfr_data(self, mock_bleak_client, mock_device):
        from unittest.mock import MagicMock

        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")

        # 1. Match reversed address: FF:EE:DD:CC:BB:AA
        dev_rev = MagicMock()
        dev_rev.address = "FF:EE:DD:CC:BB:AA"
        adv_rev = MagicMock()
        adv_rev.manufacturer_data = {}

        with (
            patch("casambi_classic_ble.device.BleakClient", return_value=mock_bleak_client),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={dev_rev.address: (dev_rev, adv_rev)}),
            ),
        ):
            assert await device.connect() is True
            assert device.is_connected is True

        # 2. Match manufacturer data
        dev_mfr = MagicMock()
        dev_mfr.address = "11:22:33:44:55:66"
        adv_mfr = MagicMock()
        adv_mfr.manufacturer_data = {963: bytes.fromhex("aabbccddeeff")}
        device._ble_device = None

        with (
            patch("casambi_classic_ble.device.BleakClient", return_value=mock_bleak_client),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={dev_mfr.address: (dev_mfr, adv_mfr)}),
            ),
        ):
            assert await device.connect() is True

    @pytest.mark.asyncio
    async def test_connect_v2_and_not_found(self, mock_bleak_client, mock_device):
        from unittest.mock import MagicMock

        from casambi_classic_ble.constants import CasambiUUIDs

        # V2 service
        srv_v2 = MagicMock()
        srv_v2.uuid = CasambiUUIDs.SERVICE_V2
        mock_bleak_client.services = [srv_v2]

        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        adv = MagicMock()
        adv.manufacturer_data = {}
        with (
            patch("casambi_classic_ble.device.BleakClient", return_value=mock_bleak_client),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={mock_device.address: (mock_device, adv)}),
            ),
        ):
            assert await device.connect() is True
            assert device._control_uuid == CasambiUUIDs.CONTROL_V2

        # Device not found
        device_missing = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        with patch(
            "casambi_classic_ble.device.BleakScanner.discover", new=AsyncMock(return_value={})
        ):
            assert await device_missing.connect() is False
            assert device_missing.is_connected is False

        # Exception during connect
        device_err = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        mock_bleak_client.connect.side_effect = Exception("Connect error")
        device_err._ble_device = mock_device
        with patch("casambi_classic_ble.device.BleakClient", return_value=mock_bleak_client):
            assert await device_err.connect() is False

    @pytest.mark.asyncio
    async def test_turn_on(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        result = await device.turn_on(unit_id=12)

        assert result is True
        mock_bleak_client.write_gatt_char.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        result = await device.turn_off(unit_id=12)

        assert result is True
        mock_bleak_client.write_gatt_char.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_level(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        result = await device.set_level(unit_id=12, level=0.75)

        assert result is True
        mock_bleak_client.write_gatt_char.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        result = await device.authenticate(password="secret")

        assert result is True
        mock_bleak_client.write_gatt_char.assert_called_once()

    def test_parse_status(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        status = device.parse_status(data=bytearray([0x01, 0x05, 0x80]))

        assert status["id"] == 5
        assert status["on"] is True
        assert status["dimLevel"] == pytest.approx(0.502, abs=0.01)

    def test_update_from_advertisement(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        # 6 bytes address (AA:BB:CC:DD:EE:FF), 1 byte flags (0x01 = ON), 1 byte dim level (255)
        mfr_data = bytes.fromhex("aabbccddeeff") + bytes([0x01, 0xFF])
        status = device.update_from_advertisement(mfr_data=mfr_data)

        assert status is not None
        assert status["on"] is True
        assert status["level_percent"] == 100

        # Too short (< 8 bytes)
        assert device.update_from_advertisement(mfr_data=b"\x00" * 7) is None

        # Address mismatch
        assert (
            device.update_from_advertisement(
                mfr_data=bytes.fromhex("112233445566") + bytes([0x01, 0xFF])
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_turn_by_address(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        assert await device.turn_on_by_address(address="AA:BB:CC:DD:EE:FF") is True
        assert await device.turn_off_by_address(address="AA:BB:CC:DD:EE:FF") is True

        # Invalid address length
        assert await device.turn_on_by_address(address="AA:BB") is False
        assert await device.turn_off_by_address(address="AA:BB") is False

    @pytest.mark.asyncio
    async def test_broadcast_commands(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        assert await device.turn_on_broadcast() is True
        assert await device.turn_off_broadcast() is True

    @pytest.mark.asyncio
    async def test_set_color_temp_and_rgb(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        assert await device.set_color_temperature(unit_id=1, temp_kelvin=3500) is True
        assert await device.set_rgb(unit_id=1, r=255, g=128, b=0) is True

    @pytest.mark.asyncio
    async def test_get_state(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        with patch("asyncio.sleep", new=AsyncMock()):
            await device.get_state(unit_id=2)
            assert mock_bleak_client.write_gatt_char.call_count == 2

    @pytest.mark.asyncio
    async def test_disconnect_and_read_status_char(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        mock_bleak_client.read_gatt_char = AsyncMock(return_value=bytearray(b"\x01\x02\x03"))
        data = await device.read_status_char()
        assert data == b"\x01\x02\x03"

        await device.disconnect()
        assert device.is_connected is False
        assert await device.read_status_char() is None

    @pytest.mark.asyncio
    async def test_get_device_info(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        mock_bleak_client.read_gatt_char = AsyncMock(side_effect=[b"Casambi", b"CBU-ASD", b"26.5"])

        info = await device.get_device_info()
        assert info["manufacturer"] == "Casambi"
        assert info["model"] == "CBU-ASD"
        assert info["firmware"] == "26.5"

    @pytest.mark.asyncio
    async def test_send_command_with_session_key(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True
        device._session_key = b"\x01\x02\x03\x04"

        # Send command with payload
        assert await device._send_command(command=0x03, payload=b"\x10\x20") is True
        mock_bleak_client.write_gatt_char.assert_called_once()

    def test_notification_callback(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        received = []
        device.set_notification_callback(callback=lambda d: received.append(d))
        device._notification_handler("test-sender", bytearray([0x01, 0x05, 0xFF]))
        assert len(received) == 1
        assert device.last_state["id"] == 5
