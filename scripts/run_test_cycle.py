#!/usr/bin/env python3
import asyncio
import sys
import yaml
import logging
import os
import json
import argparse
from bleak import BleakError

from casambi_classic_ble import CasambiDevice, CasambiScanner, CasambiCloud

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("test_cycle")

CONFIG_FILE = "casambi.yaml"
TARGET_NAME = "Husnummer"

def parse_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)

async def run_cycle():
    parser = argparse.ArgumentParser(description="Run Casambi test cycle")
    parser.add_argument("--address", help="BLE address of the device")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("casambi_classic_ble").setLevel(logging.DEBUG)

    config = parse_config()
    unit_id = config.get("unit_id", 12)
    logger.info(f"Targeting Unit ID: {unit_id} (Husnummer)")

    # Cloud session setup
    cloud = None
    if config.get("api_key") and config.get("email"):
        cloud = CasambiCloud(
            api_key=config["api_key"],
            email=config["email"],
            user_password=config["user_password"],
            network_password=config["network_password"]
        )
        await cloud.create_user_session()
        logger.info("Cloud session connected.")

    target_address = args.address or "EE:F0:3D:B9:26:A9"
    
    try:
        logger.info("--- STARTING HYBRID MONITORING (3 MINUTES) ---")
        logger.info(f"Monitoring BLE advertisements for {target_address} and Cloud state for Unit {unit_id}.")
        
        last_cloud_state = None
        
        for i in range(30): # 30 * 6s = 3 minutes
            # 1. Check Cloud
            if cloud:
                try:
                    unit_info = await cloud.get_unit_state(unit_id=unit_id)
                    c_dim = unit_info.get("dimLevel", 0)
                    current_state = f"{'ON' if c_dim > 0 else 'OFF'} ({c_dim*100:.0f}%)"
                    if current_state != last_cloud_state:
                         logger.info(f"### CLOUD: Unit {unit_id} is {current_state} ###")
                         last_cloud_state = current_state
                except:
                    pass

            # 2. Check BLE (Scanner now parses state in logs)
            try:
                await CasambiScanner.scan(duration=2.0)
            except Exception as e:
                logger.debug(f"Scan iteration failed: {e}")

            await asyncio.sleep(4)

    finally:
        if cloud:
            await cloud.close()
        logger.info("--- MONITORING ENDED ---")

if __name__ == "__main__":
    try:
        asyncio.run(run_cycle())
    except KeyboardInterrupt:
        pass
