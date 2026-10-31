# Casambi Classic BLE Library

[![PyPI version](https://img.shields.io/pypi/v/casambi-classic-ble.svg)](https://pypi.org/project/casambi-classic-ble/)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Firmware](https://img.shields.io/badge/firmware-Classic%20Casambi-orange.svg)](https://casambi.com)
[![Fork](https://img.shields.io/badge/fork-Casambi%20Classic%20BLE-orange.svg)](https://github.com/hellqvio86/casambi-classic-ble)

A Python library for controlling Casambi lighting devices running **Classic firmware** via Bluetooth Low Energy (BLE).

> [!IMPORTANT]
> **Standalone Fork Dedicated Exclusively to Casambi Classic Firmware**  
> This project is a specialized fork of the open-source Casambi BLE Python ecosystem (diverging from [lkempf/casambi-bt](https://github.com/lkempf/casambi-bt)).  
> 
> While upstream `casambi-bt` focuses on modern **Evolution** firmware networks, **this fork is dedicated specifically to legacy Casambi Classic networks**. Classic firmware uses distinct BLE GATT services (`0xFE3D`, `0xFE4D`), different cryptographic challenges, and passive manufacturer advertisement beacons (`0x03C3` / `963`).
> 
> - **Classic Networks (This Fork):** Use **`casambi-classic-ble`** ([hellqvio86/casambi-classic-ble](https://github.com/hellqvio86/casambi-classic-ble)).
> - **Evolution Networks:** Use upstream [lkempf/casambi-bt](https://github.com/lkempf/casambi-bt).

---

## Why This Fork? (Classic vs. Evolution)

Casambi networks run on one of two major firmware profiles: **Evolution** or **Classic**.

- **Evolution Networks:** Newer Casambi installations use the Evolution profile, which has different encryption, UUIDs, and network protocols. Upstream [casambi-bt](https://github.com/lkempf/casambi-bt) is designed around Evolution.
- **Classic Networks (This Fork's Exclusive Focus):** Many existing installations and older Casambi modules remain on Classic firmware. Upgrading is not always feasible or desirable. This fork is tailored to:
  - Communicate with Classic BLE GATT services and characteristics (`FE3D` and `FE4D`).
  - Parse Classic passive BLE advertisement frames (Manufacturer ID `0x03C3` / `963`) to monitor on/off state and brightness levels without polling.
  - Send direct BLE commands tailored to Classic device firmware (switching, dimming, color temperature, and RGB).
  - Provide optional Casambi Cloud API support for synchronizing network topologies and states.

> [!TIP]
> **Which library should you use?**
> - For **Classic** firmware networks: Use **`casambi-classic-ble`** ([hellqvio86/casambi-classic-ble](https://github.com/hellqvio86/casambi-classic-ble)).
> - For **Evolution** firmware networks: Use [lkempf/casambi-bt](https://github.com/lkempf/casambi-bt).

---

## Features

- 🎯 **Classic-First Architecture:** Tailored specifically for Casambi Classic firmware devices.
- 🔍 **BLE Discovery & Scanner:** Discover Classic Casambi nodes and decode passive manufacturer advertisement data.
- 📡 **Passive State Tracking:** Read on/off and dimming levels directly from BLE advertisements in real-time.
- 🔌 **Direct BLE Control:** Connect directly over Bluetooth Low Energy without mandatory cloud intermediaries.
- 💡 **Lighting Controls:** Turn lights on/off and set brightness dim levels.
- 🎨 **RGB & Color Temperature:** Adjust RGB colors and color temperature (Kelvin).
- ☁️ **Cloud Sync (Optional):** Integration with the Casambi Cloud API for session handling and topology inspection.

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

## Quick Start

```python
import asyncio
from casambi_classic_ble import CasambiScanner

async def main():
    # Scan for Classic Casambi devices
    scanner = CasambiScanner()
    devices = await scanner.scan(duration=5.0)
    
    if devices:
        # Connect to first device
        light = devices[0]
        await light.connect()
        
        # Control the light
        await light.turn_on()
        await light.set_level(unit_id=1, level=0.75)
        await light.set_color_temperature(unit_id=1, temp_kelvin=3000)
        
        # Disconnect
        await light.disconnect()

asyncio.run(main())
```

## Development

Using `make`:

```bash
# Set up development environment (syncs dependencies and installs git hooks)
make setup

# Or install the git commit hook directly
make hooks

# Run tests
make test

# Run linting and checks
make lint

# Run all checks
make all
```

## Acknowledgements & Attribution

This library is a specialized fork of [`casambi-bt`](https://github.com/lkempf/casambi-bt), originally created by **Lukas Kempf** ([@lkempf](https://github.com/lkempf)). We are immensely grateful to Lukas Kempf and the upstream contributors for their pioneering reverse-engineering and BLE protocol architecture.

See [ATTRIBUTION.md](ATTRIBUTION.md) for detailed attribution and fork history.

## Authors & Maintainers

- **Lukas Kempf** ([@lkempf](https://github.com/lkempf)) — Original author and creator of `casambi-bt`
- **Olof Hellqvist** ([@hellqvio86](https://github.com/hellqvio86), <olof.hellqvist@gmail.com>) — Maintainer of the `casambi-classic-ble` fork

## License

This project is licensed under the Apache License, Version 2.0 — see the [LICENSE](LICENSE) file for the full text.
