"""Tests for atomic write operations, crash safety, and secure path validation."""

import asyncio
from pathlib import Path

import pytest

from casambi_classic_ble.exceptions import CasambiSecurityError
from casambi_classic_ble.utils import (
    POSIX_DIR_PERMISSIONS,
    POSIX_FILE_PERMISSIONS,
    async_atomic_write_file,
    atomic_write_file,
    ensure_secure_directory,
    is_posix,
    validate_safe_path,
)


def test_atomic_write_file_basic(tmp_path: Path):
    target = tmp_path / "sub" / "test.txt"
    content = "hello secure world"

    atomic_write_file(path=target, content=content)

    assert target.exists()
    assert target.read_text(encoding="utf-8") == content
    if is_posix():
        assert (target.stat().st_mode & 0o777) == POSIX_FILE_PERMISSIONS
        assert (target.parent.stat().st_mode & 0o777) == POSIX_DIR_PERMISSIONS


@pytest.mark.asyncio
async def test_async_atomic_write_file(tmp_path: Path):
    target = tmp_path / "async_test.json"
    content = '{"secure": true}'

    await async_atomic_write_file(path=target, content=content)

    assert target.exists()
    assert target.read_text(encoding="utf-8") == content


def test_atomic_write_replaces_existing_atomically(tmp_path: Path):
    target = tmp_path / "replace_target.txt"
    target.write_text("old content")

    atomic_write_file(path=target, content="new content")

    assert target.read_text() == "new content"
    # Ensure no leftover temporary files in directory
    tmp_files = list(tmp_path.glob(".*.tmp"))
    assert tmp_files == []


def test_atomic_write_failure_cleans_up_and_preserves_target(tmp_path: Path, monkeypatch):
    target = tmp_path / "critical_data.txt"
    target.write_text("original preserved content")

    # Simulate an error during open/write to temporary file
    import os

    def failing_fsync(fd):
        raise OSError("Disk I/O error during sync")

    monkeypatch.setattr(os, "fsync", failing_fsync)

    with pytest.raises(OSError, match="Disk I/O error during sync"):
        atomic_write_file(path=target, content="corrupted new data")

    # Target remains untouched
    assert target.read_text() == "original preserved content"
    # Temp files are cleanly unlinked
    tmp_files = list(tmp_path.glob(".*.tmp"))
    assert tmp_files == []


@pytest.mark.asyncio
async def test_atomic_write_cancellation_safety(tmp_path: Path):
    target = tmp_path / "cancel_target.txt"
    await asyncio.to_thread(target.write_text, "pre-cancellation content")

    # Start an async write that gets cancelled immediately
    task = asyncio.create_task(
        async_atomic_write_file(path=target, content="this should be cancelled")
    )
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Target must remain pristine
    content = await asyncio.to_thread(target.read_text)
    assert content == "pre-cancellation content"
    tmp_files = await asyncio.to_thread(lambda: list(tmp_path.glob(".*.tmp")))
    assert tmp_files == []


def test_atomic_write_rejects_symlink_target(tmp_path: Path):
    real_file = tmp_path / "real.txt"
    real_file.write_text("real data")

    symlink_file = tmp_path / "symlink.txt"
    symlink_file.symlink_to(real_file)

    with pytest.raises(CasambiSecurityError, match="Target file cannot be a symlink"):
        atomic_write_file(path=symlink_file, content="malicious overwrite")

    assert real_file.read_text() == "real data"


def test_ensure_secure_directory_rejects_symlink(tmp_path: Path):
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()

    symlink_dir = tmp_path / "symlink_dir"
    symlink_dir.symlink_to(real_dir)

    with pytest.raises(CasambiSecurityError, match="Symlinks are forbidden"):
        ensure_secure_directory(path=symlink_dir)


def test_validate_safe_path_security(tmp_path: Path):
    base = tmp_path / "cache_base"
    base.mkdir()

    # Valid relative sub-path
    valid_sub = base / "network-1" / "file.json"
    assert validate_safe_path(path=valid_sub, base_path=base) == valid_sub

    # Path traversal outside base
    outside = tmp_path / "outside.txt"
    with pytest.raises(CasambiSecurityError, match="Path traversal detected"):
        validate_safe_path(path=outside, base_path=base)

    # Null byte injection
    with pytest.raises(CasambiSecurityError, match="forbidden null byte"):
        validate_safe_path(path=f"{base}/file\x00.json", base_path=base)

    # Symlink file rejection
    real_file = base / "target.json"
    real_file.touch()
    sym_file = base / "link.json"
    sym_file.symlink_to(real_file)

    with pytest.raises(CasambiSecurityError, match="Symlinks are forbidden"):
        validate_safe_path(path=sym_file, base_path=base)
