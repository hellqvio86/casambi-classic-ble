# Casambi Classic BLE Library

A Python library for controlling Casambi lighting devices with classic firmware via Bluetooth Low Energy (BLE).

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Features

- 🔍 Discover Casambi devices on the network
- 🔌 Connect to devices via BLE
- 💡 Control lighting (on/off, brightness)
- 🎨 RGB color control
- 🌡️ Color temperature adjustment
- 📡 Real-time notifications from devices
- ✅ Classic firmware support

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
    # Scan for devices
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

### Setup

```bash
./test.sh setup
```

### Run Tests

```bash
./test.sh test
```

### Run All Checks

```bash
./test.sh all
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Author

Olof Hellqvist <olof.hellqvist@gmail.com>
