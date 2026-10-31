# Casambi Classic BLE Library

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Firmware](https://img.shields.io/badge/firmware-Classic%20Casambi-orange.svg)](https://casambi.com)
[![Focus](https://img.shields.io/badge/focus-Classic%20BLE%20Networks-green.svg)](#why-this-fork-classic-vs-evolution)

A Python library for controlling Casambi lighting devices running **Classic firmware** via Bluetooth Low Energy (BLE).

> [!IMPORTANT]
> **Fork & Firmware Focus Notice**  
> This project is a specialized fork created specifically to focus on **Casambi Classic** networks and devices.  
> 
> Most modern open-source Casambi BLE libraries (such as `casambi-bt`) are designed exclusively for newer **Evolution** firmware networks. This library exists to fill the gap for installations that run legacy **Classic** firmware, providing dedicated BLE scanning, passive advertisement state tracking, and direct GATT control without requiring an upgrade to Evolution.

---

## Why This Fork? (Classic vs. Evolution)

Casambi networks run on one of two major firmware profiles: **Evolution** or **Classic**.

- **Evolution Networks:** Newer Casambi installations use the Evolution profile, which has different encryption, UUIDs, and network protocols. Libraries like [casambi-bt](https://github.com/lkempf/casambi-bt) are designed around Evolution.
- **Classic Networks (This Fork's Focus):** Many existing installations and older Casambi modules remain on Classic firmware. Upgrading is not always feasible or desirable. This fork is tailored to:
  - Communicate with Classic BLE GATT services and characteristics (`FE3D` and `FE4D`).
  - Parse Classic passive BLE advertisement frames (Manufacturer ID `0x03C3` / `963`) to monitor on/off state and brightness levels without polling.
  - Send direct BLE commands tailored to Classic device firmware (switching, dimming, color temperature, and RGB).
  - Provide optional Casambi Cloud API support for synchronizing network topologies and states.

> [!TIP]
> **Can I use evolution with this library?**
> - If your network runs **Evolution** firmware: Consider using [casambi-bt](https://github.com/lkempf/casambi-bt).

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

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Author

Olof Hellqvist <olof.hellqvist@gmail.com>
