import asyncio
import logging
import struct
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
    ConnectionState,
)
from casambi_classic_ble._constants import (
    FIRST_UNSUPPORTED_PROTOCOL_VERSION,
    MIN_SUPPORTED_CLASSIC_VERSION,
    IncomingPacketType,
)
from casambi_classic_ble._encryption import ClassicEncryptor
from casambi_classic_ble._network import Network
from casambi_classic_ble.exceptions import (
    BluetoothDeviceNotFoundError,
    BluetoothError,
    ConnectionStateError,
    ProtocolError,
    UnsupportedProtocolVersion,
)


@pytest.fixture
def mock_network():
    net = MagicMock(spec=Network)
    net.protocol_version = 5  # Classic minimum supported version is 5
    net.protocolVersion = 5
    key_obj = MagicMock()
    key_obj.key = b"\x01" * 16
    net.keystore.get_legacy_key.return_value = key_obj
    net.keyStore.getLegacyKey.return_value = key_obj
    return net


@pytest.fixture
def mock_classic_client(mock_network):
    data_cb = MagicMock()
    disconnect_cb = MagicMock()
    client = CasambiClientClassic(
        address_or_device="AA:BB:CC:DD:EE:FF",
        dataCallback=data_cb,
        disconnected_callback=disconnect_cb,
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
    mock_network.protocol_version = MIN_SUPPORTED_CLASSIC_VERSION - 1
    mock_network.protocolVersion = MIN_SUPPORTED_CLASSIC_VERSION - 1
    with pytest.raises(UnsupportedProtocolVersion):
        CasambiClientClassic(
            address_or_device="AA:BB:CC:DD:EE:FF",
            dataCallback=data_cb,
            disconnected_callback=disconnect_cb,
            network=mock_network,
        )

    # Unsupported version (>= 10)
    mock_network.protocol_version = FIRST_UNSUPPORTED_PROTOCOL_VERSION
    mock_network.protocolVersion = FIRST_UNSUPPORTED_PROTOCOL_VERSION
    with pytest.raises(UnsupportedProtocolVersion):
        CasambiClientClassic(
            address_or_device="AA:BB:CC:DD:EE:FF",
            dataCallback=data_cb,
            disconnected_callback=disconnect_cb,
            network=mock_network,
        )


def test_client_state_checks(mock_classic_client):
    mock_classic_client._connectionState = ConnectionState.NONE
    with pytest.raises(ConnectionStateError):
        mock_classic_client._check_state(ConnectionState.AUTHENTICATED)

    with pytest.deprecated_call(), pytest.raises(ConnectionStateError):
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
        mock_classic_client._callback_multiplexer(handle, bytearray([0x01]))

    # In KEY_EXCHANGED state -> authNotifyCallback raises ProtocolError
    mock_classic_client._connectionState = ConnectionState.KEY_EXCHANGED
    with pytest.raises(ProtocolError):
        mock_classic_client._callback_multiplexer(handle, bytearray([0x01]))

    # In AUTHENTICATED state -> calls established_notify_callback
    mock_classic_client._connectionState = ConnectionState.AUTHENTICATED
    with patch.object(mock_classic_client, "_established_notify_callback") as mock_est:
        mock_classic_client._callback_multiplexer(handle, bytearray([0x01]))
        mock_est.assert_called_once()
        assert mock_classic_client._inPacketCount == 1


@pytest.mark.asyncio
async def test_classic_exchange_key(mock_classic_client):
    mock_classic_client._connectionState = ConnectionState.CONNECTED

    # Mock response packet:
    # connhash (8 bytes), unit (1 byte), flags_lo (1 byte), mtu (1 byte), protocolVersion (1 byte), flags_high (1 byte)
    resp = bytes.fromhex("0102030405060708") + bytes([1, 0, 23, 5, 0])
    mock_classic_client._gattClient.read_gatt_char.return_value = resp

    await mock_classic_client.exchange_key()
    assert mock_classic_client._connectionState == ConnectionState.KEY_EXCHANGED
    assert mock_classic_client._connhash == bytes.fromhex("0102030405060708")
    assert mock_classic_client._unit == 1
    assert mock_classic_client._mtu == 23
    mock_classic_client._gattClient.start_notify.assert_called_once()

    # Deprecated alias emits DeprecationWarning
    mock_classic_client._connectionState = ConnectionState.CONNECTED
    with pytest.deprecated_call():
        await mock_classic_client.exchangeKey()


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
    mock_classic_client._established_notify_callback(MagicMock(), bytes([0x00]))
    mock_classic_client._established_notify_callback(MagicMock(), bytes([0xFF]))
    mock_classic_client._established_notify_callback(MagicMock(), bytes([0xF0]))
    assert mock_classic_client._dataCallback.call_count == 0

    # Valid unit state packet:
    # Unit 5, flags: stateLen=2, online=0x80 -> 0x82, state: 0xAA, 0xBB
    packet = bytes([5, 0x82, 0xAA, 0xBB])
    mock_classic_client._established_notify_callback(MagicMock(), packet)
    mock_classic_client._dataCallback.assert_called_once_with(
        IncomingPacketType.UnitState,
        {"id": 5, "online": True, "on": True, "state": bytes([0xAA, 0xBB])},
    )

    # Deprecated alias emits DeprecationWarning
    with pytest.deprecated_call():
        mock_classic_client._establishedNotifyCallback(MagicMock(), bytes([0x00]))


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
        assert mock_classic_client._callbackTask is None or mock_classic_client._callbackTask.done()

    await mock_classic_client.disconnect()


@pytest.mark.asyncio
async def test_connect_failure_does_not_leak_callback_task_on_get_device_miss(
    mock_classic_client,
) -> None:
    """T-006: Verify get_device returning None raises BluetoothDeviceNotFoundError without task leak."""
    with (
        patch("casambi_classic_ble._client.get_device", new=AsyncMock(return_value=None)),
        pytest.raises(BluetoothDeviceNotFoundError),
    ):
        await mock_classic_client.connect()

    assert mock_classic_client._callbackTask is None
    assert mock_classic_client._callbackQueue is None


@pytest.mark.asyncio
async def test_connect_failure_does_not_leak_callback_task_on_establish_failure(
    mock_classic_client,
) -> None:
    """T-006: Verify establish_connection failure cleans up callback task without leak."""
    fake_ble_device = MagicMock()
    with (
        patch(
            "casambi_classic_ble._client.get_device", new=AsyncMock(return_value=fake_ble_device)
        ),
        patch("casambi_classic_ble._client.close_stale_connections", new=AsyncMock()),
        patch(
            "casambi_classic_ble._client.establish_connection",
            new=AsyncMock(side_effect=BleakError("Connection failed")),
        ),
        pytest.raises(BluetoothError),
    ):
        await mock_classic_client.connect()

    assert mock_classic_client._callbackTask is None or mock_classic_client._callbackTask.done()


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
        patch.object(CasambiClientClassic, "exchange_key", side_effect=slow_exchange_key),
        caplog.at_level(logging.INFO),
    ):
        connect_task = asyncio.create_task(casambi._connect_client("AA:BB:CC:DD:EE:FF"))
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
    mock_classic_client, malformed_frame, caplog
):
    """T-009: Verify truncated frames never raise IndexError, log ERROR containing packet, and do not invoke dataCallback."""
    with caplog.at_level(logging.ERROR):
        mock_classic_client._established_notify_callback(MagicMock(), malformed_frame)
    mock_classic_client._dataCallback.assert_not_called()
    assert any("Malformed packet" in rec.getMessage() for rec in caplog.records)
    if malformed_frame:
        assert any(malformed_frame.hex() in rec.getMessage() for rec in caplog.records)


