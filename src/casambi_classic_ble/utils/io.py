"""Atomic file writing and secure path validation utilities."""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from ..exceptions import CasambiSecurityError
from .permissions import (
    POSIX_DIR_PERMISSIONS,
    POSIX_FILE_PERMISSIONS,
    is_posix,
    secure_chmod,
    set_secure_dir_permissions,
    set_secure_file_permissions,
)

_LOGGER = logging.getLogger(__name__)


def validate_safe_path(
    path: str | Path | Any,
    *,
    base_path: str | Path | Any | None = None,
    allow_symlinks: bool = False,
) -> Path:
    """Validate that path does not contain path traversal and optionally stays within base_path.

    Raises CasambiSecurityError if path is invalid, traverses outside base_path,
    or contains forbidden symlinks.
    """
    raw_str = str(path)
    if "\x00" in raw_str:
        raise CasambiSecurityError("Path contains forbidden null byte.")

    # Convert anyio.Path or str to pathlib.Path
    target_path = Path(raw_str)

    if not allow_symlinks and target_path.is_symlink():
        raise CasambiSecurityError(f"Symlinks are forbidden for cache paths: {target_path}")

    if base_path is not None:
        base_raw_str = str(base_path)
        if "\x00" in base_raw_str:
            raise CasambiSecurityError("Base path contains forbidden null byte.")
        base = Path(base_raw_str).resolve()
        resolved_target = target_path.resolve()

        if not resolved_target.is_relative_to(base):
            raise CasambiSecurityError(
                f"Path traversal detected: {target_path} resolves to {resolved_target} "
                f"outside base directory {base}"
            )

    return target_path


def ensure_secure_directory(path: str | Path | Any) -> Path:
    """Ensure directory exists with secure restrictive permissions (0700 on POSIX).

    Raises CasambiSecurityError if directory is a symlink.
    """
    dir_path = Path(str(path))
    if dir_path.is_symlink():
        raise CasambiSecurityError(f"Symlinks are forbidden for cache directories: {dir_path}")

    if not dir_path.exists():
        dir_path.mkdir(
            parents=True,
            exist_ok=True,
            mode=POSIX_DIR_PERMISSIONS if is_posix() else 0o777,
        )

    set_secure_dir_permissions(dir_path)
    return dir_path


def atomic_write_file(
    path: str | Path | Any,
    content: str | bytes,
    *,
    encoding: str = "utf-8",
    mode: int = POSIX_FILE_PERMISSIONS,
) -> None:
    """Write content to file atomically with restrictive permissions and fsync flush.

    Writes to a temporary file in the same directory, flushes and fsyncs,
    sets secure permissions, and atomically renames over the target path.
    Guarantees that interrupted or cancelled writes never leave corrupt or
    partially written files.
    """
    target = Path(str(path))
    if target.is_symlink():
        raise CasambiSecurityError(f"Target file cannot be a symlink: {target}")

    parent = target.parent
    ensure_secure_directory(parent)

    temp_fd, temp_path_str = tempfile.mkstemp(
        dir=parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_path_str)

    try:
        set_secure_file_permissions(temp_path)
        data = content.encode(encoding) if isinstance(content, str) else content

        with open(temp_fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        secure_chmod(temp_path, mode=mode)
        os.replace(temp_path, target)
    except BaseException:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


async def async_atomic_write_file(
    path: str | Path | Any,
    content: str | bytes,
    *,
    encoding: str = "utf-8",
    mode: int = POSIX_FILE_PERMISSIONS,
) -> None:
    """Async wrapper to write content atomically offloaded to executor."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: atomic_write_file(path, content, encoding=encoding, mode=mode),
    )
