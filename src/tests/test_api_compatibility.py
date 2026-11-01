"""Contract and regression tests verifying snake_case APIs, keyword-only parameters, and deprecations.

Enforces zero-tolerance for silent breaking changes:
1. Canonical public methods enforce keyword-only named arguments.
2. Canonical attributes/properties return expected types and values.
3. Deprecated legacy compatibility shims emit DeprecationWarning when invoked or accessed.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from casambi_classic_ble import Casambi
from casambi_classic_ble._cache import Cache
from casambi_classic_ble._client import (
    CasambiClient,
    CasambiClientClassic,
    ConnectionState,
)
from casambi_classic_ble._constants import IncomingPacketType
from casambi_classic_ble._keystore import KeyStore
from casambi_classic_ble._network import Network
from casambi_classic_ble._operation import OpCode, OperationsContextClassic
from casambi_classic_ble._unit import Group, Scene, Unit, UnitType
from casambi_classic_ble.exceptions import (
    BluetoothDeviceNotFoundError,
    BluetoothError,
    ProtocolError,
)


def test_keyword_only_signatures_enforced():
    """Verify keyword-only arguments (*) are enforced on canonical API signatures."""
    # OperationsContextClassic.prepare_operation
    sig_prepare = inspect.signature(OperationsContextClassic.prepare_operation)
    for param_name in ("op", "target", "payload"):
        assert sig_prepare.parameters[param_name].kind == inspect.Parameter.KEYWORD_ONLY

    # CasambiClient.exchange_key
    sig_exchange = inspect.signature(CasambiClient.exchange_key)
    assert sig_exchange.parameters["retries"].kind == inspect.Parameter.KEYWORD_ONLY

    # CasambiClient.send
    sig_send = inspect.signature(CasambiClient.send)
    assert sig_send.parameters["retries"].kind == inspect.Parameter.KEYWORD_ONLY

    # Network methods
    sig_get_id = inspect.signature(Network.get_network_id)
    assert sig_get_id.parameters["force_offline"].kind == inspect.Parameter.KEYWORD_ONLY

    sig_login = inspect.signature(Network.log_in)
    assert sig_login.parameters["password"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig_login.parameters["force_offline"].kind == inspect.Parameter.KEYWORD_ONLY

    # KeyStore methods
    sig_add_key = inspect.signature(KeyStore.add_key)
    assert sig_add_key.parameters["key_dict"].kind == inspect.Parameter.KEYWORD_ONLY

    sig_set_legacy = inspect.signature(KeyStore.set_legacy_key)
    assert sig_set_legacy.parameters["key"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig_set_legacy.parameters["is_visitor"].kind == inspect.Parameter.KEYWORD_ONLY

    sig_get_legacy = inspect.signature(KeyStore.get_legacy_key)
    assert sig_get_legacy.parameters["role"].kind == inspect.Parameter.KEYWORD_ONLY


def test_unit_canonical_properties_and_access():
    """Verify Unit exposes canonical properties: device_id, type_id, firmware_version, unit_type, is_classic."""
    ut = UnitType(
        id=10,
        model="M-10",
        manufacturer="Casambi",
        mode="DIM",
        stateLength=2,
        controls=[],
    )
    unit = Unit(
        _typeId=10,
        deviceId=5,
        uuid="unit-uuid-123",
        address="AA:BB:CC:DD:EE:05",
        name="Ceiling Light",
        firmwareVersion="2.4",
        unitType=ut,
        _isClassic=True,
    )

    assert unit.device_id == 5
    assert unit.type_id == 10
    assert unit.firmware_version == "2.4"
    assert unit.unit_type is ut
    assert unit.is_classic is True


def test_group_and_scene_canonical_and_deprecated():
    """Verify Group and Scene support canonical snake_case and emit DeprecationWarning for legacy args."""
    # Canonical initialization
    group = Group(group_id=42, name="Hallway", units=[1, 2])
    assert group.group_id == 42
    assert group.name == "Hallway"
    assert group.units == [1, 2]

    scene = Scene(scene_id=99, name="Evening", units={1: 255})
    assert scene.scene_id == 99
    assert scene.name == "Evening"
    assert scene.units == {1: 255}

    # Deprecated property accesses emit warnings
    with pytest.deprecated_call():
        assert group.groupId == 42
    with pytest.deprecated_call():
        assert group.groudId == 42
    with pytest.deprecated_call():
        assert scene.sceneId == 99

    # Deprecated constructor kwargs emit warnings
    with pytest.deprecated_call():
        g_legacy1 = Group(groupId=42, name="Hallway")
        assert g_legacy1.group_id == 42
    with pytest.deprecated_call():
        g_legacy2 = Group(groudId=42, name="Hallway")
        assert g_legacy2.group_id == 42
    with pytest.deprecated_call():
        g_legacy3 = Group(g_id=42, name="Hallway")
        assert g_legacy3.group_id == 42
    with pytest.deprecated_call():
        g_pos = Group(42, "Hallway", [])
        assert g_pos.group_id == 42

    with pytest.deprecated_call():
        s_legacy1 = Scene(sceneId=99, name="Evening")
        assert s_legacy1.scene_id == 99
    with pytest.deprecated_call():
        s_legacy2 = Scene(s_id=99, name="Evening")
        assert s_legacy2.scene_id == 99
    with pytest.deprecated_call():
        s_pos = Scene(99, "Evening")
        assert s_pos.scene_id == 99


def test_operation_context_deprecated_prepare_operation():
    """Verify OperationsContextClassic.prepareOperation emits DeprecationWarning."""
    ctx = OperationsContextClassic()
    unit = Unit(
        _typeId=1,
        deviceId=3,
        uuid="u-3",
        address="AA:BB:CC:DD:EE:03",
        name="U3",
        firmwareVersion="1.0",
        unitType=UnitType(1, "M", "C", "D", 1, []),
    )
    with pytest.deprecated_call():
        pkt = ctx.prepareOperation(op=OpCode.SetLevel, target=unit, payload=b"\x80")
        assert isinstance(pkt, bytes)
        assert 3 in pkt


@pytest.mark.asyncio
async def test_client_deprecated_methods_and_typos():
    """Verify CasambiClientClassic deprecated methods, aliases, and typo _address_or_devive emit warnings."""
    net = MagicMock(spec=Network)
    net.protocol_version = 5
    net.protocolVersion = 5
    key_mock = MagicMock()
    key_mock.key = b"\x01" * 16
    net.keystore.get_legacy_key.return_value = key_mock
    net.keyStore.getLegacyKey.return_value = key_mock

    client = CasambiClientClassic(
        address_or_device="AA:BB:CC:DD:EE:FF",
        dataCallback=MagicMock(),
        disconnected_callback=MagicMock(),
        network=net,
    )

    # _address_or_devive typo getter
    with pytest.deprecated_call():
        assert client._address_or_devive == "AA:BB:CC:DD:EE:FF"

    # _checkState
    with pytest.deprecated_call():
        client._checkState(ConnectionState.NONE)

    # _checkProtocolVersion
    with pytest.deprecated_call():
        client._checkProtocolVersion(5)

    # _queueCallback
    with pytest.deprecated_call():
        client._queueCallback(MagicMock(), bytearray(b"\x01"))

    # _processCallbacks
    with pytest.deprecated_call():
        coro = client._processCallbacks()
        try:
            coro.send(None)
        except (StopIteration, Exception):
            pass
        finally:
            coro.close()

    # _exchNotifyCallback
    with pytest.deprecated_call(), pytest.raises(ProtocolError):
        client._exchNotifyCallback(MagicMock(), b"\x01")

    # _authNotifyCallback
    with pytest.deprecated_call(), pytest.raises(ProtocolError):
        client._authNotifyCallback(MagicMock(), b"\x01")

    # _establishedNotifyCallback
    with pytest.deprecated_call():
        client._establishedNotifyCallback(MagicMock(), b"\x00")

    # _sendInternal
    client._connectionState = ConnectionState.AUTHENTICATED
    client._connhash = b"\x11" * 8
    client._gattClient = AsyncMock()
    with pytest.deprecated_call():
        await client._sendInternal(b"\xaa\xbb")

    # exchangeKey
    client._connectionState = ConnectionState.CONNECTED
    client._gattClient.read_gatt_char = AsyncMock(
        return_value=b"\x11" * 8 + bytes([1, 0, 64, 5, 0])
    )
    client._gattClient.start_notify = AsyncMock()
    with pytest.deprecated_call():
        await client.exchangeKey()


@pytest.mark.asyncio
async def test_network_deprecated_properties_and_methods(tmp_path):
    """Verify Network deprecated properties and aliases emit warnings."""
    cache = Cache(cache_path=tmp_path)
    cache._uuid = "00112233-4455-6677-8899-aabbccddeeff"

    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=AsyncMock(),
        cache=cache,
    )
    net._protocolVersion = 5
    net._keystore = KeyStore(cache)

    # protocolVersion property
    with pytest.deprecated_call():
        assert net.protocolVersion == 5
    assert net.protocol_version == 5

    # keyStore property
    with pytest.deprecated_call():
        assert net.keyStore is net._keystore
    assert net.keystore is net._keystore

    # _saveSesion and _saveSession
    with pytest.deprecated_call():
        await net._saveSesion()
    with pytest.deprecated_call():
        await net._saveSession()

    # _loadSession
    with pytest.deprecated_call():
        await net._loadSession()

    # _loadTypeCache and _saveTypeCache
    with pytest.deprecated_call():
        await net._loadTypeCache()
    with pytest.deprecated_call():
        await net._saveTypeCache()

    # _fetchUnitInfo
    with pytest.deprecated_call():
        await net._fetchUnitInfo(999)


@pytest.mark.asyncio
async def test_casambi_deprecated_internal_methods():
    """Verify Casambi deprecated internal aliases emit warnings."""
    casa = Casambi()
    net = MagicMock(spec=Network)
    net.protocol_version = 5
    net.protocolVersion = 5
    net._networkRevision = 1
    net.units = []
    key_mock = MagicMock()
    key_mock.key = b"\x01" * 16
    net.keystore.get_legacy_key.return_value = key_mock
    net.keyStore.getLegacyKey.return_value = key_mock
    casa._casaNetwork = net
    casa._unitChangedCallbacks = []
    casa._disconnectCallbacks = []

    # _checkNetwork
    with pytest.deprecated_call():
        casa._checkNetwork()

    # _dataCallback
    with pytest.deprecated_call():
        casa._dataCallback(
            IncomingPacketType.UnitState, {"id": 1, "state": b"", "on": True, "online": True}
        )

    # _disconnectCallback
    with pytest.deprecated_call():
        casa._disconnectCallback()

    # _connectClient
    with pytest.deprecated_call():
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.exchange_key = AsyncMock()
        mock_client.authenticate = AsyncMock()
        casa._casaClient = mock_client
        with pytest.raises((BluetoothDeviceNotFoundError, BluetoothError)):
            # Address or connection will fail on live bluetooth, but warning is checked
            await casa._connectClient("AA:BB:CC:DD:EE:FF")
