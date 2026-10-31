# Changelog

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
