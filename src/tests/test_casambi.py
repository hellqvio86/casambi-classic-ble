from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from casambi_classic_ble._casambi import Casambi
from casambi_classic_ble._client import (
    CasambiClientClassic,
    ConnectionState,
)
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
from casambi_classic_ble.errors import ConnectionStateError


@pytest.fixture
def dummy_unit_type():
    return UnitType(
        id=1,
        model="TestModel",
        manufacturer="Casambi",
        mode="Dimmer Mode",
        stateLength=4,
        controls=[
            UnitControl(type=UnitControlType.DIMMER, offset=0, length=8, default=0, readonly=False),
            UnitControl(
                type=UnitControlType.WHITECOLORBALANCE,
                offset=8,
                length=6,
                default=0,
                readonly=False,
            ),
            UnitControl(type=UnitControlType.XY, offset=14, length=18, default=0, readonly=False),
        ],
    )


@pytest.fixture
def dummy_unit(dummy_unit_type):
    return Unit(
        _typeId=1,
        deviceId=1,
        uuid="unit-uuid-1",
        address="AA:BB:CC:DD:EE:01",
        name="Ceiling Light",
        firmwareVersion="1.0",
        unitType=dummy_unit_type,
    )


@pytest.fixture
def mock_casambi(dummy_unit):
    casa = Casambi()
    # Mock network
    mock_net = MagicMock(spec=Network)
    mock_net._networkRevision = 1
    mock_net._networkName = "MyNetwork"
    mock_net._id = "net-id-123"
    mock_net.units = [dummy_unit]
    mock_net.groups = [Group(groudId=1, name="Kitchen", units=[dummy_unit])]
    mock_net.scenes = [Scene(sceneId=10, name="Dinner")]
    mock_net.protocolVersion = 1  # classic
    casa._casaNetwork = mock_net

    # Mock client
    mock_client = AsyncMock(spec=CasambiClientClassic)
    mock_client._connectionState = ConnectionState.AUTHENTICATED
    mock_client._address_or_devive = "AA:BB:CC:DD:EE:FF"
    casa._casaClient = mock_client
    casa._opContext = OperationsContextClassic()
    return casa


def test_casambi_properties_unconnected():
    casa = Casambi()
    with pytest.raises(ConnectionStateError):
        _ = casa.networkName
    with pytest.raises(ConnectionStateError):
        _ = casa.networkId
    with pytest.raises(ConnectionStateError):
        _ = casa.units
    with pytest.raises(ConnectionStateError):
        _ = casa.groups
    with pytest.raises(ConnectionStateError):
        _ = casa.scenes
    assert not casa.connected


def test_casambi_properties_connected(mock_casambi):
    assert mock_casambi.networkName == "MyNetwork"
    assert mock_casambi.networkId == "net-id-123"
    assert len(mock_casambi.units) == 1
    assert len(mock_casambi.groups) == 1
    assert len(mock_casambi.scenes) == 1
    assert mock_casambi.connected


@pytest.mark.asyncio
async def test_casambi_control_methods(mock_casambi, dummy_unit):
    # setLevel
    await mock_casambi.setLevel(target=dummy_unit, level=128)
    mock_casambi._casaClient.send.assert_called()

    with pytest.raises(ValueError):
        await mock_casambi.setLevel(target=dummy_unit, level=-1)
    with pytest.raises(ValueError):
        await mock_casambi.setLevel(target=dummy_unit, level=256)

    # setVertical
    await mock_casambi.setVertical(target=dummy_unit, vertical=64)
    with pytest.raises(ValueError):
        await mock_casambi.setVertical(target=dummy_unit, vertical=300)

    # setWhite
    await mock_casambi.setWhite(target=dummy_unit, level=100)
    with pytest.raises(ValueError):
        await mock_casambi.setWhite(target=dummy_unit, level=300)

    # setColor
    await mock_casambi.setColor(target=dummy_unit, rgbColor=(255, 0, 0))

    # setTemperature
    await mock_casambi.setTemperature(target=dummy_unit, temperature=3000)

    # For Evolution-only operations: SetSlider, SetColorXY
    from casambi_classic_ble._operation import OperationsContextEvolution

    mock_casambi._opContext = OperationsContextEvolution()

    # setSlider
    await mock_casambi.setSlider(target=dummy_unit, value=50)
    with pytest.raises(ValueError):
        await mock_casambi.setSlider(target=dummy_unit, value=300)

    # setColorXY
    await mock_casambi.setColorXY(target=dummy_unit, xyColor=(0.4, 0.4))
    with pytest.raises(ValueError):
        await mock_casambi.setColorXY(target=dummy_unit, xyColor=(1.5, 0.4))

    # Reset back to classic
    mock_casambi._opContext = OperationsContextClassic()

    # turnOn & turnOff
    await mock_casambi.turnOn(target=dummy_unit)
    await mock_casambi.turnOff(target=dummy_unit)

    # switchToScene
    scene = mock_casambi.scenes[0]
    await mock_casambi.switchToScene(target=scene, level=200)

    # setControlValue and setWhiteColorBalance use OpCode.SetState (Evolution)
    mock_casambi._opContext = OperationsContextEvolution()

    # setControlValue
    ctrl = dummy_unit.unitType.controls[0]
    await mock_casambi.setControlValue(unit=dummy_unit, control=ctrl, value=255)

    # setWhiteColorBalance
    await mock_casambi.setWhiteColorBalance(unit=dummy_unit, value=30)
    with pytest.raises(ValueError):
        await mock_casambi.setWhiteColorBalance(unit=dummy_unit, value=100)


