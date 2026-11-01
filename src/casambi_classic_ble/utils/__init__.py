"""Casambi Classic BLE utilities submodule."""

from .mask import DEFAULT_SENSITIVE_KEYS, mask_sensitive_data
from .permissions import (
    POSIX_DIR_PERMISSIONS,
    POSIX_FILE_PERMISSIONS,
    is_posix,
    secure_chmod,
    set_secure_dir_permissions,
    set_secure_file_permissions,
)

__all__ = [
    "DEFAULT_SENSITIVE_KEYS",
    "POSIX_DIR_PERMISSIONS",
    "POSIX_FILE_PERMISSIONS",
    "is_posix",
    "mask_sensitive_data",
    "secure_chmod",
    "set_secure_dir_permissions",
    "set_secure_file_permissions",
]