def test_classic_established_notify_multi_unit_with_extras(mock_classic_client):
    """T-009: Verify valid multi-unit frame with extra1/extra2 parses all units cleanly."""
    # Unit 1: stateLen=2, extra1=True (0x20), online=True (0x80) -> flags=0xA2, extra1=0x10, state=0xAA,0xBB
    # Unit 2: stateLen=1, extra2=True (0x40), online=False -> flags=0x41, extra2=0x20, state=0xCC
    frame = bytes([1, 0xA2, 0x10, 0xAA, 0xBB, 2, 0x41, 0x20, 0xCC])
    mock_classic_client._established_notify_callback(MagicMock(), frame)

    assert mock_classic_client._dataCallback.call_count == 2
    mock_classic_client._dataCallback.assert_any_call(
        IncomingPacketType.UnitState,
        {"id": 1, "online": True, "on": True, "state": bytes([0xAA, 0xBB])},
    )
    mock_classic_client._dataCallback.assert_any_call(
        IncomingPacketType.UnitState,
        {"id": 2, "online": False, "on": True, "state": bytes([0xCC])},
    )


@pytest.mark.asyncio
async def test_classic_exchange_key_parses_device_info(mock_classic_client):
    """Q-002: Verify exchangeKey parses device info (>8sBBBBB) and sets connection state."""
    mock_classic_client._connectionState = ConnectionState.CONNECTED
    # >8sBBBBB: connhash(8B), unit(1B), flags_lo(1B), mtu(1B), protocolVersion(1B), flags_high(1B)
    connhash = b"\x11\x22\x33\x44\x55\x66\x77\x88"
    resp = struct.pack(">8sBBBBB", connhash, 1, 2, 128, 5, 0)
    mock_classic_client._gattClient.read_gatt_char = AsyncMock(return_value=resp)
    mock_classic_client._gattClient.start_notify = AsyncMock()

    await mock_classic_client.exchange_key()

    assert mock_classic_client._connhash == connhash
    assert mock_classic_client._unit == 1
    assert mock_classic_client._flags == 2
    assert mock_classic_client._mtu == 128
    assert mock_classic_client._connectionState == ConnectionState.KEY_EXCHANGED
    mock_classic_client._gattClient.start_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_classic_exchange_key_transient_error_retry(mock_classic_client):
    """Q-002: Verify exchangeKey retries on transient BleakError during read_gatt_char."""
    mock_classic_client._connectionState = ConnectionState.CONNECTED
    connhash = b"\x11" * 8
    valid_resp = struct.pack(">8sBBBBB", connhash, 1, 0, 64, 5, 0)

    # Retry succeeds on second attempt
    mock_classic_client._gattClient.read_gatt_char = AsyncMock(
        side_effect=[BleakError("Device busy"), valid_resp]
    )
    mock_classic_client._gattClient.start_notify = AsyncMock()

    await mock_classic_client.exchange_key(retries=2)
    assert mock_classic_client._connectionState == ConnectionState.KEY_EXCHANGED

    # Exceeding retries raises BluetoothError
    mock_classic_client._connectionState = ConnectionState.CONNECTED
    mock_classic_client._gattClient.read_gatt_char = AsyncMock(
        side_effect=BleakError("Device busy")
    )
    with pytest.raises(BluetoothError, match="Failed to initiate GATT read"):
        await mock_classic_client.exchange_key(retries=1)


