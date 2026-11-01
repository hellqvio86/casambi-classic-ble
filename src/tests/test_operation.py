from typing import Any

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


@pytest.mark.parametrize(
    "unsupported_op",
    [
        OpCode.SetTemperature,
        OpCode.SetColor,
        OpCode.SetVertical,
        OpCode.SetWhite,
    ],
)
def test_classic_prepare_operation_unsupported_target_type_for_opcode(
    unsupported_op: OpCode,
) -> None:
    """P1.7: Scene target is only supported for SetLevel; other opcodes fail with ValueError."""
    ctx = OperationsContextClassic()
    scene = create_mock_scene(scene_id=1)
    with pytest.raises(ValueError, match="Target type Scene is not supported"):
        ctx.prepare_operation(op=unsupported_op, target=scene, payload=b"\x01")


@pytest.mark.parametrize("invalid_id", [-1, 256, 65535])
def test_classic_prepare_operation_invalid_target_id_bounds(invalid_id: int) -> None:
    """P1.7: Out-of-range unit/group/scene IDs (< 0 or > 255) fail before packing."""
    ctx = OperationsContextClassic()
    bad_unit = create_mock_unit(unit_id=invalid_id)
    with pytest.raises(ValueError, match="Target ID must be between 0 and 255"):
        ctx.prepare_operation(op=OpCode.SetLevel, target=bad_unit, payload=b"\x80")

    bad_group = create_mock_group(group_id=invalid_id)
    with pytest.raises(ValueError, match="Target ID must be between 0 and 255"):
        ctx.prepare_operation(op=OpCode.SetLevel, target=bad_group, payload=b"\x80")

    bad_scene = create_mock_scene(scene_id=invalid_id)
    with pytest.raises(ValueError, match="Target ID must be between 0 and 255"):
        ctx.prepare_operation(op=OpCode.SetLevel, target=bad_scene, payload=b"\x80")


def test_classic_session_operations_match_golden_vectors(
    golden_vectors: dict[str, Any],
) -> None:
    """P1.7: Verify all Classic session operation combinations against golden vectors."""
    for vec in golden_vectors["classic_session_operations"]:
        assert "provenance" in vec
        ctx = OperationsContextClassic()
        op = OpCode[vec["opcode_name"]]
        target_type = vec["target_type"]
        target: Unit | Group | Scene | None = None
        if target_type == "None":
            target = None
        elif target_type == "Unit":
            target = create_mock_unit(unit_id=vec["target_id"])
        elif target_type == "Group":
            target = create_mock_group(group_id=vec["target_id"])
        elif target_type == "Scene":
            target = create_mock_scene(scene_id=vec["target_id"])
        else:
            pytest.fail(f"Unknown target_type: {target_type}")

        payload = bytes.fromhex(vec["payload_hex"])
        frame = ctx.prepare_operation(op=op, target=target, payload=payload)
        assert frame.hex() == vec["expected_frame_hex"], f"Mismatch for {vec['name']}"
