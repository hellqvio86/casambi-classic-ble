import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakAbortedError,
    BleakNotFoundError,
    BleakOutOfConnectionSlotsError,
)

from casambi_classic_ble._client import (
    CasambiClientClassic,
    CasambiClientEvolution,
    ConnectionState,
)
from casambi_classic_ble._constants import (
    FIRST_EVO_VERSION,
    MIN_EVO_VERSION,
    MIN_SUPPORTED_CLASSIC_VERSION,
    IncomingPacketType,
)
from casambi_classic_ble._encryption import ClassicEncryptor
from casambi_classic_ble._network import Network
from casambi_classic_ble.errors import (
    BluetoothDeviceNotFoundError,
    BluetoothError,
    ConnectionStateError,
    ProtocolError,
    UnsupportedProtocolVersion,
)


@pytest.fixture
def mock_network():
    net = MagicMock(spec=Network)
    net.protocolVersion = 5  # Classic minimum supported version is 5
    key_obj = MagicMock()
    key_obj.key = b"\x01" * 16
    net.keyStore.getLegacyKey.return_value = key_obj
    return net


@pytest.fixture
def mock_classic_client(mock_network):
    data_cb = MagicMock()
    disconnect_cb = MagicMock()
    client = CasambiClientClassic(
        address_or_device="AA:BB:CC:DD:EE:FF",
        dataCallback=data_cb,
        disonnectedCallback=disconnect_cb,
        network=mock_network,
    )
    mock_gatt = AsyncMock()
    mock_gatt.is_connected = True
    client._gattClient = mock_gatt
    return client


def test_protocol_version_checks(mock_network):
    data_cb = MagicMock()
    disconnect_cb = MagicMock()

    # Classic version too low
    mock_network.protocolVersion = MIN_SUPPORTED_CLASSIC_VERSION - 1
    with pytest.raises(UnsupportedProtocolVersion):
        CasambiClientClassic(
            address_or_device="AA:BB:CC:DD:EE:FF",
            dataCallback=data_cb,
            disonnectedCallback=disconnect_cb,
            network=mock_network,
        )

    # Classic version is evolution version
    mock_network.protocolVersion = FIRST_EVO_VERSION
    with pytest.raises(UnsupportedProtocolVersion):
        CasambiClientClassic(
            address_or_device="AA:BB:CC:DD:EE:FF",
            dataCallback=data_cb,
            disonnectedCallback=disconnect_cb,
            network=mock_network,
        )

    # Evolution version too low
    mock_network.protocolVersion = MIN_EVO_VERSION - 1
    with pytest.raises(UnsupportedProtocolVersion):
        CasambiClientEvolution(
            address_or_device="AA:BB:CC:DD:EE:FF",
            dataCallback=data_cb,
            disonnectedCallback=disconnect_cb,
            network=mock_network,
        )


def test_client_state_checks(mock_classic_client):
    mock_classic_client._connectionState = ConnectionState.NONE
    with pytest.raises(ConnectionStateError):
        mock_classic_client._checkState(ConnectionState.AUTHENTICATED)


def test_on_disconnect(mock_classic_client):
    mock_classic_client._connectionState = ConnectionState.AUTHENTICATED
    mock_classic_client._on_disconnect(client=mock_classic_client._gattClient)
    assert mock_classic_client._connectionState == ConnectionState.NONE
    mock_classic_client._disconnectedCallback.assert_called_once()


def test_callback_multiplexer(mock_classic_client):
    handle = MagicMock()

    # In CONNECTED state -> exchNotifyCallback raises ProtocolError
    mock_classic_client._connectionState = ConnectionState.CONNECTED
    with pytest.raises(ProtocolError):
        mock_classic_client._callbackMulitplexer(handle, bytearray([0x01]))

    # In KEY_EXCHANGED state -> authNotifyCallback raises ProtocolError
    mock_classic_client._connectionState = ConnectionState.KEY_EXCHANGED
    with pytest.raises(ProtocolError):
        mock_classic_client._callbackMulitplexer(handle, bytearray([0x01]))

    # In AUTHENTICATED state -> calls establishedNotifyCallback
    mock_classic_client._connectionState = ConnectionState.AUTHENTICATED
    with patch.object(mock_classic_client, "_establishedNotifyCallback") as mock_est:
        mock_classic_client._callbackMulitplexer(handle, bytearray([0x01]))
        mock_est.assert_called_once()
        assert mock_classic_client._inPacketCount == 1


