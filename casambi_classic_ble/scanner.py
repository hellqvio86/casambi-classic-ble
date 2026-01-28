"""Casambi BLE device scanner"""

import logging
from typing import List
from bleak import BleakScanner

from .device import CasambiDevice
from .constants import CasambiUUIDs

logger = logging.getLogger(__name__)


class CasambiScanner:
    """Scanner for discovering Casambi devices"""

    @staticmethod
    async def scan(duration: float = 5.0) -> List[CasambiDevice]:
        """
        Scan for Casambi devices

        Args:
            duration: Scan duration in seconds

        Returns:
            List of discovered CasambiDevice objects
        """
        devices = []
        logger.info(f"Scanning for Casambi devices ({duration}s)...")

        discovered = await BleakScanner.discover(timeout=duration, return_adv=True)

        for device, adv_data in discovered.values():
            is_casambi = False
            uuids = [uuid.lower() for uuid in (adv_data.service_uuids or [])]
            
            # Check by Service UUID (Classic or Evolution)
            if CasambiUUIDs.SERVICE_V1.lower() in uuids or \
               CasambiUUIDs.SERVICE_V2.lower() in uuids:
                is_casambi = True
            
            # Check by Manufacturer ID (963 = 0x03C3 Casambi)
            elif 963 in adv_data.manufacturer_data:
                is_casambi = True
                
            if is_casambi:
                mfr_data = adv_data.manufacturer_data.get(963)
                state_info = ""
                if mfr_data and len(mfr_data) >= 8:
                    # Parse Passive State
                    real_address = ":".join(f"{b:02X}" for b in mfr_data[:6])
                    dim_level_byte = mfr_data[7]
                    is_on = mfr_data[6] & 0x01
                    pct = round((dim_level_byte / 255.0) * 100)
                    state_info = f" | State: {'ON' if is_on else 'OFF'} ({pct}%)"
                    logger.info(f"Discovered: {device.name} ({device.address}) | Internal: {real_address}{state_info}")
                else:
                    logger.info(f"Discovered: {device.name} ({device.address})")
                
                casambi_dev = CasambiDevice(
                    address=device, name=device.name or "Casambi Device"
                )
                if mfr_data:
                    casambi_dev.update_from_advertisement(mfr_data)
                devices.append(casambi_dev)

        logger.info(f"Found {len(devices)} Casambi device(s)")
        return devices
