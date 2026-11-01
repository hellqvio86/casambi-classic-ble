"""Unit tests ensuring example scripts compile and run without errors."""

import ast
import importlib.util
import inspect
import py_compile
import re
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest

from casambi_classic_ble import CasambiCloud, CasambiDevice, CasambiScanner

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


def _validate_snippet_ast(snippet: str, *, snippet_id: str) -> None:
    """Helper to validate that a code snippet parses and calls valid APIs."""
    class_map = {
        "CasambiDevice": CasambiDevice,
        "CasambiCloud": CasambiCloud,
        "CasambiScanner": CasambiScanner,
    }

    variable_types: dict[str, type] = {
        "light": CasambiDevice,
        "target": CasambiDevice,
        "device": CasambiDevice,
        "scanner": CasambiScanner,
        "cloud": CasambiCloud,
    }

    tree = ast.parse(snippet, filename=snippet_id)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Check constructor calls e.g. CasambiCloud(...)
        if isinstance(node.func, ast.Name) and node.func.id in class_map:
            target_cls = class_map[node.func.id]
            sig = inspect.signature(target_cls)
            valid_params = set(sig.parameters.keys()) - {"self"}

            for kw in node.keywords:
                assert kw.arg in valid_params, (
                    f"{snippet_id} passed invalid keyword argument '{kw.arg}' "
                    f"to {node.func.id}. Valid: {valid_params}"
                )

        # Check method calls e.g. cloud.get_networks(), device.turn_on(...)
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            var_name = node.func.value.id
            method_name = node.func.attr
            if var_name in variable_types:
                target_cls = variable_types[var_name]
                assert hasattr(target_cls, method_name), (
                    f"{snippet_id} calls non-existent method '{method_name}' "
                    f"on {var_name} ({target_cls.__name__})"
                )

                method_obj = getattr(target_cls, method_name)
                if callable(method_obj):
                    try:
                        sig = inspect.signature(method_obj)
                        valid_params = set(sig.parameters.keys()) - {"self"}
                        for kw in node.keywords:
                            assert kw.arg in valid_params, (
                                f"{snippet_id} passed invalid keyword '{kw.arg}' "
                                f"to {var_name}.{method_name}(). Valid: {valid_params}"
                            )
                    except (ValueError, TypeError):
                        pass


def test_readme_python_snippets_ast_and_signatures() -> None:
    """Extract fenced python blocks from README.md, ast.parse them, and check signatures (Q-006)."""
    readme_path = Path(__file__).resolve().parent.parent.parent / "README.md"
    content = readme_path.read_text(encoding="utf-8")

    pattern = re.compile(r"```python\n(.*?)\n```", re.DOTALL)
    snippets = pattern.findall(content)
    assert len(snippets) >= 4, "Expected at least 4 python code blocks in README.md"

    for idx, snippet in enumerate(snippets, start=1):
        _validate_snippet_ast(snippet=snippet, snippet_id=f"README snippet {idx}")


def test_readme_validator_catches_invalid_cloud_calls() -> None:
    """Ensure validator detects obsolete cloud params and non-existent methods (Q-006 acceptance)."""
    invalid_snippet_param = """
async with CasambiCloud(
    api_key="key",
    user_email="user@test.com",
    user_password="password",
) as cloud:
    pass
"""
    with pytest.raises(AssertionError, match="invalid keyword argument 'user_email'"):
        _validate_snippet_ast(snippet=invalid_snippet_param, snippet_id="invalid_param_test")

    invalid_snippet_method = """
async with CasambiCloud(
    api_key="key",
    email="user@test.com",
    user_password="password",
    network_password="net",
) as cloud:
    networks = await cloud.get_networks()
"""
    with pytest.raises(AssertionError, match="calls non-existent method 'get_networks'"):
        _validate_snippet_ast(snippet=invalid_snippet_method, snippet_id="invalid_method_test")
