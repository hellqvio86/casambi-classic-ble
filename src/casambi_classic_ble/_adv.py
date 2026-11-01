"""Advertisement and beacon parsing helpers for Casambi Classic."""

import logging

logger = logging.getLogger(__name__)


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
    if len(mfr_data) < 6:
        raise ValueError(f"mfr_data must have at least 6 bytes, got {len(mfr_data)}")

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
        if len(parts) == 6:
            try:
                return ":".join(f"{int(p, 16):02X}" for p in parts if len(p) <= 2)
            except ValueError:
                return None
        return None

    hex_only = cleaned.replace("-", "")
    if len(hex_only) == 12:
        try:
            bytes.fromhex(hex_only)
            return ":".join(hex_only[i : i + 2].upper() for i in range(0, 12, 2))
        except ValueError:
            return None

    return None


def matches_advertisement_address(*, target_address: str, mfr_data: bytes | bytearray) -> bool:
    """
    Check if a target MAC address matches an advertisement's manufacturer beacon data.

    Compares normalized 6-byte values for exact equality against reversed order
    first (Classic beacon convention), then forward order.

    Args:
        target_address: Target MAC address to match against.
        mfr_data: Raw manufacturer data from beacon.

    Returns:
        bool: True if exact 6-byte match in reversed or forward byte order.
    """
    if not isinstance(mfr_data, (bytes, bytearray)) or len(mfr_data) < 6:
        return False

    norm_target = normalize_mac_address(address=target_address)
    if not norm_target:
        return False

    fwd, rev = _internal_address(mfr_data=mfr_data)
    # Quirk #1: Compare reversed order first, forward second
    return norm_target in (rev, fwd)
