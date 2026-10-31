# AGENTS.md

Guidelines and operational knowledge for AI coding assistants (Antigravity Agent, Claude Code, Cursor, Copilot, etc.) and contributors working in this repository.

---

## 💡 What This Project Is

`casambi-classic-ble` is an asynchronous Python library for controlling Casambi lighting networks running **Classic firmware** over **Bluetooth Low Energy (BLE)** via [`Bleak`](https://github.com/hbldh/bleak), with optional Casambi Cloud API & WebSocket bridge support.

- **Primary Downstream Consumer:** [`casambi-classic-bt-hass`](https://github.com/hellqvio86/casambi-classic-bt-hass) (Home Assistant custom integration).
- **Target Python Version:** `>= 3.12`.
- **Packaging & Dependency Management:** Managed with [`uv`](https://docs.astral.sh/uv/) and standard `pyproject.toml`.

---

## 📁 Repository Layout

```
casambi-classic-ble/
├── src/
│   ├── casambi_classic_ble/    # Core library source code
│   │   ├── __init__.py         # Exports CasambiDevice, CasambiScanner, CasambiCloud
│   │   ├── constants.py        # UUIDs, opcodes, BLE service constants
│   │   ├── device.py           # CasambiDevice implementation (BLE connect, control, state)
│   │   ├── scanner.py          # CasambiScanner implementation (discovery via Bleak)
│   │   ├── exceptions.py       # Library-specific exceptions
│   │   └── cloud/              # Casambi Cloud REST & WebSocket bridge
│   │       ├── __init__.py     # CasambiCloud context manager & interface
│   │       ├── api.py          # REST API sessions & endpoints
│   │       └── websocket.py    # Real-time WebSocket connection to Casambi Bridge
│   └── tests/                  # Pytest unit tests (mocked BLE and HTTP/WS)
├── examples/                   # Example usage scripts (scanning, simple connection)
├── .github/
│   ├── workflows/
│   │   └── ci.yml              # CI/CD pipeline (lint, test matrix, draft release, publish)
│   └── dependabot.yml          # Dependabot configuration (2-day cooldown, hellqvio86 assignee)
├── .githooks/                  # Git commit hooks (pre-commit lint & test runner)
├── Makefile                    # Developer convenience targets
├── pyproject.toml              # Build config, dependencies, Ruff/pytest/mypy configurations
└── uv.lock                     # Deterministic dependency lockfile
```

---

## 🔒 Strict Security & Privacy Mandate (Zero PII / Zero Hardware Identifiers)

**NEVER COMMIT CREDENTIALS, REAL MAC ADDRESSES, NETWORK KEYS, DEVICE IDENTIFIERS, OR ANY PII (Personally Identifiable Information).**

1. **No Real Hardware Identifiers or PII:**
   - Never commit actual Bluetooth MAC addresses, device IDs, network addresses, or real device names (e.g. custom home tags).
   - In all unit tests, docstrings, examples, and fixtures, **always use standardized or generic mock placeholders**:
     - Example MAC addresses: `AA:BB:CC:DD:EE:FF` or `00:11:22:33:44:55`.
     - Example device names: `MockDevice` or `Test Light`.
     - Example hex payloads: `aabbccddeeff...`.
2. **No Hardware Scripts with Personal Data:**
   - Never commit personal hardware diagnostic scripts, hardcoded MAC triggers, or local network dumps into the repository.
3. **No Credentials:**
   - Never commit API keys, user passwords, network passwords, email addresses, or tokens.
   - Any local configuration files containing credentials (like `casambi.yaml`, `.env`) are strictly gitignored and must never be tracked or staged.
4. **Mandatory Secret Scanning:**
   - TruffleHog secret scanning is mandatory and enforced locally on every commit via `.githooks/pre-commit` and in CI.

---

## 🐍 Code Style & Pythonista Standards

Write clean, idiomatic, and modern Python (Python `>= 3.12`). Code should look and feel like it was crafted by an experienced Pythonista:

1. **Modern Python Syntax (>= 3.12):**
   - Use built-in generic types (`list[str]`, `dict[str, Any]`, `tuple[int, ...]`) instead of `typing.List` or `typing.Dict`.
   - Use pipe union types (`str | None`, `int | float`) instead of `Optional[...]` or `Union[...]`.
   - Prefer `enum.StrEnum` or `enum.IntEnum` for constants and enumerations.
   - Use `@dataclass` or typed structures for complex internal models where appropriate.

2. **Full Type Annotations:**
   - Every function, method signature, parameter, and return value must have explicit type annotations.
   - Annotate internal collections and class attributes (`self.last_state: dict[str, Any] = {}`).
   - Use precise types whenever possible; avoid fallback `Any` unless interfacing with raw dynamic JSON payloads or dynamic BLE buffer unpacks.

3. **Context Managers & Resource Safety:**
   - Always manage sessions, sockets, and client connections using context managers (`async with`) to ensure reliable cleanup.
   - Protect state mutation and concurrent I/O with `asyncio.Lock` where appropriate.

4. **Error Handling & Explicit Failures:**
   - Raise explicit, domain-specific exceptions from [`casambi_classic_ble.exceptions`](file:///home/hellqvio/git/casambi-classic-ble/casambi_classic_ble/exceptions.py) (`CasambiException`, `CasambiConnectionError`, `CasambiDeviceError`) rather than returning ambiguous sentinel values (`None`, `False`, `-1`).
   - **Never use bare `except:` clauses.** Always catch explicit exception types (e.g., `except (BleakError, asyncio.TimeoutError) as err:`).
   - Preserve error chaining with `raise NewException(...) from err`.

5. **Mandatory Named (Keyword) Arguments:**
   - **Always use named arguments for function and method calls.** Never pass ambiguous positional arguments (e.g., use `scanner.scan(duration=5.0)` instead of `scanner.scan(5.0)`, `device.set_level(unit_id=1, level=0.75)` instead of `device.set_level(1, 0.75)`).
   - In public APIs, function signatures, and method definitions, prefer **keyword-only arguments** using `*` (e.g. `def scan(self, *, duration: float = 10.0) -> list[CasambiDevice]:` or `def set_level(self, *, unit_id: int, level: float) -> bool:`) to enforce named arguments at the call site.
   - Tests and fixtures must strictly adhere to calling methods with explicit named arguments.

6. **Formatting & Documentation:**
   - Format with Ruff: maximum line length is **100**, rules `E`, `F`, `W`, `I`.
   - Keep docstrings clean and compliant with PEP 257.

---

## 🧪 Mandatory Pytest Test Coverage

**All code must be covered with `pytest` unit tests.** Untested code, uncovered branches, or PRs lacking test assertions are not accepted.

1. **Comprehensive Coverage Requirements:**
   - Every public method, edge case, protocol opcode parser, and error branch must be accompanied by unit tests in [`src/tests/`](file:///home/hellqvio/git/casambi-classic-ble/src/tests/).
   - Always run test suite coverage before committing:
     ```bash
     uv run pytest src/tests/ --cov=casambi_classic_ble --cov-report=term-missing
     ```
   - Write tests for both positive ("happy path") and negative (timeouts, disconnects, malformed packet payloads, auth failures) scenarios.

2. **Test Design & Isolation:**
   - **No Live Hardware or Network in Tests:** All tests must run in isolated headless CI runners.
   - Mock all `bleak.BleakClient`, BLE advertisements, and discovery calls with `unittest.mock.AsyncMock` and `MagicMock`.
   - Mock `aiohttp.ClientSession` and WebSocket connections; never make live network calls.
   - Assert exact behavior: check opcode byte sequences, packet headers, payload integrity, and callback dispatches—do not simply assert that an async method returned without throwing.

---

## 🛠️ Verification & Development Commands

Always run these before completing any changes or committing:

```bash
# Set up development environment (installs dev dependencies and extras)
uv sync --all-extras

# Run Ruff linter and formatter checks
uv run ruff check src/
uv run ruff format --check src/

# Run pytest unit test suite with coverage
uv run pytest src/tests/ --cov=casambi_classic_ble --cov-report=term-missing

# Build package distributions (wheel and sdist)
uv build
```

Convenience `Makefile` targets:
```bash
make setup      # Sets up virtualenv and installs all dependencies and hooks
make lint       # Runs ruff and formatting check
make test       # Runs pytest unit tests
make coverage   # Runs pytest with HTML and terminal coverage report
make build      # Builds package wheels and sdist with uv
make clean      # Cleans test cache, build artifacts, and pycache
```

---

## 🚀 Release Flow (CI/CD to PyPI)

This project uses an automated GitHub Actions flow configured in [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

1. **Version Change Detection:**
   - On every push to `main`, the workflow compares `version` in `pyproject.toml` against `HEAD~1`.
2. **Draft Release:**
   - When a version change is detected, CI automatically tags the commit (`v<version>`), builds the distribution packages (`.whl` and `.tar.gz`), generates an SPDX SBOM (`anchore/sbom-action`), generates a changelog from commit history, and creates a **Draft Release** on GitHub with the build artifacts attached.
3. **Publish to PyPI:**
   - **Automated:** Review and publish the draft release on GitHub. Publishing triggers the `publish` job, which validates all checks and securely uploads the distribution packages to PyPI via PyPI Trusted Publishing (OIDC).
   - **On Demand (Manual):** Trigger the `publish` job manually at any time via GitHub CLI or Web UI:
     ```bash
     gh workflow run ci.yml -f job=publish
     ```
     This executes lint, test matrix, builds the package, and publishes to PyPI with `skip-existing: true`.
   - **PyPI Trusted Publisher Settings:**
     - Repository: `hellqvio86/casambi-classic-ble`
     - Workflow name: `ci.yml`
     - Environment name: `pypi`
   - **Never manually upload releases with static PyPI API tokens from local CLI.**

---

## 📝 Commit Conventions

- Use [Conventional Commits](https://www.conventionalcommits.org/):
  - `feat:` New features or public API changes
  - `fix:` Bug fixes
  - `docs:` Documentation improvements
  - `ci:` GitHub Actions and CI/CD workflow changes
  - `chore:` Dependency bumps, repo maintenance, or configuration
  - `test:` Adding or updating unit tests
