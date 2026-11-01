import pytest

from casambi_classic_ble._unit import (
    ColorSource,
    Group,
    Scene,
    Unit,
    UnitControl,
    UnitControlType,
    UnitState,
    UnitType,
)


def test_unit_control_type_deprecation_and_errors():
    with pytest.deprecated_call():
        t = UnitControlType.UNKOWN
        assert t == UnitControlType.UNKNOWN

    with pytest.raises(AttributeError):
        _ = UnitControlType.NON_EXISTENT_ATTR


def test_unit_type_controls_and_element_names():
    ctrl1 = UnitControl(
        type=UnitControlType.DIMMER,
        offset=0,
        length=8,
        default=0,
        readonly=False,
    )
    ctrl2 = UnitControl(
        type=UnitControlType.UNKNOWN,
        offset=8,
        length=8,
        default=0,
        readonly=False,
    )
    ut = UnitType(
        id=1,
        model="TestModel",
        manufacturer="Casambi",
        mode="Sensor {Presence, Lux}",
        stateLength=2,
        controls=[ctrl1, ctrl2],
    )
    assert ut.get_control(UnitControlType.DIMMER) == ctrl1
    assert ut.get_control(UnitControlType.RGB) is None
    assert ut.element_names == ["Presence", "Lux"]

    # Test mode string with invalid or missing braces
    ut2 = UnitType(
        id=2,
        model="TestModel2",
        manufacturer="Casambi",
        mode="Simple Mode",
        stateLength=1,
        controls=[],
    )
    assert ut2.element_names == []


def test_unit_state_properties_and_range_checks():
    st = UnitState()
    assert st.raw_state is None
    assert st.unknown_controls == []
    assert st.sensors == {}

    # Dimmer
    st.dimmer = 128
    assert st.dimmer == 128
    with pytest.raises(ValueError):
        st.dimmer = 300
    del st.dimmer
    assert st.dimmer is None

    # Vertical
    st.vertical = 64
    assert st.vertical == 64
    with pytest.raises(ValueError):
        st.vertical = -1
    del st.vertical
    assert st.vertical is None

    # RGB
    st.rgb = (10, 20, 30)
    assert st.rgb == (10, 20, 30)
    with pytest.raises(ValueError):
        st.rgb = (10, 300, 30)
    del st.rgb
    assert st.rgb is None
    assert st.hs is None

    # HS roundtrip
    st.rgb = (0, 0, 0)
    assert st.hs == (0.5, 0.0)
    st.hs = (0.2, 0.8)
    assert st.rgb is not None

    # White
    st.white = 200
    assert st.white == 200
    with pytest.raises(ValueError):
        st.white = 500
    del st.white
    assert st.white is None

    # Temperature
    st.temperature = 3000
    assert st.temperature == 3000
    del st.temperature
    assert st.temperature is None

    # ColorSource
    st.colorsource = ColorSource.RGB
    assert st.colorsource == ColorSource.RGB
    del st.colorsource
    assert st.colorsource is None

    # XY
    st.xy = (0.3, 0.4)
    assert st.xy == (0.3, 0.4)
    with pytest.raises(ValueError):
        st.xy = (1.5, 0.4)
    del st.xy
    assert st.xy is None

    # Slider
    st.slider = 50
    assert st.slider == 50
    with pytest.raises(ValueError):
        st.slider = 256
    del st.slider
    assert st.slider is None

    # Onoff
    st.onoff = True
    assert st.onoff is True
    del st.onoff
    assert st.onoff is None

    # White balance
    st.white_balance = 32
    assert st.white_balance == 32
    with pytest.raises(ValueError):
        st.white_balance = 64
    del st.white_balance
    assert st.white_balance is None

    # Presence
    st.presence = 1
    assert st.presence == 1
    with pytest.raises(ValueError):
        st.presence = 5
    del st.presence
    assert st.presence is None

    # Lux
    st.lux = 500
    assert st.lux == 500
    with pytest.raises(ValueError):
        st.lux = 5000
    del st.lux
    assert st.lux is None

    assert "UnitState(" in repr(st)


