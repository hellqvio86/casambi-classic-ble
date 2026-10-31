"""Unit tests ensuring example scripts compile and run without errors."""

import importlib.util
import py_compile
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest

from casambi_classic_ble import CasambiDevice

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


def _load_example_module(filename: str) -> ModuleType:
    file_path = EXAMPLES_DIR / filename
    spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_examples_compile_without_syntax_errors() -> None:
    """Ensure all python files in examples/ compile without syntax errors."""
    example_files = list(EXAMPLES_DIR.glob("*.py"))
    assert len(example_files) >= 2

    for example_file in example_files:
        py_compile.compile(str(example_file), doraise=True)


@pytest.mark.asyncio
async def test_scan_devices_example_execution() -> None:
    """Ensure scan_devices.py executes against mocked scanner."""
    mock_device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", name="Mock Light")

    with patch(
        "casambi_classic_ble.CasambiScanner.scan",
        new=AsyncMock(return_value=[mock_device]),
    ):
        scan_devices = _load_example_module("scan_devices.py")
        await scan_devices.main()


@pytest.mark.asyncio
async def test_simple_connection_example_execution() -> None:
    """Ensure simple_connection.py executes against mocked device."""
    mock_device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", name="Mock Light")

    mock_connect = AsyncMock(return_value=None)
    mock_disconnect = AsyncMock(return_value=None)
    mock_turn_on = AsyncMock(return_value=None)
    mock_turn_off = AsyncMock(return_value=None)
    mock_set_level = AsyncMock(return_value=None)

    simple_connection = _load_example_module("simple_connection.py")

    # Test with devices found
    with (
        patch("casambi_classic_ble.CasambiScanner.scan", new=AsyncMock(return_value=[mock_device])),
        patch.object(mock_device, "connect", new=mock_connect),
        patch.object(mock_device, "disconnect", new=mock_disconnect),
        patch.object(mock_device, "turn_on", new=mock_turn_on),
        patch.object(mock_device, "turn_off", new=mock_turn_off),
        patch.object(mock_device, "set_level", new=mock_set_level),
    ):
        await simple_connection.main()
        mock_connect.assert_awaited_once()
        mock_turn_on.assert_awaited_once()
        mock_set_level.assert_awaited_once_with(unit_id=1, level=0.75)
        mock_turn_off.assert_awaited_once()
        mock_disconnect.assert_awaited_once()

    # Test empty branch
    with patch("casambi_classic_ble.CasambiScanner.scan", new=AsyncMock(return_value=[])):
        await simple_connection.main()
