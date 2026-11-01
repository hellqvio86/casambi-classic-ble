"""Data masking and sanitization utilities."""

from collections.abc import Collection
from typing import Any

DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {"session", "sessionid", "token", "password", "key", "apikey", "secret"}
)


def mask_sensitive_data(
    data: Any,
    *,
    sensitive_keys: Collection[str] = DEFAULT_SENSITIVE_KEYS,
) -> Any:
    """Mask sensitive keys in nested mappings and sequences for safe logging."""
    normalized_keys = {str(k).lower().replace("_", "") for k in sensitive_keys}
    if isinstance(data, dict):
        return {
            k: (
                "***"
                if str(k).lower().replace("_", "") in normalized_keys
                else mask_sensitive_data(v, sensitive_keys=normalized_keys)
            )
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [mask_sensitive_data(item, sensitive_keys=normalized_keys) for item in data]
    return data
