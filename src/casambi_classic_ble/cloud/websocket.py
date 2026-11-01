"""Casambi Cloud Websocket handler."""

import asyncio
import json
import logging
import uuid
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.typing import Subprotocol

from ..exceptions import CasambiCloudApiException
from ..utils import mask_sensitive_data

_LOGGER = logging.getLogger(__name__)


class CasambiCloudWebsocket:
    """Handles Websocket communication with Casambi Cloud."""

    def __init__(
        self,
        *,
        api_key: str,
        network_id: str,
        session_id: str,
        wire_id: int = 1,
    ) -> None:
        self.api_key = api_key
        self.network_id = network_id
        self.session_id = session_id
        self.wire_id = wire_id
        self.web_sock: ClientConnection | None = None
        self.connected = False

    async def open(self, *, open_timeout: float = 10.0) -> bool:
        """Open websocket connection to Casambi Bridge.

        :param open_timeout: Timeout in seconds for connection and opening handshake.
        :return: True if wire opened successfully, False otherwise.
        :raises CasambiCloudApiException: On connection failure, timeout, or network error.
        """
        url = "wss://door.casambi.com/v1/bridge/"
        reference = str(uuid.uuid4())

        message = {
            "method": "open",
            "id": self.network_id,
            "session": self.session_id,
            "ref": reference,
            "wire": self.wire_id,
            "type": 1,
        }

        try:
            async with asyncio.timeout(open_timeout):
                self.web_sock = await websockets.connect(
                    url, subprotocols=[Subprotocol(self.api_key)]
                )
                await self.web_sock.send(json.dumps(message))
                result = await self.web_sock.recv()
        except TimeoutError as err:
            self.connected = False
            if self.web_sock:
                await self.web_sock.close()
                self.web_sock = None
            raise CasambiCloudApiException("Websocket connection timed out.") from err
        except (OSError, websockets.WebSocketException, Exception) as err:
            self.connected = False
            if self.web_sock:
                await self.web_sock.close()
                self.web_sock = None
            raise CasambiCloudApiException(f"Failed to open websocket: {err}") from err

        data = json.loads(result)
        safe_data = mask_sensitive_data(data=data)
        _LOGGER.debug("ws_open response: %s", safe_data)

        if data.get("wireStatus") == "openWireSucceed":
            self.connected = True
            return True

        self.connected = False
        return False

    async def send_command(self, *, unit_id: int, target_controls: dict[str, Any]) -> None:
        """Send a control command over websocket.

        :raises CasambiCloudApiException: If websocket is not connected.
        """
        if not self.web_sock or not self.connected:
            raise CasambiCloudApiException("Websocket not connected.")

        message = {
            "wire": self.wire_id,
            "method": "controlUnit",
            "id": int(unit_id),
            "targetControls": target_controls,
        }
        await self.web_sock.send(json.dumps(message))

    async def receive_messages(self, *, timeout: float = 0.5) -> list[dict[str, Any]]:
        """Receive pending messages from websocket."""
        messages: list[dict[str, Any]] = []
        if not self.web_sock or not self.connected:
            return messages

        while True:
            try:
                msg = await asyncio.wait_for(self.web_sock.recv(), timeout=timeout)
                data = json.loads(msg)
                messages.append(data)

                # Human readable logging without leaking secrets
                if data.get("method") == "unitChanged":
                    _LOGGER.info("CLOUD UPDATE: Unit %s state changed", data.get("id"))
                elif data.get("method") == "controlUnit":
                    _LOGGER.info("CLOUD CONTROL: Unit %s command ACK", data.get("id"))

                timeout = 0.05
            except TimeoutError:
                break
            except (websockets.ConnectionClosed, ConnectionResetError):
                self.connected = False
                break
        return messages

    async def close(self) -> None:
        """Close websocket connection."""
        self.connected = False
        if self.web_sock:
            message = {"method": "close", "wire": self.wire_id}
            try:
                await self.web_sock.send(json.dumps(message))
            except (websockets.ConnectionClosed, OSError):
                pass
            try:
                await self.web_sock.close()
            except (websockets.ConnectionClosed, OSError):
                pass
            self.web_sock = None
