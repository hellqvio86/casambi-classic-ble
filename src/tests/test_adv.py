"""Unit tests for _adv module (internal address extraction and matching)."""

import pytest

from casambi_classic_ble._adv import (
    _internal_address,
    matches_advertisement_address,
    normalize_mac_address,
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

    # Forward order match
    assert (
        matches_advertisement_address(target_address="11:22:33:44:55:66", mfr_data=beacon) is True
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
