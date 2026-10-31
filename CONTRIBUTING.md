# Contributing to `casambi-classic-ble`

Thank you for your interest in contributing to `casambi-classic-ble`! This project provides an asynchronous Python library for Casambi lighting devices running **Classic firmware** over Bluetooth Low Energy (BLE).

---

## Code of Conduct & Core Guidelines

Please review [AGENTS.md](AGENTS.md) for detailed operational standards, architectural context, and coding rules. All contributors and automated agents must adhere to the rules outlined there.

> [!CAUTION]
> **Zero Hardware Identifiers & Zero PII Policy:**  
> **NEVER commit real MAC addresses, network passwords, encryption keys, device names, or personal identifiers.**  
> In all tests, documentation, mock fixtures, and logs, use standardized placeholders (e.g., `AA:BB:CC:DD:EE:FF`, `aabbccddeeff...`, `MockDevice`). TruffleHog secret scanning is strictly enforced on every commit and PR.

---

## Development Setup

The project uses [`uv`](https://docs.astral.sh/uv/) for package and virtual environment management, targeting **Python >= 3.12**.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/hellqvio86/casambi-classic-ble.git
   cd casambi-classic-ble
   ```

2. **Set up the virtual environment & install dependencies:**
   ```bash
   make setup
   # Or manually:
   uv sync --all-extras
   make hooks
   ```

3. **Install Git pre-commit hooks:**
   ```bash
   make hooks
   ```
   *The pre-commit hook runs TruffleHog secret scanning, Ruff lint/format checks, mypy typechecking, and the full pytest suite.*

---

## Coding Standards

1. **Modern Python (>= 3.12):**
   - Use built-in generic types (`list[str]`, `dict[str, Any]`, `tuple[int, ...]`) instead of `typing.List` or `typing.Dict`.
   - Use pipe union syntax (`str | None`, `int | float`) instead of `Optional[...]` or `Union[...]`.
   - Use `enum.StrEnum` or `enum.IntEnum` for enumerations.

2. **Full Static Typing:**
   - Every function, method signature, parameter, and return value must have explicit type annotations.
   - Code must pass `uv run mypy src/` with zero errors.

3. **Keyword-Only Public APIs:**
   - All public methods and functions must declare arguments as **keyword-only** using `*` (e.g., `def set_level(self, *, level: float, unit_id: int | None = None) -> None:`).
   - This ensures call sites are explicit, self-documenting, and resilient to signature changes.

4. **Error Handling:**
   - Never use bare `except:` clauses.
   - Raise explicit, domain-specific exceptions from `casambi_classic_ble.exceptions` (`CasambiException`, `CasambiConnectionError`, `CasambiDeviceError`).
   - Preserve error chains with `raise NewException(...) from err`.

5. **Formatting & Linting:**
   - Formatted with Ruff at a maximum line length of **100**.
   - Verify with `uv run ruff check src/` and `uv run ruff format --check src/`.

---

## Testing Requirements

Every bug fix, feature, and protocol opcode handler must be covered by unit tests in [`src/tests/`](src/tests/).

1. **Coverage Requirements:**
   - Total test coverage must meet or exceed **80%** (with branch coverage enabled).
   - Run tests with coverage:
     ```bash
     uv run pytest src/tests/ --cov=casambi_classic_ble --cov-branch --cov-report=term-missing
     ```

2. **Test Isolation:**
   - **No Live Hardware or Network in Tests:** All tests must run in headless, isolated CI runners.
   - Mock all `bleak.BleakClient` and advertisement payloads using `unittest.mock.AsyncMock` and `MagicMock`.
   - Protocol byte sequences must be verified against exact opcodes and little-endian wire representations. See [docs/protocol.md](docs/protocol.md) and `src/tests/fixtures/golden_vectors.json`.

---

## Git Commit Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New features or public API changes
- `fix:` Bug fixes
- `docs:` Documentation improvements
- `ci:` CI/CD pipeline or workflow changes
- `chore:` Dependency bumps, repo maintenance, or tooling configuration
- `test:` Adding or updating unit tests

---

## Stability Policy (0.x)

- **Public API:** The public API is strictly defined by `__all__` in [`src/casambi_classic_ble/__init__.py`](src/casambi_classic_ble/__init__.py). Internal modules prefixed with `_` (e.g. `_client.py`, `_unit.py`) are private implementation details.
- **Breaking Changes in 0.x:** While in `0.x`, minor version increments (`0.3.0` -> `0.4.0`) may adjust public API signatures or deprecate legacy patterns. Patch releases (`0.3.1` -> `0.3.2`) will remain backwards-compatible.

---

## Pull Request Checklist

Before opening a pull request:
1. [ ] Run `make all` locally (TruffleHog, lint, typecheck, pytest with coverage).
2. [ ] Verify that no credentials, network keys, or real MAC addresses are included in code, fixtures, or docs.
3. [ ] Ensure all commits follow Conventional Commits formatting.
4. [ ] If adding new protocol opcodes or altering frame structures, update [docs/protocol.md](docs/protocol.md) and golden vectors.