@pytest.mark.asyncio
async def test_casambi_set_unit_state(mock_casambi, dummy_unit):
    st = UnitState()
    st.dimmer = 150
    await mock_casambi.setUnitState(target=dummy_unit, state=st)
    mock_casambi._casaClient.send.assert_called()


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

    mock_casambi.registerUnitChangedHandler(handler=on_unit_changed)
    mock_casambi.registerSwitchEventHandler(handler=on_switch_event)
    mock_casambi.registerDisconnectCallback(callback=on_disconnect)

    # Data callback: UnitState
    mock_casambi._dataCallback(
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
    mock_casambi._dataCallback(packetType=IncomingPacketType.SwitchEvent, data=sw)
    assert len(switch_events) == 1

    # Disconnect callback
    mock_casambi._disconnectCallback()
    assert len(disconnect_events) == 1
    assert dummy_unit.online is False

    # Unregister
    mock_casambi.unregisterUnitChangedHandler(handler=on_unit_changed)
    mock_casambi.unregisterSwitchEventHandler(handler=on_switch_event)
    mock_casambi.unregisterDisconnectCallback(callback=on_disconnect)


@pytest.mark.asyncio
async def test_casambi_disconnect_and_cache(mock_casambi, tmp_path):
    mock_casambi._ownHttpClient = True
    mock_casambi._httpClient = AsyncMock()

    await mock_casambi.disconnect()
    mock_casambi._casaClient.disconnect.assert_called_once()
    assert mock_casambi._casaNetwork is None

    # Test cache invalidation
    casa = Casambi(cachePath=tmp_path)
    await casa.invalidateCache(uuid="aabbccddeeff")


@pytest.mark.asyncio
async def test_casambi_connect_and_reconnect():
    casa = Casambi()
    mock_net = AsyncMock(spec=Network)
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
        await casa.connect(addr_or_device="aabbccddeeff", password="pass", forceOffline=False)
        mock_net.load.assert_called_once()
        mock_net.logIn.assert_called_once_with("pass", False)
        mock_net.update.assert_called_once_with(False)
        mock_client.connect.assert_called_once()
        mock_client.exchangeKey.assert_called_once()
        mock_client.authenticate.assert_called_once()

        # Reconnect when already connected does nothing
        await casa.reconnect(addr_or_device="AA:BB:CC:DD:EE:FF")

        # Reconnect when not connected
        mock_client._connectionState = ConnectionState.CONNECTED
        await casa.reconnect(addr_or_device="AA:BB:CC:DD:EE:FF")
        mock_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_casambi_evolution_turn_on_off(dummy_unit):
    from casambi_classic_ble._operation import OperationsContextEvolution

    casa = Casambi()
    mock_net = MagicMock(spec=Network)
    mock_net._networkRevision = 1
    mock_net.protocolVersion = 11  # Evolution
    casa._casaNetwork = mock_net
    mock_client = AsyncMock()
    mock_client._connectionState = ConnectionState.AUTHENTICATED
    casa._casaClient = mock_client
    casa._opContext = OperationsContextEvolution()

    # Unit with ONOFF control
    onoff_ctrl = UnitControl(
        type=UnitControlType.ONOFF, offset=0, length=1, default=0, readonly=False
    )
    dummy_unit.unitType.controls.append(onoff_ctrl)

    await casa.turnOn(target=dummy_unit)
    await casa.turnOff(target=dummy_unit)
    assert mock_client.send.call_count == 2
