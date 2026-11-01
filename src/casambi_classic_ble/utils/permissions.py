"""Platform-agnostic file and directory permission utilities."""

import logging
import os
import sys
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Standard POSIX permission modes
POSIX_FILE_PERMISSIONS: int = 0o600  # -rw-------: owner read/write only
POSIX_DIR_PERMISSIONS: int = 0o700  # drwx------: owner read/write/search only


def is_posix() -> bool:
    """Return True if running on a POSIX-compliant operating system."""
    return os.name == "posix" and sys.platform != "win32"


def secure_chmod(path: str | Path | Any, *, mode: int) -> bool:
    """Set file or directory permissions in a platform-safe manner.

    On POSIX systems, applies the requested octal permission mode.
    On non-POSIX systems (such as Windows), POSIX octal modes are not applicable
    and this function safely acts as a no-op to prevent OS errors.

    Returns True if permissions were successfully set, False if skipped or on error.
    """
    if not is_posix():
        _LOGGER.debug(
            "Skipping POSIX chmod %o on non-POSIX platform (%s): %s", mode, sys.platform, path
        )
        return False

    try:
        os.chmod(str(path), mode)
        return True
    except OSError as err:
        _LOGGER.debug("Could not set permission %o on %s: %s", mode, path, err)
        return False


def set_secure_file_permissions(path: str | Path | Any) -> bool:
    """Set secure owner-only read/write permissions (0o600) on a file."""
    return secure_chmod(path=path, mode=POSIX_FILE_PERMISSIONS)


def set_secure_dir_permissions(path: str | Path | Any) -> bool:
    """Set secure owner-only read/write/execute permissions (0o700) on a directory."""
    return secure_chmod(path=path, mode=POSIX_DIR_PERMISSIONS)
