import asyncio
import logging
import yaml
import os
from casambi_classic_ble import CasambiDevice, CasambiCloud, CasambiScanner

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("trigger_husnummer")
# Enable debug for the library
logging.getLogger("casambi_classic_ble").setLevel(logging.DEBUG)

CONFIG_FILE = "casambi.yaml"
TARGET_ADDRESS = "A9:26:B9:3D:F0:EE"

def parse_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)

async def check_cloud_state(cloud, unit_id):
    """Fetch state from Cloud API via REST."""
    try:
        await cloud.create_user_session()
        await cloud.create_network_session()
        state = await cloud.get_unit_state(unit_id=unit_id)
        dim = state.get("dimLevel", 0)
        logger.info(f"### CLOUD STATE (REST): Unit {unit_id} is {'ON' if dim > 0 else 'OFF'} ({dim*100:.1f}%) ###")
        return dim
    except Exception as e:
        logger.error(f"Failed to fetch cloud state: {e}")
        return None

async def check_ble_passive(unit_id):
    """Scan for the device and read state from broadcast data."""
    logger.info("### LOCAL PASSIVE SCAN START ###")
    found = await CasambiScanner.scan(duration=10.0)
    for d in found:
        if d.address.upper() == TARGET_ADDRESS.upper():
            state = d.last_state
            logger.info(f"### LOCAL STATE (BLE): Unit {state.get('id')} is {'ON' if state.get('on') else 'OFF'} ({state.get('level_percent')}%) ###")
            return state
    logger.warning(f"Target {TARGET_ADDRESS} not found in scan.")
    return None

async def main():
    config = parse_config()
    api_key = config.get("api_key")
    email = config.get("email")
    user_password = config.get("user_password")
    network_password = config.get("network_password")
    unit_id = config.get("unit_id", 12)

    async with CasambiCloud(
        api_key=api_key, email=email, 
        user_password=user_password, network_password=network_password
    ) as cloud:
        
        # Phase 1: Force OFF via Cloud
        logger.info("--- PHASE 1: FORCE OFF (CLOUD) ---")
        await cloud.create_user_session()
        await cloud.create_network_session()
        if await cloud.ws_open():
            await cloud.turn_unit_off(unit_id=unit_id)
            await asyncio.sleep(8)
            await check_cloud_state(cloud, unit_id)
            await check_ble_passive(unit_id)
            await cloud.ws_close()

        # Phase 2: Force ON via BLE
        logger.info("--- PHASE 2: FORCE ON (BLE) ---")
        device = CasambiDevice(TARGET_ADDRESS)
        if await device.connect():
            await device.authenticate(network_password)
            logger.info("CONNECTED. Sending turn_on(unit_id=12)")
            await device.turn_on(unit_id)
            await asyncio.sleep(2)
            await device.disconnect()
        
        logger.info("Waiting 15s for propagation...")
        await asyncio.sleep(15)
        
        # Final Validation
        await check_cloud_state(cloud, unit_id)
        await check_ble_passive(unit_id)

if __name__ == "__main__":
    asyncio.run(main())
