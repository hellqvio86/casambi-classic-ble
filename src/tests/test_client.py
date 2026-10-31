import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

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

    await mock_classic_client.send(packet=b"\x01\x02")
    assert mock_classic_client._outPacketCount == 1

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