@pytest.mark.asyncio
async def test_classic_authenticate_flow(mock_classic_client):
    """Q-002: Verify authenticate sends version, increments outPacketCount, and authenticates."""
    mock_classic_client._connectionState = ConnectionState.KEY_EXCHANGED
    mock_classic_client._outPacketCount = 1
    mock_classic_client._connhash = b"\x22" * 8

    await mock_classic_client.authenticate()

    assert mock_classic_client._connectionState == ConnectionState.AUTHENTICATED
    assert mock_classic_client._outPacketCount == 2
    mock_classic_client._gattClient.write_gatt_char.assert_awaited_once()


@pytest.mark.asyncio
async def test_classic_send_internal_manager_vs_visitor(mock_classic_client):
    """Q-002: Verify manager key uses prefix 0x03 and visitor key uses prefix 0x02."""
    mock_classic_client._connhash = b"\x33" * 8
    mock_classic_client._outPacketCount = 1

    # 1. Manager encryptor present -> prefix 0x03, 16-byte CMAC digest
    await mock_classic_client._send_internal(b"\xaa\xbb")
    written_data = mock_classic_client._gattClient.write_gatt_char.call_args[0][1]
    assert written_data[0] == 0x03
    # 1B prefix + 2B seq + 2B payload + 16B CMAC = 21 bytes
    assert len(written_data) == 21

    # 2. Visitor encryptor only -> prefix 0x02, 4-byte CMAC digest
    mock_classic_client._managerEncryptor = None
    mock_classic_client._gattClient.write_gatt_char.reset_mock()
    await mock_classic_client._send_internal(b"\xaa\xbb")
    written_data = mock_classic_client._gattClient.write_gatt_char.call_args[0][1]
    assert written_data[0] == 0x02
    # 1B prefix + 2B seq + 2B payload + 4B CMAC = 9 bytes
    assert len(written_data) == 9


