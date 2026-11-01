"""Fuzz and edge-case unit tests for Casambi advertisement and status parsers.

Ensures that hostile, malformed, truncated, or random BLE frames never raise
unexpected exceptions (such as IndexError, ValueError, struct.error).
"""

from __future__ import annotations

import random
from typing import Any
from unittest.mock import MagicMock

import pytest

from casambi_classic_ble.device import CasambiDevice


@pytest.fixture
def mock_device() -> CasambiDevice:
    """Fixture providing a CasambiDevice with standardized mock address."""
    return CasambiDevice(address="AA:BB:CC:DD:EE:FF", name="Test Light")


@pytest.mark.parametrize(
    "truncated_payload",
    [
        b"",
        b"\xaa",
        b"\xaa\xbb",
        b"\xaa\xbb\xcc",
        b"\xaa\xbb\xcc\xdd",
        b"\xaa\xbb\xcc\xdd\xee",
        b"\xaa\xbb\xcc\xdd\xee\xff",
        b"\xaa\xbb\xcc\xdd\xee\xff\x01",  # 7 bytes, 1 short of required 8
    ],
)
def test_advertisement_truncated_payloads_return_none(
    mock_device: CasambiDevice, truncated_payload: bytes
) -> None:
    """Truncated advertisement data should safely return None without raising."""
    result = mock_device.update_from_advertisement(mfr_data=truncated_payload)
    assert result is None


@pytest.mark.parametrize(
    "invalid_input",
    [
        None,
        "not_bytes",
        12345,
        [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x01, 0xFF],
        {"data": b"\xaa\xbb\xcc\xdd\xee\xff\x01\xff"},
    ],
)
def test_advertisement_invalid_types_return_none(
    mock_device: CasambiDevice, invalid_input: Any
) -> None:
    """Non-bytes inputs must be rejected gracefully with None."""
    result = mock_device.update_from_advertisement(mfr_data=invalid_input)
    assert result is None


def test_advertisement_unmatched_address_returns_none(mock_device: CasambiDevice) -> None:
    """Payloads addressed to a different BLE node must be ignored."""
    unmatched_payload = bytes.fromhex("11223344556601ff")
    result = mock_device.update_from_advertisement(mfr_data=unmatched_payload)
    assert result is None


def test_advertisement_short_or_partial_address_does_not_match() -> None:
    """T-004: Partial or substring MAC addresses must not match beacons (no substring in)."""
    # Previously address="66" matched beacon 112233445566...
    short_device = CasambiDevice(address="66", name="Short Address Device")
    beacon = bytes.fromhex("11223344556601ff")
    assert short_device.update_from_advertisement(mfr_data=beacon) is None

    partial_device = CasambiDevice(address="AA:BB:CC", name="Partial Device")
    beacon_aabb = bytes.fromhex("aabbccddeeff0180")
    assert partial_device.update_from_advertisement(mfr_data=beacon_aabb) is None


def test_advertisement_uuid_style_address_with_ble_device_source_works() -> None:
    """T-004: UUID-style address (macOS CoreBluetooth) with a BLEDevice source works."""
    from bleak.backends.device import BLEDevice

    uuid_str = "12345678-1234-1234-1234-123456789ABC"
    ble_dev = BLEDevice(address=uuid_str, name="macOS Casambi Node", details=None)
    dev = CasambiDevice(address=ble_dev, name="macOS Casambi Node")

    beacon = bytes.fromhex("aabbccddeeff0180")
    # Passing ble_device matches the source directly
    result = dev.update_from_advertisement(mfr_data=beacon, ble_device=ble_dev)
    assert result is not None
    assert result["on"] is True
    assert result["level_percent"] == 50
    # No pseudo 'id' in status (T-004)
    assert "id" not in result
    assert result.get("address_byte") == 0xAA

    # Subsequent advertisement without ble_device matches via cached internal address
    result2 = dev.update_from_advertisement(mfr_data=beacon)
    assert result2 is not None
    assert result2["on"] is True


def test_advertisement_no_pseudo_id_in_status(mock_device: CasambiDevice) -> None:
    """T-004: Verify status does not present manufacturer address byte as unit 'id'."""
    beacon = bytes.fromhex("aabbccddeeff0180")
    status = mock_device.update_from_advertisement(mfr_data=beacon)
    assert status is not None
    assert "id" not in status
    assert status["address_byte"] == 0xAA


