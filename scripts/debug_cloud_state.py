import asyncio
import yaml
import json
from casambi_classic_ble import CasambiCloud

async def debug_unit_state():
    with open("casambi.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    async with CasambiCloud(
        api_key=config["api_key"],
        email=config["email"],
        user_password=config["user_password"],
        network_password=config["network_password"]
    ) as cloud:
        await cloud.create_user_session()
        print("--- All Units in Network (Full Details) ---")
        net_state = await cloud.get_network_state()
        units = net_state.get("units", {})
        for uid, info in units.items():
            print(f"\nUNIT ID: {uid}")
            print(json.dumps(info, indent=2))

if __name__ == "__main__":
    asyncio.run(debug_unit_state())