@pytest.mark.asyncio
async def test_classic_send_internal_disconnected_raises_connection_state_error(
    mock_classic_client,
):
    """Q-002: Verify 'Not connected' BleakError raises ConnectionStateError and resets state."""
    mock_classic_client._connhash = b"\x44" * 8
    mock_classic_client._connectionState = ConnectionState.AUTHENTICATED
    mock_classic_client._gattClient.write_gatt_char = AsyncMock(
        side_effect=BleakError("Not connected")
    )

    with pytest.raises(ConnectionStateError):
        await mock_classic_client._send_internal(b"\x01")

    assert mock_classic_client._connectionState == ConnectionState.NONE


@pytest.mark.asyncio
async def test_classic_send_internal_generic_bleak_error_raises_bluetooth_error(
    mock_classic_client,
):
    """Q-002: Verify generic BleakError during write raises BluetoothError."""
    mock_classic_client._connhash = b"\x44" * 8
    mock_classic_client._gattClient.write_gatt_char = AsyncMock(
        side_effect=BleakError("ATT write failure")
    )

    with pytest.raises(BluetoothError):
        await mock_classic_client._send_internal(b"\x01")


def test_classic_unsupported_callbacks_raise_protocol_error(mock_classic_client):
    """Q-002: Verify handshake notify callbacks reject unexpected packets."""
    with pytest.raises(ProtocolError):
        mock_classic_client._exch_notify_callback(MagicMock(), b"\x01")

    with pytest.raises(ProtocolError):
        mock_classic_client._auth_notify_callback(MagicMock(), b"\x01")


@pytest.mark.asyncio
async def test_classic_client_connect_success_and_callback_loop(mock_network):
    """Q-002: Verify successful connect() initializes callback task and queue."""
    mock_gatt = AsyncMock()
    mock_gatt.is_connected = True
    data_cb = MagicMock()
    disc_cb = MagicMock()

    client = CasambiClientClassic(
        address_or_device="AA:BB:CC:DD:EE:FF",
        dataCallback=data_cb,
        disconnected_callback=disc_cb,
        network=mock_network,
    )

    with (
        patch("casambi_classic_ble._client.get_device", new=AsyncMock(return_value=MagicMock())),
        patch("casambi_classic_ble._client.close_stale_connections", new=AsyncMock()),
        patch(
            "casambi_classic_ble._client.establish_connection",
            new=AsyncMock(return_value=mock_gatt),
        ),
    ):
        await client.connect()
        assert client._connectionState == ConnectionState.CONNECTED
        assert client._callbackTask is not None

        # Queue a callback and verify the loop processes it
        client._connectionState = ConnectionState.AUTHENTICATED
        frame = bytes([1, 0x81, 0xAA])
        client._queue_callback(MagicMock(), bytearray(frame))
        await asyncio.sleep(0.02)
        data_cb.assert_called_once()

        await client.disconnect()
        assert client._connectionState == ConnectionState.NONE
        assert client._callbackTask is None


@pytest.mark.asyncio
async def test_classic_disconnect_handles_bleak_error(mock_classic_client):
    """Q-002: Disconnect swallows BleakError cleanly."""
    mock_classic_client._gattClient.disconnect = AsyncMock(
        side_effect=BleakError("Disconnect error")
    )
    await mock_classic_client.disconnect()
    assert mock_classic_client._connectionState == ConnectionState.NONE


@pytest.mark.asyncio
async def test_classic_exchange_key_version_mismatch_and_notify_failure(mock_classic_client):
    """Q-002: Verify version mismatch logs warning and start_notify BleakError raises BluetoothError."""
    mock_classic_client._connectionState = ConnectionState.CONNECTED
    # Protocol version 7 reported by device (network expected 5)
    resp = struct.pack(">8sBBBBB", b"\x11" * 8, 1, 0, 64, 7, 0)
    mock_classic_client._gattClient.read_gatt_char = AsyncMock(return_value=resp)
    mock_classic_client._gattClient.start_notify = AsyncMock(
        side_effect=BleakError("Notify failed")
    )

    with pytest.raises(BluetoothError, match="Failed to initiate GATT notify"):
        await mock_classic_client.exchange_key()


