"""Casambi Cloud Websocket handler"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import websockets

_LOGGER = logging.getLogger(__name__)


class CasambiCloudWebsocket:
    """Handles Websocket communication with Casambi Cloud"""

    def __init__(self, api_key: str, network_id: str, session_id: str, wire_id: int = 1):
        self.api_key = api_key
        self.network_id = network_id
        self.session_id = session_id
        self.wire_id = wire_id
        self.web_sock: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False

    async def open(self) -> bool:
        """Open websocket connection to Casambi Bridge."""
        url = "wss://door.casambi.com/v1/bridge/"
        reference = str(uuid.uuid1())

        message = {
            "method": "open",
            "id": self.network_id,
            "session": self.session_id,
            "ref": reference,
            "wire": self.wire_id,
            "type": 1,
        }

        self.web_sock = await websockets.connect(url, subprotocols=[self.api_key])
        await self.web_sock.send(json.dumps(message))

        try:
            result = await self.web_sock.recv()
            data = json.loads(result)
            _LOGGER.debug(f"ws_open response: {data}")

            if data.get("wireStatus") == "openWireSucceed":
                self.connected = True
                return True
        except Exception as e:
            _LOGGER.error(f"Failed to open websocket: {e}")
            await self.web_sock.close()
            self.web_sock = None

        return False

    async def send_command(self, unit_id: int, target_controls: Dict[str, Any]):
        """Send a control command over websocket."""
        if not self.web_sock:
            raise RuntimeError("Websocket not connected")

        message = {
            "wire": self.wire_id,
            "method": "controlUnit",
            "id": int(unit_id),
            "targetControls": target_controls,
        }
        await self.web_sock.send(json.dumps(message))

    async def receive_messages(self, timeout: float = 0.5) -> List[Dict[str, Any]]:
        """Receive pending messages from websocket."""
        messages = []
        if not self.web_sock:
            return messages

        while True:
            try:
                msg = await asyncio.wait_for(self.web_sock.recv(), timeout=timeout)
                data = json.loads(msg)
                messages.append(data)

                # Human readable logging
                if data.get("method") == "unitChanged":
                    _LOGGER.info(f"CLOUD UPDATE: Unit {data.get('id')} state changed")
                elif data.get("method") == "controlUnit":
                    _LOGGER.info(f"CLOUD CONTROL: Unit {data.get('id')} command ACK")

                timeout = 0.05
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                break
        return messages

    async def close(self):
        """Close websocket connection."""
        if self.web_sock:
            message = {"method": "close", "wire": self.wire_id}
            try:
                await self.web_sock.send(json.dumps(message))
            except Exception:
                pass
            await self.web_sock.close()
            self.web_sock = None
            self.connected = False
