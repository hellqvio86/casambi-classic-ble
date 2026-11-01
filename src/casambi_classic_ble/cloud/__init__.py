"""Casambi Cloud Client Implementation"""

import logging
from types import TracebackType
from typing import Any

import aiohttp

from ..exceptions import CasambiCloudApiException
from ..utils import DEFAULT_SENSITIVE_KEYS, mask_sensitive_data
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

        self._session: aiohttp.ClientSession | None = None
        self._api: CasambiCloudAPI | None = None
        self._ws: CasambiCloudWebsocket | None = None

    async def __aenter__(self) -> "CasambiCloud":
        self._session = aiohttp.ClientSession()
        self._api = CasambiCloudAPI(api_key=self.api_key, session=self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close connection resources."""
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
            self._session = None
        self._api = None
        self._ws = None

    @property
    def network_id(self) -> str | None:
        return self._api.network_id if self._api else None

    @property
    def connected(self) -> bool:
        return self._ws.connected if self._ws else False

    async def create_user_session(self) -> str:
        """Create user session."""
        if not self._api:
            self._session = aiohttp.ClientSession()
            self._api = CasambiCloudAPI(api_key=self.api_key, session=self._session)
        return await self._api.create_user_session(email=self.email, password=self.user_password)

    async def create_network_session(self) -> list[str]:
        """Create network session."""
        if not self._api:
            self._session = aiohttp.ClientSession()
            self._api = CasambiCloudAPI(api_key=self.api_key, session=self._session)
        return await self._api.create_network_session(
            email=self.email, password=self.network_password
        )

    def _ensure_api(self) -> CasambiCloudAPI:
        if not self._api:
            raise CasambiCloudApiException("Session not created. Call create_session first.")
        return self._api

    async def get_network_information(self) -> dict[str, Any]:
        return await self._ensure_api().get_network_information()

    async def get_network_state(self) -> dict[str, Any]:
        return await self._ensure_api().get_network_state()

    async def get_unit_list(self) -> list[dict[str, Any]]:
        return await self._ensure_api().get_unit_list()

    async def get_unit_state(self, *, unit_id: int) -> dict[str, Any]:
        return await self._ensure_api().get_unit_state(unit_id=unit_id)

    async def get_scenes_list(self) -> list[dict[str, Any]]:
        return await self._ensure_api().get_scenes_list()

    async def ws_open(self) -> bool:
        """Open websocket connection."""
        if not self._api or not self._api.network_id or not self._api.session_id:
            raise CasambiCloudApiException("Login required before opening websocket.")

        self._ws = CasambiCloudWebsocket(
            api_key=self.api_key,
            network_id=self._api.network_id,
            session_id=self._api.session_id,
            wire_id=self.wire_id,
        )
        return await self._ws.open()

    async def ws_receive_messages(self, *, timeout: float = 0.5) -> list[dict[str, Any]]:
        if not self._ws:
            return []
        return await self._ws.receive_messages(timeout=timeout)

    async def ws_close(self) -> None:
        if self._ws:
            await self._ws.close()

    async def turn_unit_on(self, *, unit_id: int) -> None:
        await self.set_unit_value(unit_id=unit_id, value=1.0)

    async def turn_unit_off(self, *, unit_id: int) -> None:
        await self.set_unit_value(unit_id=unit_id, value=0.0)

    async def set_unit_value(self, *, unit_id: int, value: float) -> None:
        if not self._ws:
            raise CasambiCloudApiException("Websocket connection required for control.")
        target_controls = {"Dimmer": {"value": value}}
        await self._ws.send_command(unit_id=unit_id, target_controls=target_controls)


__all__ = [
    "CasambiCloud",
    "CasambiCloudAPI",
    "CasambiCloudWebsocket",
    "DEFAULT_SENSITIVE_KEYS",
    "mask_sensitive_data",
]
