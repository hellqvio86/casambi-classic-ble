"""Casambi Cloud REST API handler"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from ..exceptions import CasambiCloudApiException

_LOGGER = logging.getLogger(__name__)


class CasambiCloudAPI:
    """Handles REST API communication with Casambi Cloud"""

    def __init__(self, *, api_key: str, session: Optional[aiohttp.ClientSession] = None):
        self.api_key = api_key
        self._session = session
        self.network_id: Optional[str] = None
        self.session_id: Optional[str] = None

    def _get_headers(self, *, include_session: bool = True) -> Dict[str, str]:
        headers = {
            "Content-type": "application/json",
            "X-Casambi-Key": self.api_key,
        }
        if include_session and self.session_id:
            headers["X-Casambi-Session"] = self.session_id
        return headers

    async def create_user_session(self, *, email: str, password: str) -> str:
        """Create a user session."""
        url = "https://door.casambi.com/v1/users/session/"
        payload = {"email": email, "password": password}

        async with self._session.post(
            url, json=payload, headers=self._get_headers(include_session=False)
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise CasambiCloudApiException(
                    f"create_user_session failed: {response.status}, {text}"
                )

            data = await response.json()
            self.session_id = data["sessionId"]
            if data.get("networks"):
                self.network_id = list(data["networks"].keys())[0]

            _LOGGER.debug(f"User session created: {self.session_id}")
            return self.session_id

    async def create_network_session(self, *, email: str, password: str) -> List[str]:
        """Create a network session."""
        url = "https://door.casambi.com/v1/networks/session/"
        payload = {"email": email, "password": password}

        async with self._session.post(
            url, json=payload, headers=self._get_headers(include_session=False)
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise CasambiCloudApiException(
                    f"create_network_session failed: {response.status}, {text}"
                )

            data = await response.json()
            network_ids = list(data.keys())
            if network_ids:
                self.network_id = network_ids[0]
                self.session_id = data[self.network_id]["sessionId"]

            _LOGGER.debug(f"Network session created for {self.network_id}")
            return network_ids

    async def get_network_information(self) -> Dict[str, Any]:
        """Get network information."""
        if not self.network_id:
            raise CasambiCloudApiException("Network ID not set.")

        url = f"https://door.casambi.com/v1/networks/{self.network_id}"
        async with self._session.get(url, headers=self._get_headers()) as response:
            if response.status != 200:
                text = await response.text()
                raise CasambiCloudApiException(
                    f"get_network_information failed: {response.status}, {text}"
                )
            return await response.json()

    async def get_network_state(self) -> Dict[str, Any]:
        """Get network state."""
        if not self.network_id:
            raise CasambiCloudApiException("Network ID not set.")

        url = f"https://door.casambi.com/v1/networks/{self.network_id}/state"
        async with self._session.get(url, headers=self._get_headers()) as response:
            if response.status != 200:
                text = await response.text()
                raise CasambiCloudApiException(
                    f"get_network_state failed: {response.status}, {text}"
                )
            return await response.json()

    async def get_unit_list(self) -> List[Dict[str, Any]]:
        """Get list of units."""
        if not self.network_id:
            raise CasambiCloudApiException("Network ID not set.")

        url = f"https://door.casambi.com/v1/networks/{self.network_id}/units"
        async with self._session.get(url, headers=self._get_headers()) as response:
            if response.status != 200:
                text = await response.text()
                raise CasambiCloudApiException(f"get_unit_list failed: {response.status}, {text}")
            return await response.json()

    async def get_unit_state(self, *, unit_id: int) -> Dict[str, Any]:
        """Get specific unit state."""
        if not self.network_id:
            raise CasambiCloudApiException("Network ID not set.")

        url = f"https://door.casambi.com/v1/networks/{self.network_id}/units/{unit_id}/state"
        async with self._session.get(url, headers=self._get_headers()) as response:
            if response.status != 200:
                text = await response.text()
                raise CasambiCloudApiException(f"get_unit_state failed: {response.status}, {text}")
            return await response.json()

    async def get_scenes_list(self) -> List[Dict[str, Any]]:
        """Get list of scenes."""
        if not self.network_id:
            raise CasambiCloudApiException("Network ID not set.")

        url = f"https://door.casambi.com/v1/networks/{self.network_id}/scenes"
        async with self._session.get(url, headers=self._get_headers()) as response:
            if response.status != 200:
                text = await response.text()
                raise CasambiCloudApiException(f"get_scenes_list failed: {response.status}, {text}")
            return await response.json()
