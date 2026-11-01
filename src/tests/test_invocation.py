import logging

from casambi_classic_ble._invocation import parse_invocation_stream


def make_frame(
    *,
    flags: int = 0,
    opcode: int = 1,
    origin: int = 2,
    target: int = 3,
    age: int = 4,
    origin_handle: int | None = None,
    payload: bytes = b"",
) -> bytes:
    actual_flags = flags | (len(payload) & 0x3F)
    if origin_handle is not None:
        actual_flags |= 0x0200
    data = bytearray()
    data.extend(actual_flags.to_bytes(2, "big"))
    data.append(opcode)
    data.extend(origin.to_bytes(2, "big"))
    data.extend(target.to_bytes(2, "big"))
    data.extend(age.to_bytes(2, "big"))
    if origin_handle is not None:
        data.append(origin_handle)
    data.extend(payload)
    return bytes(data)


def test_parse_invocation_stream_single():
    payload = b"\x01\x02\x03"
    raw = make_frame(
        opcode=10,
        origin=100,
        target=200,
        age=5,
        payload=payload,
    )
    frames = parse_invocation_stream(raw)
    assert len(frames) == 1
    f = frames[0]
    assert f.opcode == 10
    assert f.origin == 100
    assert f.target == 200
    assert f.age == 5
    assert f.origin_handle is None
    assert f.payload == payload
    assert f.payload_len == 3
    assert f.offset == 0


def test_parse_invocation_stream_with_origin_handle():
    raw = make_frame(
        opcode=12,
        origin=50,
        target=60,
        age=1,
        origin_handle=99,
        payload=b"abc",
    )
    frames = parse_invocation_stream(raw)
    assert len(frames) == 1
    f = frames[0]
    assert f.origin_handle == 99
    assert f.payload == b"abc"


def test_parse_invocation_stream_multiple():
    f1 = make_frame(opcode=1, origin=10, target=20, payload=b"one")
    f2 = make_frame(opcode=2, origin=11, target=21, payload=b"two")
    frames = parse_invocation_stream(f1 + f2)
    assert len(frames) == 2
    assert frames[0].opcode == 1
    assert frames[1].opcode == 2


def test_parse_invocation_stream_truncated_header():
    frames = parse_invocation_stream(b"\x00\x01\x02")
    assert frames == []


def test_parse_invocation_stream_truncated_origin_handle(caplog):
    # Set flag 0x0200 without providing the byte
    raw = (0x0200).to_bytes(2, "big") + bytes(7)
    with caplog.at_level(logging.ERROR):
        frames = parse_invocation_stream(raw)
    assert frames == []
    assert any("Malformed packet" in rec.getMessage() for rec in caplog.records)
    assert any(raw.hex() in rec.getMessage() for rec in caplog.records)


def test_parse_invocation_stream_truncated_payload(caplog):
    # Set payload len to 10 but provide only 2 bytes
    raw = (10).to_bytes(2, "big") + bytes(7) + b"\x01\x02"
    with caplog.at_level(logging.ERROR):
        frames = parse_invocation_stream(raw)
    assert frames == []
    assert any("Malformed packet" in rec.getMessage() for rec in caplog.records)
    assert any(raw.hex() in rec.getMessage() for rec in caplog.records)


def test_parse_invocation_stream_trailing_bytes():
    f = make_frame(opcode=1, origin=1, target=1, payload=b"")
    raw = f + b"\xff\xff"
    frames = parse_invocation_stream(raw)
    assert len(frames) == 1
