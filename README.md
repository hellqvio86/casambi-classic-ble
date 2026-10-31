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
from casambi_classic_ble import CasambiDevice

async def main():
    # Target your node by Bluetooth address (or pass a Bleak BLEDevice from Home Assistant)
    light = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
    await light.connect()

    try:
        # Optional: Authenticate if your network requires a password
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

### 2. Discovery & Bring-Your-Own-Scanner (Home Assistant)

```python
import asyncio
from casambi_classic_ble import CasambiScanner, CasambiDevice

async def main():
    scanner = CasambiScanner()
    devices = await scanner.scan(duration=5.0)

    # Filter for your specific device by Bluetooth address rather than connecting blindly
    target = next((d for d in devices if d.address.upper() == "AA:BB:CC:DD:EE:FF"), None)
    if target:
        await target.connect()
        await target.turn_on(unit_id=1)
        await target.disconnect()

asyncio.run(main())
```

### 3. Passive State Tracking & Subscriptions

```python
from casambi_classic_ble import CasambiDevice

device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")

def on_state_change(state: dict):
    print(f"Unit {state['id']}: {'ON' if state['on'] else 'OFF'} ({state['level_percent']}%)")

# Register subscription callback (automatically deduplicates identical frames)
unsubscribe = device.register_state_callback(callback=on_state_change)

# Feed raw manufacturer data (0x03C3) received from Bleak or Home Assistant
def on_advertisement(mfr_data: bytes):
    device.update_from_advertisement(mfr_data=mfr_data)
```

### 4. Optional Cloud API Bridge

```python
import asyncio
from casambi_classic_ble import CasambiCloud

async def main():
    async with CasambiCloud(
        api_key="your_api_key",
        user_email="user@example.com",
        user_password="password",
    ) as cloud:
        networks = await cloud.get_networks()
        print("Discovered cloud networks:", networks)

asyncio.run(main())
```

---

## Hardware Compatibility & Limitations

- **Supported Hardware (Verified in Production):**
  - **Vadsbo LD220WCM** (Trailing-edge phase-cut dimmer)
  - **Vadsbo LD220WCM_onoff** (On/off relay module)
  - **Casambi CBU-PWM4 RGBW** (4-channel PWM dimmer)
  - **AIMOTION GLOW** (Pendant luminaire)
  - *All running Casambi Classic firmware (v26.x or earlier).*
- **Concurrent Connections:** Casambi mesh nodes typically allow only **one active BLE connection** at a time. If the official Casambi mobile app is actively connected to a node, connection attempts from other clients will be rejected until the app disconnects.
- **Protocol Details:** See [docs/protocol.md](docs/protocol.md) for characteristic UUIDs, opcodes, and Wireshark capture guides.

---

## Troubleshooting

- **Linux / BlueZ Permissions:** Non-root users may need permission to access Bluetooth adapters via D-Bus:
  ```bash
  sudo usermod -a -G bluetooth $USER
  ```
- **BlueZ Version:** BlueZ `>= 5.64` is strongly recommended for reliable BLE GATT operation and connection stability.
- **Connection Drops / Timeouts:** If connecting directly, ensure the target node is within adequate RF range and no mobile app has an active session open. Using [`casambi-classic-bt-hass`](https://github.com/hellqvio86/casambi-classic-bt-hass) leverages Home Assistant's proxying Bluetooth architecture automatically.

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