def test_unit_state_conversions_and_payloads():
    # HS <-> int
    val_hs = UnitState.int_from_hs((0.25, 0.5), length=18)
    hs_out = UnitState.hs_from_int(val_hs, length=18)
    assert abs(hs_out[0] - 0.25) < 0.05
    assert abs(hs_out[1] - 0.5) < 0.05

    # RGB <-> int
    val_rgb = UnitState.int_from_rgb((255, 128, 0), length=24)
    rgb_out = UnitState.rgb_from_int(val_rgb, length=24)
    assert rgb_out[0] == 255
    assert abs(rgb_out[1] - 128) <= 2
    assert rgb_out[2] == 0

    # XY <-> int
    val_xy = UnitState.int_from_xy((0.33, 0.66), length=22)
    xy_out = UnitState.xy_from_int(val_xy, length=22)
    assert abs(xy_out[0] - 0.33) < 0.01
    assert abs(xy_out[1] - 0.66) < 0.01

    # Temperature <-> int
    val_temp = UnitState.int_from_temperature(3000, min_temp=2000, max_temp=6000, length=12)
    temp_out = UnitState.temperature_from_int(val_temp, min_temp=2000, max_temp=6000, length=12)
    assert abs(temp_out - 3000) <= 10

    # Payloads
    assert len(UnitState.payload_from_hs((0.5, 0.5))) == 3
    assert len(UnitState.payload_from_rgb((255, 0, 0))) == 3
    assert len(UnitState.payload_from_xy((0.3, 0.3))) == 3
    assert len(UnitState.payload_from_temperature(4000)) == 1


def test_unit_is_on_and_online():
    ctrl_dim = UnitControl(
        type=UnitControlType.DIMMER, offset=0, length=8, default=0, readonly=False
    )
    ctrl_onoff = UnitControl(
        type=UnitControlType.ONOFF, offset=8, length=1, default=0, readonly=False
    )
    ut = UnitType(
        id=1,
        model="M",
        manufacturer="Casambi",
        mode="Mode",
        stateLength=2,
        controls=[ctrl_dim, ctrl_onoff],
    )
    unit = Unit(
        _typeId=1,
        deviceId=5,
        uuid="uuid-1",
        address="AA:BB:CC:DD:EE:FF",
        name="Light",
        firmwareVersion="1.0",
        unitType=ut,
    )
    assert not unit.is_on
    assert not unit.online

    st = UnitState()
    st.onoff = True
    st.dimmer = 100
    unit._state = st
    unit._on = True
    assert unit.is_on

    st.onoff = False
    assert not unit.is_on

    # Test dimmer without onoff control
    ut_dim_only = UnitType(
        id=2,
        model="M",
        manufacturer="Casambi",
        mode="Mode",
        stateLength=1,
        controls=[ctrl_dim],
    )
    unit2 = Unit(
        _typeId=2,
        deviceId=6,
        uuid="uuid-2",
        address="AA:BB:CC:DD:EE:FF",
        name="Dimmer Only",
        firmwareVersion="1.0",
        unitType=ut_dim_only,
    )
    unit2._state = st
    unit2._on = True
    st.dimmer = 0
    assert not unit2.is_on
    st.dimmer = 50
    assert unit2.is_on


