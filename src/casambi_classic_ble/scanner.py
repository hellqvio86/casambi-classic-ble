"""Casambi BLE device scanner"""

import logging
import platform

from bleak import BleakScanner

from ._adv import CASAMBI_MANUFACTURER_ID, parse_advertisement
from .constants import CasambiUUIDs
from .device import CasambiDevice
from .utils import mask_mac

logger = logging.getLogger(__name__)


class CasambiScanner:
    """Scanner for discovering Casambi devices"""

    @staticmethod
    async def scan(*, duration: float = 5.0) -> list[CasambiDevice]:
        """
        Scan for Casambi devices

        Args:
            duration: Scan duration in seconds

        Returns:
            List of discovered CasambiDevice objects
        """
        devices = []
        logger.info(f"Scanning for Casambi devices ({duration}s)...")

        if platform.system() == "Darwin":
            discovered = await BleakScanner.discover(
                timeout=duration, return_adv=True, cb={"use_bdaddr": True}
            )
        else:
            discovered = await BleakScanner.discover(timeout=duration, return_adv=True)

        for device, adv_data in discovered.values():
            is_casambi = False
            uuids = [uuid.lower() for uuid in (adv_data.service_uuids or [])]

            # Check by Service UUID (V1 or V2)
            if CasambiUUIDs.SERVICE_V1.lower() in uuids or CasambiUUIDs.SERVICE_V2.lower() in uuids:
                is_casambi = True

            # Check by Manufacturer ID (963 = 0x03C3 Casambi)
            elif (
                adv_data.manufacturer_data
                and isinstance(adv_data.manufacturer_data, dict)
                and CASAMBI_MANUFACTURER_ID in adv_data.manufacturer_data
            ):
                is_casambi = True

            if is_casambi:
                mfr_data = (
                    adv_data.manufacturer_data.get(CASAMBI_MANUFACTURER_ID)
                    if adv_data.manufacturer_data and isinstance(adv_data.manufacturer_data, dict)
                    else None
                )
                parsed = (
                    parse_advertisement(mfr_data=mfr_data, company_id=CASAMBI_MANUFACTURER_ID)
                    if isinstance(mfr_data, (bytes, bytearray))
                    else None
                )
                if parsed is not None:
                    state_info = (
                        f" | State: {'ON' if parsed.is_on else 'OFF'} ({parsed.level_percent}%)"
                    )
                    is_debug = logger.isEnabledFor(logging.DEBUG)
                    logger.info(
                        "Discovered: %s (%s) | Internal: %s%s",
                        device.name,
                        mask_mac(device.address, is_debug=is_debug),
                        mask_mac(parsed.reversed_mac, is_debug=is_debug),
                        state_info,
                    )
                else:
                    logger.info(
                        "Discovered: %s (%s)",
                        device.name,
                        mask_mac(device.address, is_debug=logger.isEnabledFor(logging.DEBUG)),
                    )

                casambi_dev = CasambiDevice(address=device, name=device.name or "Casambi Device")
                if mfr_data:
                    casambi_dev.update_from_advertisement(mfr_data=mfr_data, ble_device=device)
                devices.append(casambi_dev)

        logger.info(f"Found {len(devices)} Casambi device(s)")
        return devices
