from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from casambi_classic_ble import Casambi
from casambi_classic_ble._client import ConnectionState
from casambi_classic_ble._constants import IncomingPacketType
from casambi_classic_ble._network import Network
from casambi_classic_ble._operation import OperationsContextClassic
from casambi_classic_ble._switch import ButtonEventType, SwitchEvent
from casambi_classic_ble._unit import (
    Group,
    Scene,
    Unit,
    UnitControl,
    UnitControlType,
    UnitState,
    UnitType,
)
from casambi_classic_ble.exceptions import ConnectionStateError


@pytest.fixture
def dummy_unit():
    ctrl_dimmer = UnitControl(
        type=UnitControlType.DIMMER,
        offset=0,
        length=8,
        default=0,
        readonly=False,
    )
    ctrl_rgb = UnitControl(
        type=UnitControlType.RGB,
        offset=8,
        length=24,
        default=0,
        readonly=False,
    )
    ut = UnitType(
        id=1,
        model="TestModel",
        manufacturer="Casambi",
        mode="DIM",
        stateLength=4,
        controls=[ctrl_dimmer, ctrl_rgb],
    )
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="u-1",
        address="AA:BB:CC:DD:EE:FF",
        name="TestUnit",
        firmwareVersion="1.0",
        unitType=ut,
    )
    return unit


@pytest.fixture
def mock_casambi(dummy_unit):
    casa = Casambi()
    mock_net = MagicMock(spec=Network)
    mock_net.protocol_version = 1  # classic
    mock_net.protocolVersion = 1  # classic
    mock_net._networkRevision = 1
    mock_net._networkName = "MyNetwork"
    mock_net._id = "net-id-123"
    mock_net.units = [dummy_unit]
    mock_net.groups = [Group(group_id=1, name="G1", units=[1])]
    mock_net.scenes = [Scene(scene_id=1, name="S1", units={1: 255})]
    casa._casaNetwork = mock_net

    mock_client = AsyncMock()
    mock_client._connectionState = ConnectionState.AUTHENTICATED
    mock_client._address_or_device = "AA:BB:CC:DD:EE:FF"
    casa._casaClient = mock_client
    casa._opContext = OperationsContextClassic()
    return casa


def test_casambi_properties_unconnected():
    casa = Casambi()
    with pytest.raises(ConnectionStateError):
        _ = casa.network_name
    with pytest.raises(ConnectionStateError):
        _ = casa.network_id
    with pytest.raises(ConnectionStateError):
        _ = casa.units
    with pytest.raises(ConnectionStateError):
        _ = casa.groups
    with pytest.raises(ConnectionStateError):
        _ = casa.scenes
    assert not casa.connected

    # Test deprecated properties
    with pytest.deprecated_call(), pytest.raises(ConnectionStateError):
        _ = casa.networkName
    with pytest.deprecated_call(), pytest.raises(ConnectionStateError):
        _ = casa.networkId


def test_casambi_properties_connected(mock_casambi):
    assert mock_casambi.network_name == "MyNetwork"
    assert mock_casambi.network_id == "net-id-123"
    assert len(mock_casambi.units) == 1
    assert len(mock_casambi.groups) == 1
    assert len(mock_casambi.scenes) == 1
    assert mock_casambi.connected

    # Test deprecated property aliases
    with pytest.deprecated_call():
        assert mock_casambi.networkName == "MyNetwork"
    with pytest.deprecated_call():
        assert mock_casambi.networkId == "net-id-123"


