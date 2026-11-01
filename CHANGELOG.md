# Changelog

## [0.5.2] - 2026-11-01

### Fixed
- **Disconnect Callback State Ordering (Eager Reconnect Fix):**
  - Set `self._connectionState = ConnectionState.NONE` before executing `self._disconnectedCallback()` in `_client.py`.
  - Fixes race condition where eager background tasks in Python 3.12+ / Home Assistant run `reconnect()` while `_connectionState` is still `AUTHENTICATED`, causing `reconnect()` to return early without reconnecting and leaving the mesh disconnected.
  - Avoids overwriting newly established connection state if an eager callback immediately restores the connection.
- **BlueZ D-Bus Resource Cleanup on Disconnection:**
  - Removed `is_connected` guard on `_gattClient.disconnect()` in `_client.py` and `device.py`.
  - Ensures Bleak always invokes `disconnect()` to cleanly unregister notifications and release private D-Bus bus handles on Linux/BlueZ even after an unexpected link drop, preventing frozen key exchanges on subsequent reconnection attempts.

## [0.5.1] - 2026-11-01

### Added
- **Opcode & Address Command Constants (T-016):**
  - Added `TURN_LIGHT_ON_LONG = 0x81` and `TURN_LIGHT_OFF_LONG = 0x82` to `CasambiCommands` enum.
  - Documented observed vs exposed opcodes (`TURN_LIGHT_ON`, `TURN_LIGHT_OFF`, `GET_DEVICE_INFO`, `GET_NETWORK_INFO`) in `CasambiCommands` docstring and `docs/protocol.md`.
  - Added golden vectors for `TURN_LIGHT_ON_LONG` and `TURN_LIGHT_OFF_LONG` in `fixtures/golden_vectors.json`.
  - Added AST introspection test ensuring every command opcode dispatched via `CasambiDevice._send_command` is covered in golden vectors.
- **Hardware Compatibility Matrix & Vector Provenance (T-017):**
  - Added Command Variant & Hardware Compatibility Matrix to `docs/protocol.md` detailing 1-byte vs 2-byte unit ID payload layouts, verified models, and capture provenance across verified Classic models.
  - Added `provenance` field (`"captured"` or `"derived"`) to every entry in `fixtures/golden_vectors.json`.
  - Added automated test asserting provenance declarations across all protocol fixture entries.
  - Linked hardware section in `README.md` to the compatibility matrix in `docs/protocol.md`.
- **Quality Gates, Strict Typing & Client Test Suite (Q-001, Q-002, Q-006, Q-007):**
  - Enforced `strict = true` in Mypy across all source files and aligned `AGENTS.md` gate specifications.
  - Added extensive unit tests for `CasambiClientClassic` covering device info unpacking (`>8sBBBBB`), transient GATT read retries, authentication state transition and counter bumps, manager vs visitor key CMAC digest lengths, and disconnected error handling, raising `_client.py` test coverage to 92%.
  - Added automated AST and signature validation for all fenced Python snippets in `README.md` (`Q-006`).
  - Added release hygiene test ensuring `CHANGELOG.md` always has an entry for the version in `pyproject.toml` (`Q-007`).

### Documentation
- **README & Quick-Start Accuracy (D-001, D-002):**
  - Fixed `CasambiCloud` quick-start snippet with valid constructor arguments (`email`, `api_key`, `user_password`, `network_password`) and valid session initialization calls (`create_user_session`, `create_network_session`, `get_network_information`).
  - Updated quick-start examples to demonstrate modern `try...except CasambiConnectionError` handling.
  - Added dedicated "Troubleshooting" section covering the single-GATT-connection limit when the official mobile Casambi app is open.

### Fixed
- **Address Parsing & Error Chaining in Direct Commands (T-016):**
  - Extracted `_parse_address_bytes()` helper in `device.py` validating 6-byte hexadecimal addresses (supporting colon, hyphen, or unseparated hex string formats) and raising `CasambiDeviceError` with chained `from err`.
  - Replaced raw `except Exception` blocks in `turn_on_by_address` and `turn_off_by_address`.

## [0.5.0] - 2026-11-01

### Added
- **API Surface Documentation (A-001):**
  - Added "Which API Should I Use?" comparative guide to `README.md` contrasting `CasambiDevice` vs `Casambi`.
  - Added signed session protocol specification to `docs/protocol.md` detailing handshake, key derivation, and signed packet layout.
