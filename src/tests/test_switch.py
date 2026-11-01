from casambi_classic_ble._switch import ButtonEventType, SwitchEventDecoder
from tests.test_invocation import make_frame


def test_switch_decoder_button_stream_press_and_release():
    decoder = SwitchEventDecoder()
    unit_id = 7
    target = (unit_id << 8) | 0x06  # button stream

    # Press: opcode 29 (button 1), origin & 0x02 == 0
    f_press = make_frame(opcode=29, origin=0x0100, target=target, payload=b"")
    events = decoder.decode(data=f_press, packet_seq=1)
    assert len(events) == 1
    ev = events[0]
    assert ev.unit_id == unit_id
    assert ev.button == 1
    assert ev.button_event_index == 0
    assert ev.event == ButtonEventType.PRESS
    assert ev.target_type == 0x06

    # Retransmission of press (same unit, button, origin) within window should be suppressed
    events_retransmit = decoder.decode(data=f_press, packet_seq=2)
    assert len(events_retransmit) == 0

    # Release: opcode 29, origin & 0x02 != 0
    f_release = make_frame(opcode=29, origin=0x0102, target=target, payload=b"")
    events_rel = decoder.decode(data=f_release, packet_seq=3)
    assert len(events_rel) == 1
    assert events_rel[0].event == ButtonEventType.RELEASE


def test_switch_decoder_input_stream():
    decoder = SwitchEventDecoder()
    unit_id = 12
    target = (unit_id << 8) | 0x12  # input stream

    # 1. Empty payload is skipped
    f_empty = make_frame(opcode=64, origin=1, target=target, payload=b"")
    assert decoder.decode(data=f_empty, packet_seq=1) == []

    # 2. PRESS (0x01) and RELEASE (0x02) from 0x12 stream are ignored
    f_press = make_frame(opcode=64, origin=2, target=target, payload=b"\x01extra")
    assert decoder.decode(data=f_press, packet_seq=2) == []

    f_rel = make_frame(opcode=64, origin=3, target=target, payload=b"\x02extra")
    assert decoder.decode(data=f_rel, packet_seq=3) == []

    # 3. HOLD (0x09) is accepted
    f_hold = make_frame(opcode=64, origin=4, target=target, payload=b"\x09\xaa\xbb")
    events = decoder.decode(data=f_hold, packet_seq=4)
    assert len(events) == 1
    assert events[0].event == ButtonEventType.HOLD
    assert events[0].button == 1
    assert events[0].extra_data == b"\xaa\xbb"

    # Retransmit of hold is suppressed
    assert decoder.decode(data=f_hold, packet_seq=5) == []

    # 4. RELEASE_AFTER_HOLD (0x0C)
    f_rah = make_frame(opcode=64, origin=5, target=target, payload=b"\x0c")
    events_rah = decoder.decode(data=f_rah, packet_seq=6)
    assert len(events_rah) == 1
    assert events_rah[0].event == ButtonEventType.RELEASE_AFTER_HOLD

    # 5. Unknown event code in input stream
    f_unk = make_frame(opcode=64, origin=6, target=target, payload=b"\xff\x11")
    events_unk = decoder.decode(data=f_unk, packet_seq=7)
    assert len(events_unk) == 1
    assert events_unk[0].event == ButtonEventType.UNKNOWN


def test_switch_decoder_unrelated_target_and_reset():
    decoder = SwitchEventDecoder()
    # Unrelated target type 0x05
    f_other = make_frame(opcode=10, origin=1, target=(1 << 8) | 0x05, payload=b"")
    assert decoder.decode(data=f_other, packet_seq=1) == []

    # Test reset clears cache so retransmit is accepted
    target = (1 << 8) | 0x06
    f_press = make_frame(opcode=29, origin=10, target=target, payload=b"")
    ev1 = decoder.decode(data=f_press, packet_seq=2)
    assert len(ev1) == 1
    # Without reset, duplicate is suppressed
    assert decoder.decode(data=f_press, packet_seq=3) == []
    # After reset, duplicate is accepted
    decoder.reset()
    ev2 = decoder.decode(data=f_press, packet_seq=4)
    assert len(ev2) == 1


def test_switch_decoder_counter_wraparound_and_out_of_order():
    """P1.6: SwitchEventDecoder handles 16-bit origin wraparound, out-of-order frames, and expiry."""
    from unittest.mock import patch

    decoder = SwitchEventDecoder()
    unit_id = 3
    target = (unit_id << 8) | 0x06

    # 1. Origin at 16-bit wraparound boundary: 0xFFFC (PRESS) -> 0xFFFE (RELEASE) -> 0x0000 (PRESS)
    f_press_max = make_frame(opcode=29, origin=0xFFFC, target=target, payload=b"")
    f_rel_max = make_frame(opcode=29, origin=0xFFFE, target=target, payload=b"")
    f_press_wrap = make_frame(opcode=29, origin=0x0000, target=target, payload=b"")

    assert len(decoder.decode(data=f_press_max, packet_seq=1)) == 1
    assert len(decoder.decode(data=f_rel_max, packet_seq=2)) == 1
    ev_wrap = decoder.decode(data=f_press_wrap, packet_seq=3)
    assert len(ev_wrap) == 1
    assert ev_wrap[0].event == ButtonEventType.PRESS

    # 2. Out-of-order retransmit of 0xFFFC after 0x0000 was already accepted is still suppressed within window
    assert decoder.decode(data=f_press_max, packet_seq=4) == []

    # 3. After _DEDUP_WINDOW_SECONDS (0.5s), expired origins are pruned and accepted again
    with patch("casambi_classic_ble._switch.monotonic", return_value=1e9):
        ev_after_expiry = decoder.decode(data=f_press_max, packet_seq=5)
        assert len(ev_after_expiry) == 1
        assert len(decoder._seen_origins) == 1
