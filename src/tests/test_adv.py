"""Unit tests for _adv module (internal address extraction and matching)."""

import pytest

from casambi_classic_ble._adv import (
    CASAMBI_MANUFACTURER_ID,
    _internal_address,
    matches_advertisement_address,
    normalize_mac_address,
    parse_advertisement,
)


def test_internal_address_extraction() -> None:
    """T-004: Extracts forward and reversed MAC addresses from manufacturer data."""
    # 6 bytes MAC
    mfr_data = bytes.fromhex("11223344556601020304")
    fwd, rev = _internal_address(mfr_data=mfr_data)
    assert fwd == "11:22:33:44:55:66"
    assert rev == "66:55:44:33:22:11"


def test_internal_address_too_short_raises_value_error() -> None:
    """_internal_address requires at least 6 bytes."""
    with pytest.raises(ValueError, match="at least 6 bytes"):
        _internal_address(mfr_data=b"\x01\x02\x03\x04\x05")


def test_normalize_mac_address() -> None:
    """Normalizes MAC addresses in various formats or rejects invalid inputs."""
    assert normalize_mac_address(address="aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac_address(address="AA:BB:CC:DD:EE:FF") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac_address(address="aabbccddeeff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac_address(address="AA-BB-CC-DD-EE-FF") == "AA:BB:CC:DD:EE:FF"

    # Invalid formats
    assert normalize_mac_address(address="66") is None
    assert normalize_mac_address(address="AA:BB:CC") is None
    assert normalize_mac_address(address="AA:BB:CC:DD:EE:123") is None
    assert normalize_mac_address(address="AA:BB:CC:DD:EE:") is None
    assert normalize_mac_address(address="-1:BB:CC:DD:EE:FF") is None
    assert normalize_mac_address(address="AA-BB-CC-DD-EE") is None
    assert normalize_mac_address(address="GG:GG:GG:GG:GG:GG") is None
    assert normalize_mac_address(address="GGGGGGGGGGGG") is None
    assert normalize_mac_address(address="not_hex_digits") is None
    assert normalize_mac_address(address="12345678-1234-1234-1234-123456789ABC") is None
    assert normalize_mac_address(address=None) is None  # type: ignore[arg-type]


def test_matches_advertisement_address_both_orders() -> None:
    """T-004: Both golden advertisements (forward and reversed) match exact MAC."""
    beacon = bytes.fromhex("11223344556601020304")

    # Reversed order match (Classic convention)
    assert (
        matches_advertisement_address(target_address="66:55:44:33:22:11", mfr_data=beacon) is True
    )
    assert (
        matches_advertisement_address(
            target_address="66:55:44:33:22:11", mfr_data=beacon, allow_forward=False
        )
        is True
    )

    # Forward order match (allowed by default, rejected when allow_forward=False)
    assert (
        matches_advertisement_address(target_address="11:22:33:44:55:66", mfr_data=beacon) is True
    )
    assert (
        matches_advertisement_address(
            target_address="11:22:33:44:55:66", mfr_data=beacon, allow_forward=False
        )
        is False
    )

    # Substring must NOT match
    assert matches_advertisement_address(target_address="66", mfr_data=beacon) is False
    assert matches_advertisement_address(target_address="11:22:33", mfr_data=beacon) is False

    # Different MAC must NOT match
    assert (
        matches_advertisement_address(target_address="AA:BB:CC:DD:EE:FF", mfr_data=beacon) is False
    )

    # Truncated mfr_data
    assert (
        matches_advertisement_address(target_address="66:55:44:33:22:11", mfr_data=b"\x11\x22")
        is False
    )


def test_parse_advertisement_separates_verified_and_unverified_fields() -> None:
    """P1.6: parse_advertisement separates verified state from unverified status/trailing flags."""
    # 10-byte frame: MAC 11..66 (rev 66:55:44:33:22:11), status 0xFE (OFF, flags=0x7F), level 0x80 (50%), trailing 0x0304
    raw = bytes.fromhex("112233445566fe800304")
    parsed = parse_advertisement(mfr_data=raw, company_id=CASAMBI_MANUFACTURER_ID)
    assert parsed is not None
    assert parsed.company_id == 963
    assert parsed.forward_mac == "11:22:33:44:55:66"
    assert parsed.reversed_mac == "66:55:44:33:22:11"
    assert parsed.address_byte == 0x11
    assert parsed.is_on is False
    assert parsed.level_byte == 0x80
    assert parsed.dim_level == 0.502
    assert parsed.level_percent == 50
    assert parsed.raw_status_byte == 0xFE
    assert parsed.unverified_status_flags == 0x7F
    assert parsed.unverified_trailing_bytes == b"\x03\x04"

    status_dict = parsed.to_status_dict()
    assert status_dict["on"] is False
    assert status_dict["dimLevel"] == 0.502
    assert status_dict["level_percent"] == 50
    assert status_dict["unverified"] == {
        "raw_status_byte": 0xFE,
        "status_flags": 0x7F,
        "trailing_hex": "0304",
    }

    # Unknown manufacturer ID returns None
    assert parse_advertisement(mfr_data=raw, company_id=0x004C) is None
    # Truncated (< 8 bytes) returns None
    assert parse_advertisement(mfr_data=raw[:7], company_id=CASAMBI_MANUFACTURER_ID) is None
