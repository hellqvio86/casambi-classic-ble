"""Scan for Casambi devices"""

import asyncio

from casambi_classic_ble import CasambiScanner


async def main() -> None:
    scanner = CasambiScanner()
    print("Scanning for Casambi devices...")

    devices = await scanner.scan(duration=5.0)

    print(f"\nFound {len(devices)} device(s):")
    for device in devices:
        print(f"  - {device.name} ({device.address})")


if __name__ == "__main__":
    asyncio.run(main())

