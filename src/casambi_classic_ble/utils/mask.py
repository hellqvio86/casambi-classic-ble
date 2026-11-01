"""Data masking and sanitization utilities."""

from collections.abc import Collection
from typing import Any

DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "apikey",
        "auth",
        "connhash",
        "credential",
        "credentials",
        "key",
        "managerkey",
        "password",
        "secret",
        "session",
        "sessionid",
        "token",
        "visitorkey",
    }
)


def mask_mac(address: str | None, *, is_debug: bool = False) -> str:
    """Mask a Bluetooth MAC address for privacy-safe logging (e.g. AA:BB:**:**:EE:FF).

    If is_debug is True, the unmasked address is returned as-is for troubleshooting.
    """
    if not address or not isinstance(address, str):
        return ""
    if is_debug:
        return address.strip()
    addr = address.strip()
    sep = ":" if ":" in addr else ("-" if "-" in addr else None)
    if sep:
        parts = addr.split(sep)
        if len(parts) == 6:
            return f"{parts[0]}{sep}{parts[1]}{sep}**{sep}**{sep}{parts[4]}{sep}{parts[5]}"
    if len(addr) == 12:
        return f"{addr[:4]}****{addr[8:]}"
    return "***"


def mask_sensitive_data(
    data: Any,
    *,
    sensitive_keys: Collection[str] = DEFAULT_SENSITIVE_KEYS,
    is_debug: bool = False,
) -> Any:
    """Mask sensitive keys in nested mappings and sequences for safe logging.

    If is_debug is True, data is returned unmasked for troubleshooting.
    """
    if is_debug:
        return data
    normalized_keys = {str(k).lower().replace("_", "") for k in sensitive_keys}
    if isinstance(data, dict):
        return {
            k: (
                "***"
                if str(k).lower().replace("_", "") in normalized_keys
                and not isinstance(v, (dict, list))
                else mask_sensitive_data(v, sensitive_keys=normalized_keys, is_debug=is_debug)
            )
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [
            mask_sensitive_data(item, sensitive_keys=normalized_keys, is_debug=is_debug)
            for item in data
        ]
    return data