@pytest.mark.asyncio
async def test_classic_exchange_key(mock_classic_client):
    mock_classic_client._connectionState = ConnectionState.CONNECTED

    # Mock response packet:
    # connhash (8 bytes), unit (1 byte), flags_lo (1 byte), mtu (1 byte), protocolVersion (1 byte), flags_high (1 byte)
    resp = bytes.fromhex("0102030405060708") + bytes([1, 0, 23, 5, 0])
    mock_classic_client._gattClient.read_gatt_char.return_value = resp

    await mock_classic_client.exchangeKey()
    assert mock_classic_client._connectionState == ConnectionState.KEY_EXCHANGED
    assert mock_classic_client._connhash == bytes.fromhex("0102030405060708")
    assert mock_classic_client._unit == 1
    assert mock_classic_client._mtu == 23
    mock_classic_client._gattClient.start_notify.assert_called_once()


@pytest.mark.asyncio
async def test_classic_authenticate(mock_classic_client):
    mock_classic_client._connectionState = ConnectionState.KEY_EXCHANGED
    mock_classic_client._connhash = bytes(8)
    mock_classic_client._managerEncryptor = ClassicEncryptor(bytes(16), 4)

    await mock_classic_client.authenticate()
    assert mock_classic_client._connectionState == ConnectionState.AUTHENTICATED
    mock_classic_client._gattClient.write_gatt_char.assert_called_once()


def test_classic_established_notify_callback(mock_classic_client):
    # Skip markers 0x00, 0xFF, 0xF0
    mock_classic_client._establishedNotifyCallback(MagicMock(), bytes([0x00]))
    mock_classic_client._establishedNotifyCallback(MagicMock(), bytes([0xFF]))
    mock_classic_client._establishedNotifyCallback(MagicMock(), bytes([0xF0]))
    assert mock_classic_client._dataCallback.call_count == 0

    # Valid unit state packet:
    # Unit 5, flags: stateLen=2, online=0x80 -> 0x82, state: 0xAA, 0xBB
    packet = bytes([5, 0x82, 0xAA, 0xBB])
    mock_classic_client._establishedNotifyCallback(MagicMock(), packet)
    mock_classic_client._dataCallback.assert_called_once_with(
        IncomingPacketType.UnitState,
        {"id": 5, "online": True, "on": True, "state": bytes([0xAA, 0xBB])},
    )


@pytest.mark.asyncio
async def test_classic_send_and_retry(mock_classic_client):
    mock_classic_client._connectionState = ConnectionState.AUTHENTICATED
    mock_classic_client._connhash = bytes(8)
    mock_classic_client._managerEncryptor = ClassicEncryptor(bytes(16), 4)
    mock_classic_client._outPacketCount = 1

    await mock_classic_client.send(packet=b"\x01\x02")
    assert mock_classic_client._outPacketCount == 2

    # Test BleakError "Not connected"
    mock_classic_client._gattClient.write_gatt_char.side_effect = BleakError("Not connected")
    with pytest.raises(ConnectionStateError):
        await mock_classic_client.send(packet=b"\x01\x02")
    assert mock_classic_client._connectionState == ConnectionState.NONE


@pytest.mark.asyncio
async def test_client_disconnect(mock_classic_client):
    mock_classic_client._connectionState = ConnectionState.AUTHENTICATED
    task = asyncio.create_task(asyncio.sleep(10))
    mock_classic_client._callbackTask = task

    await mock_classic_client.disconnect()
    assert mock_classic_client._connectionState == ConnectionState.NONE
    mock_classic_client._gattClient.disconnect.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_counter", [0, 0x10000])