- **Unified Exception Hierarchy (A-003):**
  - Consolidated exception classes into `casambi_classic_ble.exceptions` (`CasambiException`, `CasambiError`, `BluetoothError`, `AuthenticationError`, `ProtocolError`, `ConnectionStateError`, `NetworkNotFoundError`, `BluetoothDeviceNotFoundError`, `CasambiDeviceNotFoundError`, etc.) and re-exported all from package root `__init__.py`.
  - Converted `errors.py` into a backwards-compatible deprecation shim issuing `DeprecationWarning`.
- **Snake_case & Keyword-Only Public API (A-004):**
  - Modernized `Casambi`, `KeyStore`, `Network`, `Unit`, `Group`, `Scene`, and `Cache` with snake_case method and property names enforcing keyword-only arguments.
  - Provided backwards-compatible deprecated camelCase wrappers for legacy consumers (`setLevel`, `turnOn`, `setUuid`, etc.) issuing `DeprecationWarning`.
  - Added flexible parameter support for `Group` (`group_id`, `groupId`, `g_id`) and `Scene` (`scene_id`, `sceneId`, `s_id`).

### Removed
- **Evolution Protocol Code Removal (A-002):**
  - Completely removed Evolution-only code paths (`CasambiClientEvolution`, `OperationsContextEvolution`, unused `Encryptor`, etc.).
  - Protocol version checks in `_connect_client` now raise explicit `UnsupportedProtocolVersion` for protocol versions $\ge 10$ pointing users to upstream `casambi-bt`.
- **Dependency Graph Cleanup (A-005):**
  - Dropped unnecessary runtime dependency `multidict` from direct dependencies in `pyproject.toml`.

### Fixed
- **Cache Concurrency & Event Loop Safety (A-006):**
  - Replaced global lock with loop- and path-keyed lock registry `_get_cache_lock()` in `_cache.py`.
  - Added `get_default_cache_path()` resolving default cache location lazily at runtime rather than at import time.
- **Cloud Client Robustness (A-007):**
  - Added configurable `open_timeout` to WebSocket connection in `CasambiCloudWebSocket`.
  - Switched from MAC-derived `uuid.uuid1()` to `uuid.uuid4()` for client command references to safeguard privacy.
  - Mapped connection errors to `CasambiCloudApiException` and ensured clean connection state resetting on close.
  - Sanitized sensitive session tokens and credentials from debug logging.

## [0.4.0] - 2026-11-01

### Breaking Changes
- **Domain Exception Contract in `CasambiDevice` (T-010):**
  - `CasambiDevice.connect()` now returns `None` on success, and raises `CasambiDeviceNotFoundError` when device discovery fails or `CasambiConnectionError` when connection establishment fails (with chained root cause).
  - `CasambiDevice.read_status_char()` now returns `bytes` and raises `CasambiConnectionError` when disconnected or `CasambiDeviceError` on GATT read failure.
  - `CasambiDevice.get_device_info()` now returns `dict[str, str]` and raises `CasambiConnectionError` when disconnected or `CasambiDeviceError` on GATT read failure.
  - Removed error sentinel values (`False`, `None`) across `CasambiDevice`.
- **Required `unit_id` in Unit Commands (T-013):**
  - `CasambiDevice.set_color_temperature` and `CasambiDevice.set_rgb` now require `unit_id: int` as a mandatory keyword-only argument. Removed silent default to `unit_id=1`. Broadcast (`None`) is not supported by these opcodes and now rejected with explicit typing and validation.

### Added
- **Multi-Subscriber Notifications & Disconnections (T-015):**
  - Added `CasambiDevice.register_notification_callback` and `CasambiDevice.register_disconnect_callback` returning unsubscribe callables, matching `register_state_callback`.
  - Deprecated `set_notification_callback` and `set_disconnected_callback` with `DeprecationWarning`.
  - Stopped feeding raw advertisement bytes into GATT notification callbacks in `update_from_advertisement`.
- **Async State Queries (T-014):**
  - Added `CasambiDevice.request_state(*, unit_id: int, settle: float = 1.0) -> None` with configurable settle delay between queries `0x14` and `0x0F`. Incoming states arrive via registered state callbacks.
  - Deprecated `CasambiDevice.get_state` with `DeprecationWarning` pointing to `request_state`.
