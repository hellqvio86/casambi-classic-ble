import asyncio
from bleak import BleakScanner
import time

async def scan_diagnostic():
    print("--- Diagnostic BLE Scan (ID 963 / Casambi) ---")
    
    def detection_callback(device, advertisement_data):
        mfr = advertisement_data.manufacturer_data.get(963)
        if mfr:
            print(f"[{time.strftime('%H:%M:%S')}] Dev: {device.address} ({device.name})")
            print(f"    Raw Mfr Data: {mfr.hex()}")
            if len(mfr) >= 8:
                internal_id = mfr[:6].hex()
                flags = mfr[6]
                is_on = flags & 0x01
                level = mfr[7]
                pct = round((level / 255.0) * 100)
                target_marker = "*** TARGET ***" if internal_id == "eef03db926a9" else ""
                print(f"    Internal ID: {internal_id} {target_marker}")
                print(f"    State: {'ON' if is_on else 'OFF'} | Level: {level} ({pct}%) | Flags: {flags:02x}")

    scanner = BleakScanner(detection_callback, scanning_mode="active")
    await scanner.start()
    for _ in range(12):
        print(f"[{time.strftime('%H:%M:%S')}] Scanner heartbeat...")
        await asyncio.sleep(5)
    await scanner.stop()

if __name__ == "__main__":
    asyncio.run(scan_diagnostic())
