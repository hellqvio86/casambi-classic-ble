# Casambi Classic BLE Library

[![PyPI version](https://img.shields.io/pypi/v/casambi-classic-ble.svg)](https://pypi.org/project/casambi-classic-ble/)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Firmware](https://img.shields.io/badge/firmware-Classic%20Casambi-orange.svg)](https://casambi.com)
[![Fork](https://img.shields.io/badge/fork-Casambi%20Classic%20BLE-orange.svg)](https://github.com/hellqvio86/casambi-classic-ble)

An asynchronous Python library for controlling Casambi lighting devices running **Classic firmware** via Bluetooth Low Energy (BLE).

> [!NOTE]
> **Disclaimer:** This is an independent open-source project and is not affiliated with, endorsed by, or supported by Casambi Technologies Oy. Casambi is a registered trademark of Casambi Technologies Oy.

> [!IMPORTANT]
> **Primary Downstream Consumer:** This library serves as the core BLE engine for [`casambi-classic-bt-hass`](https://github.com/hellqvio86/casambi-classic-bt-hass), the Home Assistant integration for Classic Casambi meshes.

---

## Classic vs. Evolution Firmware

Casambi networks operate under one of two major radio profiles: **Evolution** or **Classic**.

### How to check your network profile
Open the official **Casambi App** → Select your network → **More** (`...`) → **Network setup** → **Network configuration** → Look at **Radio profile**:
- **Classic**: Use **`casambi-classic-ble`** (this library).
- **Evolution**: Use upstream [`casambi-bt`](https://github.com/lkempf/casambi-bt).

### Why this specialized fork exists
Classic networks rely on different GATT services (`0xFE3D`, `0xFE4D`), different challenge-handshakes, and passive manufacturer advertisement beacons (`0x03C3` / `963`). This library provides native, standalone support for Classic devices without cloud lock-in.

---

## Which API Should I Use?

`casambi-classic-ble` provides two client interfaces depending on your integration needs:

| Capability / Requirement | `CasambiDevice` | `Casambi` |
|---|---|---|
| **Primary Use Case** | Direct BLE GATT control for single nodes or mesh gateway | Full network topology discovery, scene switching, group control |
| **Downstream Consumer** | [`casambi-classic-bt-hass`](https://github.com/hellqvio86/casambi-classic-bt-hass) (Home Assistant) | Standalone network automation & scripting tools |
| **Cloud / Topology Dependency** | **Zero.** Connects directly via Bluetooth address. | Requires network configuration via Casambi Cloud or local cache. |
| **Authentication** | Optional network password write (`0x07` MD5 hash). | Challenge-response authentication with CMAC-signed packets & KeyStore. |
| **Unit Targeting** | Target any unit ID directly (`unit_id=1`). | High-level `Unit` and `Group` model instances. |
| **Scene Support** | Not supported directly. | Native `switch_to_scene()` support. |
| **State Feedback** | Passive BLE manufacturer advertisement beacons (`0x03C3`). | BLE GATT notification stream or Cloud WebSocket bridge. |
| **Verified Hardware** | Vadsbo LD220WCM, LD220WCM_onoff, CBU-PWM4, AIMOTION GLOW | Classic firmware networks (protocol versions 1–9). |

---

## Features

- 🎯 **Classic-First Architecture:** Tailored specifically for Casambi Classic firmware devices.
- 🔍 **BLE Discovery & Scanner:** Discover Classic Casambi nodes and decode passive manufacturer advertisement data.
- 📡 **Passive State Tracking:** Read on/off and dimming levels directly from BLE advertisements with duplicate frame suppression.
- 🔌 **Direct BLE Control:** Connect directly over Bluetooth Low Energy without mandatory cloud intermediaries.
- 💡 **Lighting Controls:** Turn lights on/off, set brightness dim levels, color temperature (Kelvin), and RGB colors.
- 🛡️ **Robust Concurrency:** Serialized GATT writes via `asyncio.Lock` and domain exception raising.
- ☁️ **Cloud Sync (Optional):** Optional Casambi Cloud API and WebSocket bridge for topology sync.

---

## Installation

```bash
pip install casambi-classic-ble
```

Or from source:

```bash
git clone https://github.com/hellqvio86/casambi-classic-ble.git
cd casambi-classic-ble
pip install -e .
```

---

## Quick Start

### 1. Controlling a Device by Address

```python
import asyncio
from casambi_classic_ble import CasambiConnectionError, CasambiDevice

async def main():
    # Target your node by Bluetooth address (or pass a Bleak BLEDevice from Home Assistant)
    light = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
    try:
        await light.connect()
    except CasambiConnectionError as err:
        print(f"Could not connect to {light.address}: {err}")
        return

    try:
        # Optional: Authenticate if your network requires a password
        # (Only needed if the network is password-protected and unauthenticated writes are rejected)
        # await light.authenticate(password="your_network_password")

        # Control a specific unit (e.g. Unit 1)
        await light.turn_on(unit_id=1)
        await light.set_level(unit_id=1, level=0.75)
        await light.set_color_temperature(unit_id=1, temp_kelvin=3000)
        await light.set_rgb(unit_id=1, r=255, g=200, b=100)

        # Or control all units across the mesh (omit unit_id or use broadcast)
        # await light.turn_on()
        # await light.turn_off()
    finally:
        await light.disconnect()

asyncio.run(main())
```

> [!NOTE]
> **Single Connection Limit:** Casambi nodes accept only **one active BLE connection** at a time. If the official Casambi mobile app is open, connections will time out (see [Troubleshooting](#troubleshooting)).

### 2. Discovery & Bring-Your-Own-Scanner (Home Assistant)

```python
import asyncio
from casambi_classic_ble import CasambiConnectionError, CasambiDevice, CasambiScanner

async def main():
    scanner = CasambiScanner()
    devices = await scanner.scan(duration=5.0)

    # Filter for your specific device by Bluetooth address rather than connecting blindly
    target = next((d for d in devices if d.address.upper() == "AA:BB:CC:DD:EE:FF"), None)
    if target:
        try:
            await target.connect()
            await target.turn_on(unit_id=1)
        except CasambiConnectionError as err:
            print(f"Failed to connect to {target.address}: {err}")
        finally:
            await target.disconnect()

asyncio.run(main())
```

### 3. Passive State Tracking & Subscriptions

```python
from casambi_classic_ble import CasambiDevice

device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")

def on_state_change(state: dict):
    # Decoded passive broadcast state dictionary containing verified status
    print(f"State updated: {'ON' if state['on'] else 'OFF'} ({state['level_percent']}%)")

# Register subscription callback (automatically deduplicates identical frames)
unsubscribe = device.register_state_callback(callback=on_state_change)

# Feed raw manufacturer data (0x03C3) received from Bleak or Home Assistant
def on_advertisement(mfr_data: bytes):
    device.update_from_advertisement(mfr_data=mfr_data)
```

### 4. Optional Cloud API Bridge

Install with cloud extras: `pip install casambi-classic-ble[cloud]`

```python
import asyncio
from casambi_classic_ble import CasambiCloud

async def main():
    # Required credentials:
    # - api_key: Casambi developer API key
    # - email & user_password: User account credentials
    # - network_password: Password of the specific lighting network
    async with CasambiCloud(
        api_key="your_api_key",
        email="user@example.com",
        user_password="password",
        network_password="network_password",
    ) as cloud:
        await cloud.create_user_session()
        await cloud.create_network_session()
        net_info = await cloud.get_network_information()
        print("Discovered cloud network information:", net_info)

asyncio.run(main())
```

---

## Operational Limitations & Hardware Compatibility

- **Reverse-Engineered Wire Protocol:** Casambi does not publish an official specification for the Classic BLE GATT protocol. This library implements protocol behavior observed and verified via packet captures and production fixtures.
- **Tested Hardware & Firmware Scope:**
  - **Vadsbo LD220WCM** (Trailing-edge phase-cut dimmer, Classic FW `26.x`)
  - **Vadsbo LD220WCM_onoff** (On/off relay module, Classic FW `26.x`)
  - **Casambi CBU-PWM4 RGBW** (4-channel PWM dimmer, Classic FW `26.x`)
  - **AIMOTION GLOW** (Pendant luminaire, Classic FW `26.x`)
  - **EnOcean PTM215B** (4-button kinetic BLE switch, Classic FW `20.x`–`26.x`)
  - *Supported protocol versions:* Classic firmware protocol versions `5`–`9` (and legacy `< 5` via direct GATT). Evolution firmware (`protocolVersion >= 10`) is explicitly rejected; use upstream [`casambi-bt`](https://github.com/lkempf/casambi-bt) for Evolution networks.
- **Single Active BLE Connection Limit:** Casambi mesh nodes accept only **one active Bluetooth Low Energy GATT connection** at a time. If the official Casambi mobile app (iOS or Android) or another BLE client is actively connected to the gateway node, connection attempts from `casambi-classic-ble` will time out or be rejected until the app disconnects.
- **Local BLE Control vs. Cloud Topology Sync:**
  - **`CasambiDevice` (Direct BLE):** Operates 100% locally over BLE with zero cloud or cache dependencies, targeting unit IDs directly.
  - **`Casambi` (Full Network Session):** Uses BLE GATT for real-time control and state notifications, and fetches network topology (unit names, groups, scenes, fixture profiles, and Visitor/Manager signing keys) from the Casambi API on initial login.
- **What "Offline Mode" (`force_offline=True`) Requires:**
  - Offline mode on `Casambi.connect(..., force_offline=True)` requires a **previously populated local cache** for that network UUID (`casambi_network_id.txt`, `<network_id>.json` topology, `casambi_lookup.json` keys, and `casambi_types.json` unit control definitions).
  - First-time network discovery, password changes (re-authentication), or newly added fixtures/groups/scenes cannot be discovered offline and require an online sync.
- **Protocol Details & Provenance:** See [docs/protocol.md](docs/protocol.md) for the complete [Command Variant & Hardware Compatibility Matrix](docs/protocol.md#3-command-variant--hardware-compatibility-matrix), characteristic UUIDs, signed session packets, and Wireshark capture guides.

---

## Safe Troubleshooting & Diagnostics

### 1. Connection Times Out While Casambi App Is Open
Because Casambi nodes only allow a single active GATT connection, force-close or background-disconnect the official Casambi mobile app on any nearby phones or tablets before connecting with `casambi-classic-ble` or Home Assistant.

### 2. Linux / BlueZ Adapter Requirements
- **BlueZ Version:** BlueZ `>= 5.64` is strongly recommended for reliable BLE GATT operation and notification cleanup.
- **D-Bus Permissions:** Non-root users on Linux may need `bluetooth` group membership:
  ```bash
  sudo usermod -a -G bluetooth $USER
  ```
- **RF Range & Proxies:** Ensure the host Bluetooth adapter (or ESPHome Bluetooth proxy when using [`casambi-classic-bt-hass`](https://github.com/hellqvio86/casambi-classic-bt-hass)) has stable RF signal (`RSSI > -80 dBm`) to at least one mesh node.

### 3. Sharing Logs Safely (Redacting Secrets & Identifiers)
- **Never publish plaintext network passwords, AES keys (`visitorKey` / `managerKey`), session tokens, raw unredacted packet captures (`.pcap` / `.btsnoop`), or real Bluetooth MAC addresses in public GitHub issues.**
- At standard `INFO` / `WARNING` / `ERROR` log levels, `casambi-classic-ble` automatically masks MAC addresses (`AA:**:**:**:**:FF`) and redacts credentials via `mask_mac` and `mask_sensitive_data`.
- When `logging.DEBUG` is enabled for local troubleshooting, full MAC addresses and debug payloads are logged to assist diagnosis—always sanitize (`AA:BB:CC:DD:EE:FF`, `<REDACTED>`) before sharing debug snippets externally.

---

## Contributing & Security

- **Contributing:** See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) for development setup, coding standards, and pull request guidelines.
- **Security Policy:** See [SECURITY.md](SECURITY.md) for vulnerability disclosure procedures and private reporting channels.
- **Protocol Documentation:** See [docs/protocol.md](docs/protocol.md) for packet formats, opcode tables, and Wireshark capture guides.

---

## Acknowledgements & Attribution

This library is a specialized fork of [`casambi-bt`](https://github.com/lkempf/casambi-bt), originally created by **Lukas Kempf** ([@lkempf](https://github.com/lkempf)). We are immensely grateful to Lukas Kempf and the upstream contributors for their pioneering reverse-engineering and BLE protocol architecture.

See [ATTRIBUTION.md](ATTRIBUTION.md) for detailed attribution and fork history.

## Authors & Maintainers

- **Lukas Kempf** ([@lkempf](https://github.com/lkempf)) — Original author and creator of `casambi-bt`
- **Olof Hellqvist** ([@hellqvio86](https://github.com/hellqvio86), <olof.hellqvist@gmail.com>) — Maintainer of the `casambi-classic-ble` fork

## License

This project is licensed under the Apache License, Version 2.0 — see the [LICENSE](LICENSE) file for the full text.