- **Fast Discovery Lookup (T-012):**
  - `CasambiDevice.connect()` now checks `bleak_retry_connector.get_device(address)` first before falling back to full `BleakScanner.discover` scanning, significantly speeding up reconnection times.
  - Imported `bleak_retry_connector` functions at module top level.
- **Connection Lifecycle & Injected Client Support (T-011):**
  - `CasambiDevice.is_connected` is now a property checking both internal connection state and `client.is_connected`, immediately reflecting connection drops on caller-injected clients.
  - Added `CasambiDevice.handle_disconnect()` to allow external managers (such as Home Assistant) to notify `CasambiDevice` when an injected client disconnects.
  - `CasambiDevice.disconnect()` and `handle_disconnect()` reset deduplication state (`_last_notified_states.clear()`) and clear references for non-injected clients, ensuring the first state update after reconnect is always delivered.

### Fixed
- **Callback Task Leak on Connection Failure (T-006):**
  - Delayed `self._callbackTask` creation in `CasambiClient.connect()` until after GATT connection is successfully established.
  - Added `_cleanup_callback_task()` to reliably cancel and await worker tasks upon failure or disconnection.

### Security & Hygiene
- **JSON Cache Migration & Backward Compatibility (S-001):** Migrated network session (`casambi_session.json`), unit types (`casambi_types.json`), and network ID (`casambi_network_id.txt`) from pickle to JSON. Automatically migrates legacy pickle files (`session.pck`, `types.pck`, `networkid`) on load with a `DeprecationWarning`, writes JSON with `0o600` permissions, and deletes legacy pickle files. Enforced `0o700` permissions on cache directories.
- **Sensitive Logging Sanitization (S-002):** Sanitized protocol logging across `device.py`, `_encryption.py`, `_client.py`, and `cloud/`. Raw notification frames, status reads, and packet payloads now log at `DEBUG` or behind `CASAMBI_TRACE`; `ClassicEncryptor.verify` never logs computed MAC on verification failure; and cloud session IDs are excluded from logs.
- **Dead Code Elimination & Password Validation (S-006):** Removed unreachable `self._session_key` field and dead XOR payload branch from `CasambiDevice`. Added validation to `CasambiDevice.authenticate(password=...)` requiring a non-empty password (raising `CasambiDeviceError`), and documented that write completion over GATT acknowledges transmission but is not explicit proof of authentication success.

## [0.3.6] - 2026-11-01