@pytest.mark.asyncio
async def test_casambi_control_methods(mock_casambi, dummy_unit):
    # set_level
    await mock_casambi.set_level(target=dummy_unit, level=128)
    mock_casambi._casaClient.send.assert_called()

    with pytest.raises(ValueError):
        await mock_casambi.set_level(target=dummy_unit, level=-1)
    with pytest.raises(ValueError):
        await mock_casambi.set_level(target=dummy_unit, level=256)

    # set_vertical
    await mock_casambi.set_vertical(target=dummy_unit, vertical=64)
    with pytest.raises(ValueError):
        await mock_casambi.set_vertical(target=dummy_unit, vertical=300)

    # set_white
    await mock_casambi.set_white(target=dummy_unit, level=100)
    with pytest.raises(ValueError):
        await mock_casambi.set_white(target=dummy_unit, level=300)

    # set_color
    await mock_casambi.set_color(target=dummy_unit, rgb_color=(255, 0, 0))

    # set_temperature
    await mock_casambi.set_temperature(target=dummy_unit, temperature=3000)

    # Operations unsupported on Classic OpCode map raise ValueError
    with pytest.raises(ValueError, match="not supported on Classic"):
        await mock_casambi.set_slider(target=dummy_unit, value=50)

    with pytest.raises(ValueError, match=r"isn't supported|not supported on Classic"):
        await mock_casambi.set_color_xy(target=dummy_unit, xy_color=(0.4, 0.4))

    # turn_on & turn_off
    await mock_casambi.turn_on(target=dummy_unit)
    await mock_casambi.turn_off(target=dummy_unit)

    # switch_to_scene
    scene = mock_casambi.scenes[0]
    await mock_casambi.switch_to_scene(target=scene, level=200)

    # set_control_value and set_white_color_balance raise ValueError on Classic
    ctrl = dummy_unit.unitType.controls[0]
    with pytest.raises(ValueError, match="not supported on Classic"):
        await mock_casambi.set_control_value(unit=dummy_unit, control=ctrl, value=255)

    with pytest.raises(
        ValueError, match=r"The unit does not support WHITECOLORBALANCE|not supported on Classic"
    ):
        await mock_casambi.set_white_color_balance(unit=dummy_unit, value=30)

    # Deprecated camelCase aliases emit DeprecationWarning
    with pytest.deprecated_call():
        await mock_casambi.setLevel(target=dummy_unit, level=128)
    with pytest.deprecated_call():
        await mock_casambi.setVertical(target=dummy_unit, vertical=64)
    with pytest.deprecated_call():
        await mock_casambi.setWhite(target=dummy_unit, level=100)
    with pytest.deprecated_call():
        await mock_casambi.setColor(target=dummy_unit, rgbColor=(255, 0, 0))
    with pytest.deprecated_call():
        await mock_casambi.setTemperature(target=dummy_unit, temperature=3000)
    with pytest.deprecated_call():
        await mock_casambi.turnOn(target=dummy_unit)
    with pytest.deprecated_call():
        await mock_casambi.turnOff(target=dummy_unit)
    with pytest.deprecated_call():
        await mock_casambi.switchToScene(target=scene, level=200)


@pytest.mark.asyncio
async def test_casambi_set_unit_state(mock_casambi, dummy_unit):
    st = UnitState()
    st.dimmer = 150
    await mock_casambi.set_unit_state(target=dummy_unit, state=st)
    mock_casambi._casaClient.send.assert_called()

    with pytest.deprecated_call():
        await mock_casambi.setUnitState(target=dummy_unit, state=st)


@pytest.mark.asyncio
async def test_casambi_callbacks_and_data_handling(mock_casambi, dummy_unit):
    unit_events = []
    switch_events = []
    disconnect_events = []

    def on_unit_changed(u: Unit) -> None:
        unit_events.append(u)

    def on_switch_event(s: SwitchEvent) -> None:
        switch_events.append(s)

    def on_disconnect() -> None:
        disconnect_events.append(True)

    mock_casambi.register_unit_changed_handler(handler=on_unit_changed)
    mock_casambi.register_switch_event_handler(handler=on_switch_event)
    mock_casambi.register_disconnect_callback(callback=on_disconnect)

    # Data callback: UnitState
    mock_casambi._data_callback(
        packetType=IncomingPacketType.UnitState,
        data={"id": dummy_unit.deviceId, "state": b"\x80\x00\x00\x00", "on": True, "online": True},
    )
    assert len(unit_events) == 1
    assert dummy_unit.is_on is True

    # Data callback: SwitchEvent
    sw = SwitchEvent(
        button_event_index=0,
        button=1,
        unit_id=1,
        target_type=0x06,
        event=ButtonEventType.PRESS,
        flags=0,
        extra_data=b"",
    )
    mock_casambi._data_callback(packetType=IncomingPacketType.SwitchEvent, data=sw)
    assert len(switch_events) == 1

    # Disconnect callback
    mock_casambi._disconnect_callback()
    assert len(disconnect_events) == 1
    assert dummy_unit.online is False

    # Deprecated callback method aliases emit DeprecationWarning
    with pytest.deprecated_call():
        mock_casambi._dataCallback(
            packetType=IncomingPacketType.UnitState,
            data={
                "id": dummy_unit.deviceId,
                "state": b"\x80\x00\x00\x00",
                "on": True,
                "online": True,
            },
        )
    with pytest.deprecated_call():
        mock_casambi._disconnectCallback()

    # Unregister
    mock_casambi.unregister_unit_changed_handler(handler=on_unit_changed)
    mock_casambi.unregister_switch_event_handler(handler=on_switch_event)
    mock_casambi.unregister_disconnect_callback(callback=on_disconnect)

    # Verify deprecated registration methods emit warnings
    with pytest.deprecated_call():
        mock_casambi.registerUnitChangedHandler(handler=on_unit_changed)
    with pytest.deprecated_call():
        mock_casambi.unregisterUnitChangedHandler(handler=on_unit_changed)
    with pytest.deprecated_call():
        mock_casambi.registerSwitchEventHandler(handler=on_switch_event)
    with pytest.deprecated_call():
        mock_casambi.unregisterSwitchEventHandler(handler=on_switch_event)
    with pytest.deprecated_call():
        mock_casambi.registerDisconnectCallback(callback=on_disconnect)
    with pytest.deprecated_call():
        mock_casambi.unregisterDisconnectCallback(callback=on_disconnect)


