import asyncio
from bleak import BleakScanner
import time

TARGET_ID = "eef03db926a9"

async def monitor_target():
    print(f"--- Monitoring {TARGET_ID} (Husnummer) ---")
    last_payload = None
    
    def detection_callback(device, advertisement_data):
        nonlocal last_payload
        mfr = advertisement_data.manufacturer_data.get(963)
        if mfr and mfr.hex().startswith(TARGET_ID):
            payload = mfr.hex()
            if payload != last_payload:
                timestamp = time.strftime('%H:%M:%S')
                print(f"[{timestamp}] CHANGE DETECTED:")
                print(f"    Raw: {payload}")
                # Analyze common offsets
                flags = mfr[6]
                level = mfr[7]
                print(f"    Flags (byte 6): {flags:02x} (bin: {flags:08b})")
                print(f"    Level (byte 7): {level} ({level/2.55:.1f}%)")
                last_payload = payload

    scanner = BleakScanner(detection_callback)
    await scanner.start()
    await asyncio.sleep(120)
    await scanner.stop()

if __name__ == "__main__":
    asyncio.run(monitor_target())