def test_classic_constructor_validations(mock_network):
    """Q-002: Verify constructor requires callbacks, network, and visitor key."""
    # Missing disconnected callback
    with pytest.raises(ValueError, match="disconnected_callback is required"):
        CasambiClientClassic(
            address_or_device="AA:BB:CC:DD:EE:FF",
            dataCallback=MagicMock(),
            disconnected_callback=None,
            network=mock_network,
        )

    # Missing network
    with pytest.raises(ValueError, match="network is required"):
        CasambiClientClassic(
            address_or_device="AA:BB:CC:DD:EE:FF",
            dataCallback=MagicMock(),
            disconnected_callback=MagicMock(),
            network=None,
        )

    # Missing visitor key
    bad_net = MagicMock(spec=Network)
    bad_net.protocol_version = 5
    bad_net.protocolVersion = 5
    bad_net.keystore.get_legacy_key.return_value = None
    bad_net.keyStore.getLegacyKey.return_value = None
    with pytest.raises(ProtocolError, match="Can't continue without visitor key"):
        CasambiClientClassic(
            address_or_device="AA:BB:CC:DD:EE:FF",
            dataCallback=MagicMock(),
            disconnected_callback=MagicMock(),
            network=bad_net,
        )


def test_classic_callback_multiplexer_unhandled_state(mock_classic_client, caplog):
    """Q-002: Verify unhandled notify in NONE state logs warning."""
    mock_classic_client._connectionState = ConnectionState.NONE
    with caplog.at_level(logging.WARNING):
        mock_classic_client._callback_multiplexer(MagicMock(), b"\x01\x02")
    assert "Unhandled notify in state" in caplog.text


def test_disconnect_marks_offline_before_callback(mock_classic_client):
    """Verify that _connectionState is set to NONE before disconnectedCallback executes."""
    mock_classic_client._connectionState = ConnectionState.AUTHENTICATED
    observed = []
    mock_classic_client._disconnectedCallback.side_effect = lambda: observed.append(
        mock_classic_client._connectionState
    )
    mock_classic_client._on_disconnect(client=MagicMock())
    assert observed == [ConnectionState.NONE]
    assert mock_classic_client._connectionState == ConnectionState.NONE


async def test_disconnect_allows_eager_reconnect(mock_classic_client):
    """Verify that eager reconnect tasks in disconnect callback succeed and keep connected state."""
    from casambi_classic_ble import Casambi

    casa = Casambi.__new__(Casambi)
    casa._casaNetwork = MagicMock(spec=Network)
    casa._casaNetwork.protocol_version = 5
    casa._casaNetwork.protocolVersion = 5
    casa._casaNetwork._networkRevision = 1
    casa._casaClient = mock_classic_client
    casa._connectionLock = asyncio.Lock()
    mock_classic_client.disconnect = AsyncMock()

    async def fake_connect(address):
        mock_classic_client._connectionState = ConnectionState.AUTHENTICATED

    casa._connect_client = AsyncMock(side_effect=fake_connect)
    tasks = []

    def disconnected():
        # Home Assistant executes config entry background tasks with eager_start=True
        loop = asyncio.get_running_loop()
        tasks.append(
            asyncio.Task(
                casa.reconnect(address="AA:BB:CC:DD:EE:FF"),
                eager_start=True,
                loop=loop,
            )
        )

    mock_classic_client._disconnectedCallback = disconnected
    mock_classic_client._connectionState = ConnectionState.AUTHENTICATED
    mock_classic_client._on_disconnect(client=MagicMock())

    await asyncio.gather(*tasks)
    casa._connect_client.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")
    assert casa.connected


async def test_disconnect_cleans_up_gatt_client_even_when_not_connected(mock_classic_client):
    """Verify that BleakClient.disconnect is awaited even when is_connected is already False."""
    mock_classic_client._gattClient.is_connected = False
    await mock_classic_client.disconnect()
    mock_classic_client._gattClient.disconnect.assert_awaited_once()


async def test_device_disconnect_cleans_up_client_even_when_not_connected():
    """Verify CasambiDevice.disconnect calls BleakClient.disconnect even if is_connected is False."""
    from casambi_classic_ble import CasambiDevice

    mock_bleak = AsyncMock()
    mock_bleak.is_connected = False
    device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak)
    device._is_connected = False

    await device.disconnect()
    mock_bleak.disconnect.assert_awaited_once()
