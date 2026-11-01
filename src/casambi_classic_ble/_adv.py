"""Advertisement and beacon parsing helpers for Casambi Classic."""

import logging
from dataclasses import dataclass
from typing import Any, Final

logger = logging.getLogger(__name__)

CASAMBI_MANUFACTURER_ID: Final[int] = 0x03C3  # Decimal 963
MIN_ADVERTISEMENT_BYTES: Final[int] = 8
_HEX_CHARS: Final[frozenset[str]] = frozenset("0123456789abcdefABCDEF")


@dataclass(frozen=True, slots=True)
class ParsedAdvertisement:
    """Structured representation of a Casambi Classic BLE manufacturer advertisement.

    Separates verified protocol fields (MAC address bytes 0..5, power bit 0 of byte 6,
    and dimmer level byte 7) from unverified/inferred flags (bits 1..7 of byte 6 and
    trailing bytes 8..N).
    """

    company_id: int
    forward_mac: str
    reversed_mac: str
    address_byte: int
    is_on: bool
    level_byte: int
    dim_level: float
    level_percent: int
    raw_status_byte: int
    unverified_status_flags: int
    unverified_trailing_bytes: bytes

    def to_status_dict(self) -> dict[str, Any]:
        """Convert parsed advertisement into a public device status dictionary."""
        return {
            "on": self.is_on,
            "dimLevel": self.dim_level,
            "level_percent": self.level_percent,
            "source": "passive_adv",
            "address_byte": self.address_byte,
            "unverified": {
                "raw_status_byte": self.raw_status_byte,
                "status_flags": self.unverified_status_flags,
                "trailing_hex": self.unverified_trailing_bytes.hex(),
            },
        }


def _internal_address(*, mfr_data: bytes | bytearray) -> tuple[str, str]:
    """
    Extract forward and reversed MAC addresses from manufacturer beacon data.

    Classic Casambi nodes broadcast manufacturer beacons (0x03C3) with the device MAC
    address in reversed byte order (quirk #1).

    Args:
        mfr_data: Raw manufacturer data (at least 6 bytes).

    Returns:
        tuple[str, str]: (forward_mac, reversed_mac) formatted as XX:XX:XX:XX:XX:XX.
    """
    if not isinstance(mfr_data, (bytes, bytearray)) or len(mfr_data) < 6:
        length = len(mfr_data) if isinstance(mfr_data, (bytes, bytearray)) else 0
        raise ValueError(f"mfr_data must have at least 6 bytes, got {length}")

    fwd = ":".join(f"{b:02X}" for b in mfr_data[:6])
    rev = ":".join(f"{b:02X}" for b in reversed(mfr_data[:6]))
    return fwd, rev


def normalize_mac_address(*, address: str) -> str | None:
    """
    Normalize a 6-byte MAC address into standard uppercase colon-separated format.

    Returns None if the address is not a valid 6-byte MAC (e.g. UUID, partial string).
    """
    if not isinstance(address, str):
        return None

    cleaned = address.strip()
    if ":" in cleaned:
        parts = cleaned.split(":")
        if len(parts) != 6:
            return None
        normalized_parts: list[str] = []
        for part in parts:
            if not (1 <= len(part) <= 2) or not all(c in _HEX_CHARS for c in part):
                return None
            normalized_parts.append(f"{int(part, 16):02X}")
        return ":".join(normalized_parts)

    if "-" in cleaned and cleaned.count("-") != 5:
        return None

    hex_only = cleaned.replace("-", "")
    if len(hex_only) == 12 and all(c in _HEX_CHARS for c in hex_only):
        return ":".join(hex_only[i : i + 2].upper() for i in range(0, 12, 2))

    return None


def matches_advertisement_address(
    *,
    target_address: str,
    mfr_data: bytes | bytearray,
    allow_forward: bool = True,
) -> bool:
    """
    Check if a target MAC address matches an advertisement's manufacturer beacon data.

    Compares normalized 6-byte values for exact equality against reversed order
    first (Classic beacon convention), then forward order if allow_forward is True.

    Args:
        target_address: Target MAC address to match against.
        mfr_data: Raw manufacturer data from beacon.
        allow_forward: Whether to also accept forward byte order match.

    Returns:
        bool: True if exact 6-byte match in reversed (or allowed forward) byte order.
    """
    if not isinstance(mfr_data, (bytes, bytearray)) or len(mfr_data) < 6:
        return False

    norm_target = normalize_mac_address(address=target_address)
    if not norm_target:
        return False

    fwd, rev = _internal_address(mfr_data=mfr_data)
    # Quirk #1: Compare reversed order first, forward second if permitted
    if norm_target == rev:
        return True
    return bool(allow_forward and norm_target == fwd)


def parse_advertisement(
    *,
    mfr_data: bytes | bytearray,
    company_id: int = CASAMBI_MANUFACTURER_ID,
) -> ParsedAdvertisement | None:
    """
    Parse raw Casambi Classic manufacturer advertisement bytes into verified and unverified fields.

    Args:
        mfr_data: Raw manufacturer payload (must be at least 8 bytes).
        company_id: BLE manufacturer company ID (must be 0x03C3 / 963).

    Returns:
        ParsedAdvertisement | None: Structured advertisement or None if invalid/malformed.
    """
    if company_id != CASAMBI_MANUFACTURER_ID:
        return None
    if not isinstance(mfr_data, (bytes, bytearray)) or len(mfr_data) < MIN_ADVERTISEMENT_BYTES:
        return None

    fwd_mac, rev_mac = _internal_address(mfr_data=mfr_data)
    raw_status = int(mfr_data[6])
    is_on = bool(raw_status & 0x01)
    unverified_flags = (raw_status >> 1) & 0x7F
    level_byte = int(mfr_data[7])
    dim_level = round(level_byte / 255.0, 3)
    level_percent = round((level_byte / 255.0) * 100)
    trailing = bytes(mfr_data[8:])

    return ParsedAdvertisement(
        company_id=company_id,
        forward_mac=fwd_mac,
        reversed_mac=rev_mac,
        address_byte=int(mfr_data[0]),
        is_on=is_on,
        level_byte=level_byte,
        dim_level=dim_level,
        level_percent=level_percent,
        raw_status_byte=raw_status,
        unverified_status_flags=unverified_flags,
        unverified_trailing_bytes=trailing,
    )
