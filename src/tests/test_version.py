"""Tests for package version and pyproject.toml synchronization."""

import importlib
import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

import casambi_classic_ble


def test_version_matches_pyproject() -> None:
    """Verify that casambi_classic_ble.__version__ matches pyproject.toml."""
    pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)

    expected_version = pyproject_data["project"]["version"]
    assert casambi_classic_ble.__version__ == expected_version


def test_version_fallback_on_package_not_found() -> None:
    """Verify fallback to '0+unknown' when package metadata is not found."""
    with patch("importlib.metadata.version", side_effect=PackageNotFoundError):
        importlib.reload(casambi_classic_ble)
        assert casambi_classic_ble.__version__ == "0+unknown"

    # Reload again to restore the real version
    importlib.reload(casambi_classic_ble)
    assert casambi_classic_ble.__version__ != "0+unknown"