async def test_classic_sequence_number_skips_zero(mock_classic_client, initial_counter):
    """T-005: Verify _sendInternal never emits sequence 0x0000 and increments counter."""
    mock_classic_client._connectionState = ConnectionState.AUTHENTICATED
    mock_classic_client._connhash = bytes(8)
    mock_classic_client._managerEncryptor = (
        None  # Use 4-byte visitor encryptor (prefix 0x02 + 4B sig)
    )
    mock_classic_client._outPacketCount = initial_counter

    await mock_classic_client.send(packet=b"\xaa\xbb")

    written_bytes = mock_classic_client._gattClient.write_gatt_char.call_args[0][1]
    # Format: 1B prefix (0x02) + 4B signature + 2B sequence + payload
    seq_bytes = written_bytes[5:7]
    assert seq_bytes == b"\x00\x01"
    assert seq_bytes != b"\x00\x00"
    assert mock_classic_client._outPacketCount == initial_counter + 2

    # Next packet uses sequence 0x0002
    await mock_classic_client.send(packet=b"\xcc\xdd")
    written_bytes_2 = mock_classic_client._gattClient.write_gatt_char.call_args[0][1]
    assert written_bytes_2[5:7] == b"\x00\x02"
    assert mock_classic_client._outPacketCount == initial_counter + 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "expected_error", "expected_log_level"),
    [
        (BleakNotFoundError("not found"), BluetoothDeviceNotFoundError, logging.ERROR),
        (BleakOutOfConnectionSlotsError("no slots"), BluetoothError, logging.WARNING),
        (BleakAbortedError("aborted"), BluetoothError, logging.WARNING),
        (BleakError("generic bleak error"), BluetoothError, logging.ERROR),
        (RuntimeError("unexpected boom"), BluetoothError, logging.ERROR),
    ],
)
async def test_connect_exception_hierarchy_and_logging(
    mock_classic_client, caplog, exc, expected_error, expected_log_level
):
    """T-007: Verify specific-first exception handling, log levels, and error chaining."""
    fake_ble_device = MagicMock()
    with (
        patch(
            "casambi_classic_ble._client.get_device", new=AsyncMock(return_value=fake_ble_device)
        ),
        patch("casambi_classic_ble._client.close_stale_connections", new=AsyncMock()),
        patch(
            "casambi_classic_ble._client.establish_connection",
            new=AsyncMock(side_effect=exc),
        ),
        caplog.at_level(logging.WARNING),
    ):
        with pytest.raises(expected_error) as exc_info:
            await mock_classic_client.connect()

        assert exc_info.value.__cause__ is exc
        assert any(r.levelno == expected_log_level for r in caplog.records)

    await mock_classic_client.disconnect()


@pytest.mark.asyncio
async def test_process_callbacks_cancellation_and_casambi_connect_cancel(mock_network, caplog):
    """T-008: Verify _processCallbacks handles CancelledError and Casambi.connect cleans up on cancel."""
    from casambi_classic_ble._casambi import Casambi

    casambi = Casambi()
    casambi._casaNetwork = mock_network

    async def slow_exchange_key():
        await asyncio.sleep(10)

    with (
        patch.object(CasambiClientClassic, "connect", new=AsyncMock()),
        patch.object(CasambiClientClassic, "exchangeKey", side_effect=slow_exchange_key),
        caplog.at_level(logging.INFO),
    ):
        connect_task = asyncio.create_task(casambi._connectClient("AA:BB:CC:DD:EE:FF"))
        await asyncio.sleep(0.02)
        connect_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await connect_task

        assert casambi._casaClient._connectionState == ConnectionState.NONE
        assert casambi._casaClient._callbackTask is None


@pytest.mark.parametrize(
    "malformed_frame",
    [
        b"",  # Empty frame
        b"\x05",  # 1-byte frame (missing flags)
        bytes([5, 0x22]),  # Header with extra1 bit (0x20) set, but no extra1 byte
        bytes([5, 0x62, 0x11]),  # Header with extra1+extra2 (0x60) set, but only 1 extra byte
        bytes([5, 0x82, 0xAA]),  # Truncated state (stateLen=2, only 1 byte present)
    ],
)
def test_classic_established_notify_truncated_frames_do_not_raise(
    mock_classic_client, malformed_frame
):
    """T-009: Verify truncated frames never raise IndexError and do not invoke dataCallback."""
    mock_classic_client._establishedNotifyCallback(MagicMock(), malformed_frame)
    mock_classic_client._dataCallback.assert_not_called()


def test_classic_established_notify_multi_unit_with_extras(mock_classic_client):
    """T-009: Verify valid multi-unit frame with extra1/extra2 parses all units cleanly."""
    # Unit 1: stateLen=2, extra1=True (0x20), online=True (0x80) -> flags=0xA2, extra1=0x10, state=0xAA,0xBB
    # Unit 2: stateLen=1, extra2=True (0x40), online=False -> flags=0x41, extra2=0x20, state=0xCC
    frame = bytes([1, 0xA2, 0x10, 0xAA, 0xBB, 2, 0x41, 0x20, 0xCC])
    mock_classic_client._establishedNotifyCallback(MagicMock(), frame)

    assert mock_classic_client._dataCallback.call_count == 2
    mock_classic_client._dataCallback.assert_any_call(
        IncomingPacketType.UnitState,
        {"id": 1, "online": True, "on": True, "state": bytes([0xAA, 0xBB])},
    )
    mock_classic_client._dataCallback.assert_any_call(
        IncomingPacketType.UnitState,
        {"id": 2, "online": False, "on": True, "state": bytes([0xCC])},
    )
