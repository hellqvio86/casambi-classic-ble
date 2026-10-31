"""Test ensuring all public functions and methods enforce keyword-only arguments (*) per AGENTS.md."""

import inspect
from typing import Any

from casambi_classic_ble import CasambiCloud, CasambiDevice, CasambiScanner


def check_keyword_only_signatures(
    cls: type[Any], excluded_methods: set[str] | None = None
) -> list[str]:
    """Inspect all public methods on a class to verify parameters (beyond self/cls) are KEYWORD_ONLY."""
    violations: list[str] = []
    excluded = excluded_methods or set()

    for name, member in inspect.getmembers(cls):
        if name.startswith("_") or name in excluded:
            continue

        if inspect.isfunction(member) or inspect.ismethod(member):
            sig = inspect.signature(member)
            params = list(sig.parameters.values())

            # Skip 'self' or 'cls'
            non_self_params = [
                p
                for p in params
                if p.name not in {"self", "cls"} and p.kind != inspect.Parameter.VAR_KEYWORD
            ]

            for p in non_self_params:
                if p.kind not in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_POSITIONAL):
                    violations.append(
                        f"{cls.__name__}.{name}({p.name}): parameter kind is {p.kind.name}, expected KEYWORD_ONLY"
                    )

    return violations


def test_casambi_device_public_methods_enforce_keyword_only() -> None:
    """Verify all public methods on CasambiDevice require keyword-only arguments."""
    violations = check_keyword_only_signatures(CasambiDevice)
    assert not violations, "Positional arguments detected on CasambiDevice:\n" + "\n".join(
        violations
    )


def test_casambi_scanner_public_methods_enforce_keyword_only() -> None:
    """Verify all public methods on CasambiScanner require keyword-only arguments."""
    violations = check_keyword_only_signatures(CasambiScanner)
    assert not violations, "Positional arguments detected on CasambiScanner:\n" + "\n".join(
        violations
    )


def test_casambi_cloud_public_methods_enforce_keyword_only() -> None:
    """Verify all public methods on CasambiCloud require keyword-only arguments."""
    # __aenter__ and __aexit__ are standard dunder protocol methods
    violations = check_keyword_only_signatures(
        CasambiCloud, excluded_methods={"__aenter__", "__aexit__"}
    )
    assert not violations, "Positional arguments detected on CasambiCloud:\n" + "\n".join(
        violations
    )
