"""Casambi Cloud Client Implementation"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from ..exceptions import CasambiCloudApiException
from .api import CasambiCloudAPI
from .websocket import CasambiCloudWebsocket

_LOGGER = logging.getLogger(__name__)


class CasambiCloud:
    """
    Casambi Cloud API client. Acts as a facade for REST and Websocket modules.
    """

    def __init__(
        self,
        *,
        api_key: str,
        email: str,
        user_password: str,
        network_password: str,
        wire_id: int = 1,
    ):
        self.api_key = api_key
        self.email = email
        self.user_password = user_password
        self.network_password = network_password
        self.wire_id = wire_id

        self._session: Optional[aiohttp.ClientSession] = None
        self._api: Optional[CasambiCloudAPI] = None
        self._ws: Optional[CasambiCloudWebsocket] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        self._api = CasambiCloudAPI(self.api_key, self._session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close connection resources."""
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
            self._session = None
        self._api = None
        self._ws = None

    @property
    def network_id(self) -> Optional[str]:
        return self._api.network_id if self._api else None

    @property
    def connected(self) -> bool:
        return self._ws.connected if self._ws else False

    async def create_user_session(self) -> str:
        """Create user session."""
        if not self._api:
            self._session = aiohttp.ClientSession()
            self._api = CasambiCloudAPI(self.api_key, self._session)
        return await self._api.create_user_session(self.email, self.user_password)

    async def create_network_session(self) -> List[str]:
        """Create network session."""
        if not self._api:
            self._session = aiohttp.ClientSession()
            self._api = CasambiCloudAPI(self.api_key, self._session)
        return await self._api.create_network_session(self.email, self.network_password)

    async def get_network_information(self) -> Dict[str, Any]:
        return await self._api.get_network_information()

    async def get_network_state(self) -> Dict[str, Any]:
        return await self._api.get_network_state()

    async def get_unit_list(self) -> List[Dict[str, Any]]:
        return await self._api.get_unit_list()

    async def get_unit_state(self, *, unit_id: int) -> Dict[str, Any]:
        return await self._api.get_unit_state(unit_id)

    async def get_scenes_list(self) -> List[Dict[str, Any]]:
        return await self._api.get_scenes_list()

    async def ws_open(self) -> bool:
        """Open websocket connection."""
        if not self._api or not self._api.network_id or not self._api.session_id:
            raise CasambiCloudApiException("Login required before opening websocket.")

        self._ws = CasambiCloudWebsocket(
            self.api_key, self._api.network_id, self._api.session_id, self.wire_id
        )
        return await self._ws.open()

    async def ws_receive_messages(self, timeout: float = 0.5) -> List[Dict[str, Any]]:
        if not self._ws:
            return []
        return await self._ws.receive_messages(timeout)

    async def ws_close(self):
        if self._ws:
            await self._ws.close()

    async def turn_unit_on(self, *, unit_id: int):
        await self.set_unit_value(unit_id=unit_id, value=1.0)

    async def turn_unit_off(self, *, unit_id: int):
        await self.set_unit_value(unit_id=unit_id, value=0.0)

    async def set_unit_value(self, *, unit_id: int, value: float):
        if not self._ws:
            raise CasambiCloudApiException("Websocket connection required for control.")
        target_controls = {"Dimmer": {"value": value}}
        await self._ws.send_command(unit_id, target_controls)


__all__ = ["CasambiCloud"]