@pytest.mark.asyncio
async def test_casambi_disconnect_and_cache(mock_casambi, tmp_path):
    mock_casambi._ownHttpClient = True
    mock_casambi._httpClient = AsyncMock()

    await mock_casambi.disconnect()
    mock_casambi._casaClient.disconnect.assert_called_once()
    assert mock_casambi._casaNetwork is None

    # Test cache invalidation
    casa = Casambi(cache_path=tmp_path)
    await casa.invalidate_cache(uuid="aabbccddeeff")

    with pytest.deprecated_call():
        casa_deprecated = Casambi(cachePath=tmp_path)
        await casa_deprecated.invalidateCache(uuid="aabbccddeeff")


@pytest.mark.asyncio
async def test_casambi_connect_and_reconnect():
    casa = Casambi()
    mock_net = AsyncMock(spec=Network)
    mock_net.protocol_version = 1  # classic
    mock_net.protocolVersion = 1  # classic
    mock_net._networkRevision = 1

    with (
        patch("casambi_classic_ble._casambi.Network", return_value=mock_net),
        patch("casambi_classic_ble._casambi.CasambiClientClassic") as mock_classic_cls,
    ):
        mock_client = AsyncMock()
        mock_client._connectionState = ConnectionState.AUTHENTICATED
        mock_classic_cls.return_value = mock_client

        # Connect with hex address without colons
        await casa.connect(address="aabbccddeeff", password="pass", force_offline=False)
        mock_net.load.assert_called_once()
        mock_net.log_in.assert_called_once_with(password="pass", force_offline=False)
        mock_net.update.assert_called_once_with(force_offline=False)
        mock_client.connect.assert_called_once()
        mock_client.exchange_key.assert_called_once()
        mock_client.authenticate.assert_called_once()

        # Reconnect when already connected does nothing
        await casa.reconnect(address="AA:BB:CC:DD:EE:FF")

        # Reconnect when not connected
        mock_client._connectionState = ConnectionState.CONNECTED
        await casa.reconnect(address="AA:BB:CC:DD:EE:FF")
        mock_client.disconnect.assert_called_once()

        # Deprecated connect / reconnect with warning
        with pytest.deprecated_call():
            await casa.connect(addr_or_device="aabbccddeeff", password="pass", forceOffline=False)
        with pytest.deprecated_call():
            await casa.reconnect(addr_or_device="AA:BB:CC:DD:EE:FF")


@pytest.mark.asyncio
async def test_casambi_unsupported_protocol_version_raises(dummy_unit):
    from casambi_classic_ble.exceptions import UnsupportedProtocolVersion

    casa = Casambi()
    mock_net = MagicMock(spec=Network)
    mock_net._networkRevision = 1
    mock_net.protocol_version = 11  # Unsupported version >= 10
    mock_net.protocolVersion = 11
    casa._casaNetwork = mock_net

    with pytest.raises(UnsupportedProtocolVersion, match="not supported"):
        await casa._connect_client(addr_or_device="AA:BB:CC:DD:EE:FF")

    with pytest.deprecated_call(), pytest.raises(UnsupportedProtocolVersion, match="not supported"):
        await casa._connectClient(addr_or_device="AA:BB:CC:DD:EE:FF")
