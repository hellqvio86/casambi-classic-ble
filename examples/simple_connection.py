"""Simple connection example"""

import asyncio

from casambi_classic_ble import CasambiConnectionError, CasambiScanner


async def main() -> None:
    # Scan for devices
    scanner = CasambiScanner()
    devices = await scanner.scan(duration=5.0)

    if not devices:
        print("No devices found")
        return

    # Connect to first device
    light = devices[0]
    print(f"Connecting to: {light.name}")

    try:
        await light.connect()
        print("✓ Connected!")
    except CasambiConnectionError as err:
        print(f"Failed to connect to {light.name}: {err}")
        return

    try:
        await light.turn_on()
        await light.set_level(unit_id=1, level=0.75)
        await light.turn_off()
    finally:
        await light.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

