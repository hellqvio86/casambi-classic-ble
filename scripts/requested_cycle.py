ogging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("control_cycle")

CONFIG_FILE = "casambi.yaml"
BLE_MAC = "A9:26:B9:3D:F0:EE"

def parse_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)

async def get_states(cloud, unit_id):
    """Fetch state from Cloud and BLE Scan"""
    # 1. Cloud State
    cloud_info = {"on": "UNKNOWN", "dim": 0}
    if cloud:
        try:
            state = await cloud.get_unit_state(unit_id=unit_id)
            c_dim = state.get("dimLevel", 0)
            cloud_info = {"on": "ON" if c_dim > 0 else "OFF", "dim": round(c_dim * 100)}
        except Exception as e:
            logger.warning(f"Cloud poll failed: {e}")

    # 2. BLE Local State (Passive Scan)
    ble_info = {"on": "UNKNOWN", "dim": 0}
    try:
        # Long scan to be super sure we catch it
        found = await CasambiScanner.scan(duration=8.0)
        target = next((d for d in found if BLE_MAC.lower() == d.address.lower()), None)
        
        if target and target.last_state:
            ble_info = {
                "on": "ON" if target.last_state.get("on") else "OFF",
                "dim": target.last_state.get("level_percent", 0)
            }
        else:
            logger.warning(f"Target device {BLE_MAC} not found in this scan.")
    except Exception as e:
        logger.warning(f"BLE scan failed: {e}")

    return cloud_info, ble_info

async def run_cycle():
    config = parse_config()
    unit_id = config.get("unit_id", 12)
    logger.info(f"Targeting Unit ID: {unit_id} (Husnummer)")

    async with CasambiCloud(
        api_key=config["api_key"],
        email=config["email"],
        user_password=config["user_password"],
        network_password=config["network_password"]
    ) as cloud:
        await cloud.create_user_session()
        
        # --- STEP 1: INITIAL STATE ---
        logger.info(">>> PHASE 1: Reading INITIAL State")
        c_state, b_state = await get_states(cloud, unit_id)
        logger.info(f"INITIAL | Cloud: {c_state['on']} ({c_state['dim']}%) | BLE: {b_state['on']} ({b_state['dim']}%)")

        # --- STEP 2: TURN ON ---
        logger.info(">>> PHASE 2: Turning Unit 12 ON (via Cloud)")
        if await cloud.ws_open():
            # Turn ON (100%)
            await cloud.set_unit_value(unit_id=unit_id, value=1.0)
            logger.info("Command SENT. Waiting 10s for mesh/cloud sync...")
            await asyncio.sleep(10)
            await cloud.ws_close()
        
        # --- STEP 3: VERIFY ON STATE ---
        logger.info(">>> PHASE 3: Verifying ON State")
        c_state, b_state = await get_states(cloud, unit_id)
        logger.info(f"POST-ON | Cloud: {c_state['on']} ({c_state['dim']}%) | BLE: {b_state['on']} ({b_state['dim']}%)")

        # --- STEP 4: TURN OFF ---
        logger.info(">>> PHASE 4: Turning Unit 12 OFF (via Cloud)")
        if await cloud.ws_open():
            await cloud.set_unit_value(unit_id=unit_id, value=0.0)
            logger.info("Command SENT. Waiting 10s for mesh/cloud sync...")
            await asyncio.sleep(10)
            await cloud.ws_close()

        # --- STEP 5: FINAL STATE ---
        logger.info(">>> PHASE 5: Reading FINAL State")
        c_state, b_state = await get_states(cloud, unit_id)
        logger.info(f"FINAL   | Cloud: {c_state['on']} ({c_state['dim']}%) | BLE: {b_state['on']} ({b_state['dim']}%)")

if __name__ == "__main__":
    asyncio.run(run_cycle())
