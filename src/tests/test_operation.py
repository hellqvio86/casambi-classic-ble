import pytest

from casambi_classic_ble._operation import (
    OpCode,
    OperationsContextClassic,
)
from casambi_classic_ble._unit import Group, Scene, Unit, UnitType


def create_mock_unit(unit_id: int = 1) -> Unit:
    return Unit(
        _typeId=1,
        deviceId=unit_id,
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        address="AA:BB:CC:DD:EE:FF",
        name="Test Unit",
        firmwareVersion="1.0",
        unitType=UnitType(
            id=1,
            model="TestModel",
            manufacturer="Casambi",
            mode="Dimmer",
            stateLength=1,
            controls=[],
        ),
    )


def create_mock_group(group_id: int = 2) -> Group:
    return Group(group_id=group_id, name="Test Group", units=[])


def create_mock_scene(scene_id: int = 3) -> Scene:
    return Scene(scene_id=scene_id, name="Test Scene")


def test_classic_prepare_operation_broadcast():
    ctx = OperationsContextClassic()
    pkt = ctx.prepare_operation(op=OpCode.SetLevel, target=None, payload=b"\xff")
    assert isinstance(pkt, bytes)
    assert len(pkt) > 0

    # Deprecated prepareOperation alias emits DeprecationWarning
    ctx_deprecated = OperationsContextClassic()
    with pytest.deprecated_call():
        pkt_deprecated = ctx_deprecated.prepareOperation(
            op=OpCode.SetLevel, target=None, payload=b"\xff"
        )
        assert pkt_deprecated == pkt


def test_classic_prepare_operation_unit():
    ctx = OperationsContextClassic()
    unit = create_mock_unit(unit_id=5)
    pkt = ctx.prepare_operation(op=OpCode.SetLevel, target=unit, payload=b"\x80")
    assert isinstance(pkt, bytes)
    # Check that unit id is in packet
    assert 5 in pkt


def test_classic_prepare_operation_group():
    ctx = OperationsContextClassic()
    group = create_mock_group(group_id=10)
    pkt = ctx.prepare_operation(op=OpCode.SetLevel, target=group, payload=b"\x40")
    assert isinstance(pkt, bytes)
    assert 10 in pkt


def test_classic_prepare_operation_scene():
    ctx = OperationsContextClassic()
    scene = create_mock_scene(scene_id=12)
    pkt = ctx.prepare_operation(op=OpCode.SetLevel, target=scene, payload=b"\x00")
    assert isinstance(pkt, bytes)
    assert 12 in pkt


def test_classic_prepare_operation_payload_too_long():
    ctx = OperationsContextClassic()
    with pytest.raises(ValueError, match="Payload too long"):
        ctx.prepare_operation(op=OpCode.SetLevel, target=None, payload=b"0" * 17)


def test_classic_prepare_operation_origin_rollover():
    ctx = OperationsContextClassic()
    ctx._origin = 256
    pkt = ctx.prepare_operation(op=OpCode.SetLevel, target=None, payload=b"\x01")
    assert isinstance(pkt, bytes)
    assert ctx._origin == 2  # Rolled over to 1 and incremented to 2


def test_classic_prepare_operation_unsupported_opcode():
    ctx = OperationsContextClassic()
    with pytest.raises(ValueError, match="not supported on Classic networks"):
        ctx.prepare_operation(op=OpCode.SetSlider, target=None, payload=b"\x01")