### Fixed
- Restricted `CasambiDevice.parse_status` to only parse verified status opcode `0x03` frames into unit states. Unhandled or non-status opcodes (e.g. `0x07`, `0x01`) safely return `{}` without overwriting `last_state` or corrupting unit tracking (T-003).
- Refactored advertisement address extraction into helper module `_adv.py`. Replaced substring matching with exact 6-byte normalized MAC matching against reversed (Quirk #1) and forward beacon byte order. Supported macOS CoreBluetooth UUID devices via direct `BLEDevice` matching and applied `cb={"use_bdaddr": True}` in `scanner.py` and `connect()`. Removed pseudo unit `id` from beacon status payloads (T-004).
- Verified 2-byte zero sequence wrap check in `CasambiClientClassic._sendInternal` skips `b"\x00\x00"` and consistently increments counter (T-005).

## [0.3.5] - 2026-11-01

### Fixed
- Fixed GATT notifications never reaching `register_state_callback` subscribers in `CasambiDevice` (T-002).
- Replaced global `_last_notified_state` tuple with per-unit deduplication dictionary to prevent multi-unit state collisions.
- Isolated exceptions in state change and raw notification callbacks to prevent subscriber crashes from breaking BLE notification processing.

## [0.3.4] - 2026-11-01

### Fixed
- Fixed 2-byte zero sequence wrap check in `CasambiClientClassic._sendInternal` (`b"\x00\x00"` -> `b"\x00\x01"`).
- Ordered exception handlers in `CasambiClient.connect()` most-specific first with explicit messages and error chaining (`from err`).
- Re-raised `asyncio.CancelledError` in `_processCallbacks`, replaced bare `except:` in `_connectClient`, and migrated `_activityLock` to `async with` context managers.
- Added bounds checks in `CasambiClientClassic._establishedNotifyCallback` before reading packet type and optional `extra1`/`extra2` fields.
- Replaced manual MAC byte comparison in `ClassicEncryptor.verify` with constant-time `hmac.compare_digest`.
- Replaced all runtime `assert` statements with explicit `ValueError` and `RuntimeError` raises for `PYTHONOPTIMIZE=1` safety.
- Dynamically read `casambi_classic_ble.__version__` from package metadata via `importlib.metadata.version`.

### Changed
- Added Python `3.14` to CI test matrix and enabled `filterwarnings = ["error"]` in pytest configuration.
- Standardized exception variable naming to `err` across all modules.

## [0.3.3] - 2026-10-31

### Changed
- Promoted package classifier to `Development Status :: 4 - Beta`.
- Restated supported hardware in documentation to exclusively reflect verified production hardware (Vadsbo LD220WCM, LD220WCM_onoff, Casambi CBU-PWM4 RGBW, AIMOTION GLOW).
- Command methods (`turn_on`, `turn_off`, `set_level`, `set_color_temperature`, `set_rgb`, `turn_on_by_address`, `turn_off_by_address`, `turn_on_broadcast`, `turn_off_broadcast`, `authenticate`) now return `None` on success and raise explicit domain exceptions (`CasambiCommandError`, `CasambiConnectionError`, `CasambiDeviceError`) on failure.
- Command methods accept `unit_id: int | None = None` where `None` indicates targeting all units (broadcast) across the network.
- Replaced upstream `CasambiBtError` naming with `CasambiClassicBleError` (retaining `CasambiBtError` backwards-compatibility alias).

### Added
- Added `CasambiDevice.register_state_callback` with duplicate frame suppression and isolated exception handling.
- Added comprehensive protocol golden-vector test fixtures covering all opcodes in `CasambiCommands`.
- Added `docs/protocol.md` detailing GATT services, opcodes, frame structures, and packet capture workflows.
- Serialized all GATT writes through `asyncio.Lock` to prevent interleaving packet chunks.
- Made `CasambiDevice.connect()` idempotent and `disconnect()` safe when unconnected.
- Supported injecting external `BleakClient` and `BLEDevice` into `CasambiDevice` with `bleak_retry_connector`.
- Added comprehensive project governance files (`SECURITY.md`, `CONTRIBUTING.md`, `.github/ISSUE_TEMPLATE/`).
- Added example script automated testing suite (`test_examples.py`).

## [0.3.2] - 2026-10-31

### Fixed
- Migrated `UnitControlType` to `IntEnum` for cross-package and integer interoperability.
- Added legacy pickle normalization for `types.pck` cache to guarantee `UnitControlType` instances match when unpickling fixtures cached by previous library versions.
- Safe enum comparison in `UnitType.get_control`, `Unit.setStateFromBytes`, and `Casambi.setUnitState`.

## [0.3.1] - 2026-10-31

### Fixed
- Resolved `UnboundLocalError` in `Casambi.connect` when formatting Bluetooth addresses without colons.

### Added
- Expanded unit test coverage to 82% branch coverage across 154 unit tests covering BLE operations, encryption, keystore, and cloud interfaces.
- Enforced 80% coverage threshold (`--cov-branch --cov-fail-under=80`) and pytest asyncio function fixture loop scope.
- Strict mypy type checking in CI pipeline and full type annotation compliance.

## [0.3.0] - 2026-10-31

### Added
- Initial standalone release of `casambi-classic-ble` fork, dedicated exclusively to Casambi Classic firmware networks.
- Classic BLE GATT service definitions (`0xFE3D`, `0xFE4D`) and passive advertisement decoder (`0x03C3`).
- Zero PII policy and TruffleHog secret scanning in CI and pre-commit hooks.

## [0.2.0] - 2026-10-31

### Changed
- Migrated repository structure to standard `src/` layout (`src/casambi_classic_ble`).
- Enforced keyword-only named arguments across all library public functions and methods.
- Upgraded dependencies and fixed Dependabot security alerts (`aiohttp>=3.14.4`, `multidict>=6.7.2`).

### Added
- Automated PyPI release workflow in GitHub Actions (draft release triggered on version bump, publish on release).
- Dependabot configuration with 2-day cooldown and assigned maintainer.
- Comprehensive contributor and AI coding guidelines in `AGENTS.md`.

## [0.1.0] - 2024-01-24

### Added
- Upstream baseline (`casambi-bt` legacy initial release).
