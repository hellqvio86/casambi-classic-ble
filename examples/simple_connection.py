"""Simple connection example"""

import asyncio
from casambi_classic_ble import CasambiScanner


async def main():
    # Scan for devices
    scanner = CasambiScanner()
    devices = await scanner.scan(duration=5.0)
    
    if not devices:
        print("No devices found")
        return
    
    # Connect to first device
    light = devices[0]
    print(f"Connecting to: {light.name}")
    
    if await light.connect():
        print("✓ Connected!")
        
        try:
            await light.turn_on()
            await asyncio.sleep(2)
            
            await light.set_level(unit_id=1, level=0.75)
            await asyncio.sleep(2)
            
            await light.turn_off()
            
        finally:
            await light.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
