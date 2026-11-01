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


def test_changelog_has_current_version() -> None:
    """Verify that CHANGELOG.md contains a section header matching the pyproject.toml version (Q-007)."""
    pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)

    current_version = pyproject_data["project"]["version"]
    changelog_path = Path(__file__).parents[2] / "CHANGELOG.md"
    assert changelog_path.exists(), "CHANGELOG.md file is missing"

    changelog_text = changelog_path.read_text(encoding="utf-8")
    expected_header = f"## [{current_version}]"
    assert expected_header in changelog_text, (
        f"CHANGELOG.md is missing an entry for the current version: '{expected_header}'"
    )