def test_unit_get_state_as_bytes_and_set_state_from_bytes():
    controls = [
        UnitControl(type=UnitControlType.DIMMER, offset=0, length=8, default=0, readonly=False),
        UnitControl(type=UnitControlType.VERTICAL, offset=8, length=8, default=0, readonly=False),
        UnitControl(type=UnitControlType.RGB, offset=16, length=24, default=0, readonly=False),
        UnitControl(type=UnitControlType.WHITE, offset=40, length=8, default=0, readonly=False),
        UnitControl(
            type=UnitControlType.TEMPERATURE,
            offset=48,
            length=12,
            default=0,
            readonly=False,
            min=2000,
            max=6000,
        ),
        UnitControl(
            type=UnitControlType.COLORSOURCE, offset=60, length=4, default=0, readonly=False
        ),
        UnitControl(type=UnitControlType.XY, offset=64, length=22, default=0, readonly=False),
        UnitControl(type=UnitControlType.SLIDER, offset=88, length=8, default=0, readonly=False),
        UnitControl(type=UnitControlType.ONOFF, offset=96, length=1, default=0, readonly=False),
        UnitControl(
            type=UnitControlType.WHITECOLORBALANCE, offset=97, length=6, default=0, readonly=False
        ),
        UnitControl(type=UnitControlType.PRESENCE, offset=104, length=2, default=0, readonly=False),
        UnitControl(type=UnitControlType.LUX, offset=106, length=12, default=0, readonly=False),
        UnitControl(type=UnitControlType.UNKNOWN, offset=120, length=8, default=42, readonly=False),
    ]
    ut = UnitType(
        id=10,
        model="SuperLight",
        manufacturer="Casambi",
        mode="EXT/Elements {CustomSensor}",
        stateLength=16,
        controls=controls,
    )
    unit = Unit(
        _typeId=10,
        deviceId=1,
        uuid="uuid-super",
        address="AA:BB:CC:DD:EE:FF",
        name="SuperLight",
        firmwareVersion="2.0",
        unitType=ut,
        _isClassic=True,
    )

    st = UnitState()
    st.dimmer = 255
    st.vertical = 128
    st.rgb = (255, 0, 128)
    st.white = 200
    st.temperature = 4000
    st.colorsource = ColorSource.RGB
    st.xy = (0.2, 0.4)
    st.slider = 80
    st.onoff = True
    st.white_balance = 30
    st.presence = 1
    st.lux = 1500

    raw = unit.get_state_as_bytes(state=st)
    assert len(raw) == 16

    # Test deprecated alias
    with pytest.deprecated_call():
        raw_deprecated = unit.getStateAsBytes(state=st)
    assert raw_deprecated == raw

    # Now parse it back
    unit.set_state_from_bytes(value=raw)
    assert unit.state is not None
    assert unit.state.dimmer == 255
    assert unit.state.vertical == 128
    assert unit.state.white == 200
    assert abs(unit.state.temperature - 4000) <= 20
    assert unit.state.colorsource == ColorSource.RGB
    assert unit.state.onoff is True
    assert unit.state.white_balance == 30
    assert unit.state.presence == 1
    assert abs(unit.state.lux - 1500) <= 2
    assert "CustomSensor" in unit.state.sensors

    # Test deprecated setStateFromBytes
    with pytest.deprecated_call():
        unit.setStateFromBytes(raw)

    # Test EXT/Elements multiplexed sensor accumulation
    # Packet header: raw[1] bits[7:6] = packet_type, raw[2] = raw_value
    sensor_packet = bytearray(16)
    sensor_packet[1] = 0x80  # packet_type = 2
    sensor_packet[2] = 0x4B  # value = 75
    unit.set_state_from_bytes(value=bytes(sensor_packet))
    assert unit.sensor_cache[2] == 75


def test_group_and_scene():
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="u-1",
        address="AA:BB:CC:DD:EE:FF",
        name="L1",
        firmwareVersion="1.0",
        unitType=UnitType(
            id=1,
            model="M",
            manufacturer="Casambi",
            mode="",
            stateLength=1,
            controls=[],
        ),
    )
    group = Group(group_id=1, name="Kitchen", units=[unit])
    scene = Scene(scene_id=10, name="Dinner")
    assert group.group_id == 1
    assert len(group.units) == 1
    assert scene.scene_id == 10

    # Deprecated properties and constructor kwargs emit warnings
    with pytest.deprecated_call():
        assert group.groudId == 1
    with pytest.deprecated_call():
        assert group.groupId == 1
    with pytest.deprecated_call():
        assert scene.sceneId == 10
    with pytest.deprecated_call():
        g_legacy = Group(groudId=1, name="Kitchen", units=[unit])
        assert g_legacy.group_id == 1
    with pytest.deprecated_call():
        s_legacy = Scene(sceneId=10, name="Dinner")
        assert s_legacy.scene_id == 10