def test_advertisement_valid_payload_parsing(mock_device: CasambiDevice) -> None:
    """Valid matching payload correctly parses state and level."""
    # Matches AA:BB:CC:DD:EE:FF, flags 0x01 (ON), level 0x80 (128 / 255 = 50%)
    valid_payload = bytes.fromhex("aabbccddeeff0180")
    result = mock_device.update_from_advertisement(mfr_data=valid_payload)
    assert result is not None
    assert result["on"] is True
    assert result["level_percent"] == 50
    assert result["source"] == "passive_adv"


def test_advertisement_reversed_address_parsing(mock_device: CasambiDevice) -> None:
    """Some Classic beacons carry reversed byte order addresses."""
    # Reversed AA:BB:CC:DD:EE:FF -> FF:EE:DD:CC:BB:AA
    reversed_payload = bytes.fromhex("ffeeddccbbaa0040")
    result = mock_device.update_from_advertisement(mfr_data=reversed_payload)
    assert result is not None
    assert result["on"] is False
    assert result["level_percent"] == 25


def test_advertisement_oversized_payload_handling(mock_device: CasambiDevice) -> None:
    """Oversized payloads beyond 8 bytes parse the header and ignore trailing bytes."""
    oversized = bytes.fromhex("aabbccddeeff01ff") + (b"\x00" * 500)
    result = mock_device.update_from_advertisement(mfr_data=oversized)
    assert result is not None
    assert result["on"] is True
    assert result["level_percent"] == 100


def test_advertisement_callback_exception_isolation(mock_device: CasambiDevice) -> None:
    """Faulty external subscriber callbacks must never raise out of the parser."""
    failing_cb = MagicMock(side_effect=RuntimeError("Subscriber crash"))
    mock_device.set_notification_callback(callback=failing_cb)

    valid_payload = bytes.fromhex("aabbccddeeff0180")
    result = mock_device.update_from_advertisement(mfr_data=valid_payload)
    assert result is not None
    assert failing_cb.called


def test_advertisement_fuzz_random_bytes(mock_device: CasambiDevice) -> None:
    """Fuzz testing with 500 pseudorandom payloads (fixed seed for deterministic CI)."""
    rng = random.Random(42)

    for _ in range(500):
        length = rng.randint(0, 128)
        payload = bytes(rng.getrandbits(8) for _ in range(length))
        # Should either return a parsed dict or None, but NEVER raise an exception
        result = mock_device.update_from_advertisement(mfr_data=payload)
        assert result is None or isinstance(result, dict)


@pytest.mark.parametrize(
    "truncated_status",
    [
        b"",
        b"\x01",
        b"\x01\x02",
    ],
)
def test_parse_status_truncated_returns_empty_dict(
    mock_device: CasambiDevice, truncated_status: bytes
) -> None:
    """Status notification payloads < 3 bytes return an empty dictionary."""
    assert mock_device.parse_status(data=truncated_status) == {}


def test_parse_status_fuzz_random_bytes(mock_device: CasambiDevice) -> None:
    """Fuzz parse_status with 500 random frames."""
    rng = random.Random(1337)

    for _ in range(500):
        length = rng.randint(0, 64)
        payload = bytes(rng.getrandbits(8) for _ in range(length))
        status = mock_device.parse_status(data=payload)
        assert isinstance(status, dict)
        if length >= 3 and payload[0] == 0x03:
            assert "opcode" in status
            assert "id" in status
            assert "dimLevel" in status
        else:
            assert status == {}


def test_parse_status_unknown_opcodes_return_empty_dict(mock_device: CasambiDevice) -> None:
    """T-003: Non-0x03 opcodes (e.g. 0x07 auth, 0x01 turn_on, random) must return {}."""
    assert mock_device.parse_status(data=bytes([0x07, 0x01, 0x80])) == {}
    assert mock_device.parse_status(data=bytes([0x01, 0x01, 0x80])) == {}
    assert mock_device.parse_status(data=bytes([0x02, 0x01, 0x80])) == {}
    assert mock_device.parse_status(data=bytes([0x10, 0x01, 0x80])) == {}
    assert mock_device.parse_status(data=bytes([0xFF, 0x01, 0x80])) == {}

    # Verified opcode 0x03 parses successfully
    status_03 = mock_device.parse_status(data=bytes([0x03, 0x01, 0x80]))
    assert status_03["opcode"] == "0x03"
    assert status_03["id"] == 1
    assert status_03["on"] is True
