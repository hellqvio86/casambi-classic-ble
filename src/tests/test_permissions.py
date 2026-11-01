"""Tests for cross-platform file and directory permission utilities."""

import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

from casambi_classic_ble.utils.permissions import (
    POSIX_DIR_PERMISSIONS,
    POSIX_FILE_PERMISSIONS,
    is_posix,
    secure_chmod,
    set_secure_dir_permissions,
    set_secure_file_permissions,
)


def test_is_posix() -> None:
    """Verify is_posix correctly detects posix vs non-posix."""
    expected = os.name == "posix" and sys.platform != "win32"
    assert is_posix() == expected


def test_secure_chmod_posix(tmp_path: Path) -> None:
    """Verify secure_chmod sets permission bits on POSIX."""
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("hello")

    with patch("casambi_classic_ble.utils.permissions.is_posix", return_value=True):
        result = secure_chmod(path=test_file, mode=0o600)
        assert result is True
        if is_posix():
            file_stat = os.stat(str(test_file))
            assert stat.S_IMODE(file_stat.st_mode) == 0o600


def test_secure_chmod_non_posix(tmp_path: Path) -> None:
    """Verify secure_chmod is safely a no-op on non-POSIX platforms like Windows."""
    test_file = tmp_path / "test_win.txt"
    test_file.write_text("windows")

    with (
        patch("casambi_classic_ble.utils.permissions.is_posix", return_value=False),
        patch("os.chmod") as mock_chmod,
    ):
        result = secure_chmod(path=test_file, mode=0o600)
        assert result is False
        mock_chmod.assert_not_called()


def test_secure_chmod_os_error(tmp_path: Path) -> None:
    """Verify secure_chmod catches OSError and returns False safely without raising."""
    test_file = tmp_path / "error_file.txt"
    test_file.write_text("error")

    with (
        patch("casambi_classic_ble.utils.permissions.is_posix", return_value=True),
        patch("os.chmod", side_effect=OSError("Read-only filesystem")),
    ):
        result = secure_chmod(path=test_file, mode=0o600)
        assert result is False


def test_set_secure_file_permissions(tmp_path: Path) -> None:
    """Verify set_secure_file_permissions delegates to secure_chmod with POSIX_FILE_PERMISSIONS."""
    test_file = tmp_path / "secure_file.txt"
    test_file.write_text("data")

    with patch(
        "casambi_classic_ble.utils.permissions.secure_chmod", return_value=True
    ) as mock_secure_chmod:
        result = set_secure_file_permissions(path=test_file)
        assert result is True
        mock_secure_chmod.assert_called_once_with(path=test_file, mode=POSIX_FILE_PERMISSIONS)


def test_set_secure_dir_permissions(tmp_path: Path) -> None:
    """Verify set_secure_dir_permissions delegates to secure_chmod with POSIX_DIR_PERMISSIONS."""
    test_dir = tmp_path / "secure_dir"
    test_dir.mkdir()

    with patch(
        "casambi_classic_ble.utils.permissions.secure_chmod", return_value=True
    ) as mock_secure_chmod:
        result = set_secure_dir_permissions(path=test_dir)
        assert result is True
        mock_secure_chmod.assert_called_once_with(path=test_dir, mode=POSIX_DIR_PERMISSIONS)
