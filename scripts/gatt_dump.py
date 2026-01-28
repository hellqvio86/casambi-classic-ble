import asyncio
from bleak import BleakClient, BleakScanner
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gatt_dump")

TARGET = "A9:26:B9:3D:F0:EE"

async def dump_gatt():
    print(f"Connecting to {TARGET}...")
    async with BleakClient(TARGET, timeout=20.0) as client:
        print(f"Connected: {client.is_connected}")
        for service in client.services:
            print(f"Service: {service.uuid} ({service.description})")
            for char in service.characteristics:
                print(f"  Char: {char.uuid} ({char.description}) {char.properties}")
                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char.uuid)
                        print(f"    Value: {value.hex()}")
                    except Exception as e:
                        print(f"    Read Error: {e}")

if __name__ == "__main__":
    asyncio.run(dump_gatt())
