import json
import logging
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
from httpx import AsyncClient, RequestError

from ._cache import Cache
from ._constants import (
    DEVICE_NAME,
    isClassicNetwork,
)
from ._constants import (
    LEGACY_NETWORK_ID_CACHE_FILE as LEGACY_NETWORK_ID_CACHE_FILE,
)
from ._constants import (
    LEGACY_SESSION_CACHE_FILE as LEGACY_SESSION_CACHE_FILE,
)
from ._constants import (
    LEGACY_TYPES_CACHE_FILE as LEGACY_TYPES_CACHE_FILE,
)
from ._constants import (
    NETWORK_ID_CACHE_FILE as NETWORK_ID_CACHE_FILE,
)
from ._constants import (
    SESSION_CACHE_FILE as SESSION_CACHE_FILE,
)
from ._constants import (
    TYPES_CACHE_FILE as TYPES_CACHE_FILE,
)
from ._keystore import KeyStore
from ._unit import Group, Scene, Unit, UnitControl, UnitControlType, UnitType
from .exceptions import (
    AuthenticationError,
    NetworkNotFoundError,
    NetworkOnlineUpdateNeededError,
    NetworkUpdateError,
)
from .utils import (
    async_atomic_write_file,
    set_secure_file_permissions,
    validate_safe_path,
)


@dataclass()
class _NetworkSession:
    session: str
    network: str
    manager: bool
    keyID: int
    expires: datetime

    role: int = 3  # TODO: Support other role types?

    def expired(self) -> bool:
        return datetime.now(UTC) > self.expires

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.session,
            "network": self.network,
            "manager": self.manager,
            "keyID": self.keyID,
            "expires": self.expires.isoformat(),
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_NetworkSession":
        if not isinstance(data, dict):
            raise ValueError(f"Session data must be a dict, got {type(data).__name__}")
        raw_expires = data.get("expires")
        if raw_expires is None:
            raise ValueError("Missing 'expires' field in session data")
        if isinstance(raw_expires, (int, float)):
            dt = datetime.fromtimestamp(raw_expires / 1000, UTC)
        else:
            dt = datetime.fromisoformat(str(raw_expires))
        session_val = data.get("session")
        if not isinstance(session_val, str):
            raise ValueError("Missing or invalid 'session' field in session data")
        network_val = data.get("network")
        if not isinstance(network_val, str):
            raise ValueError("Missing or invalid 'network' field in session data")
        return cls(
            session=session_val,
            network=network_val,
            manager=bool(data.get("manager", False)),
            keyID=int(data["keyID"]),
            expires=dt,
            role=int(data.get("role", 3)),
        )


class Network:
    def __init__(self, uuid: str, httpClient: AsyncClient, cache: Cache) -> None:
        self._session: _NetworkSession | None = None

        self._networkName: str | None = None
        self._networkRevision: int | None = None
        self._protocolVersion: int = -1

        self._unitTypes: dict[int, tuple[UnitType | None, datetime]] = {}
        self.units: list[Unit] = []
        self.groups: list[Group] = []
        self.scenes: list[Scene] = []

        self._logger = logging.getLogger(__name__)
        # TODO: Create LoggingAdapter to prepend uuid.

        self._id: str | None = None
        self._uuid = uuid
        self._httpClient = httpClient

        self._cache = cache

    async def load(self) -> None:
        self._keystore = KeyStore(self._cache)
        await self._keystore.load()

        await self._loadSession()
        await self._loadTypeCache()

    async def _loadSession(self) -> None:
        self._logger.debug("Loading session...")
        async with self._cache as cachePath:
            json_file = cachePath / SESSION_CACHE_FILE
            pickle_file = cachePath / LEGACY_SESSION_CACHE_FILE

            if await json_file.exists():
                validate_safe_path(json_file, base_path=cachePath)
                try:
                    raw_json = await json_file.read_text()
                    data = json.loads(raw_json)
                    if not isinstance(data, dict):
                        raise ValueError(
                            f"Expected dict in {SESSION_CACHE_FILE}, got {type(data).__name__}"
                        )
                    self._session = _NetworkSession.from_dict(data)
                    self._logger.info("Session loaded from JSON.")
                    return
                except (json.JSONDecodeError, ValueError, KeyError, TypeError) as err:
                    self._logger.warning(f"Failed to load session from JSON: {err}")

            if await pickle_file.exists():
                msg = (
                    f"Legacy pickle session cache '{LEGACY_SESSION_CACHE_FILE}' found, but pickle support "
                    f"was removed in v0.6.0 for security. Legacy cache is ignored; please re-authenticate."
                )
                warnings.warn(msg, UserWarning, stacklevel=2)
                self._logger.warning(msg)

    async def _save_session_to_cache(self, cachePath: Any) -> None:
        if self._session is None:
            return
        json_file = cachePath / SESSION_CACHE_FILE
        validate_safe_path(json_file, base_path=cachePath)
        await async_atomic_write_file(
            path=json_file,
            content=json.dumps(self._session.to_dict(), indent=2),
        )

    async def _save_session(self) -> None:
        self._logger.debug("Saving session...")
        async with self._cache as cachePath:
            await self._save_session_to_cache(cachePath)

    _saveSession = _save_session
    _saveSesion = _save_session

    async def _loadTypeCache(self) -> None:
        self._logger.debug("Loading unit type cache...")
        async with self._cache as cachePath:
            json_file = cachePath / TYPES_CACHE_FILE
            pickle_file = cachePath / LEGACY_TYPES_CACHE_FILE

            if await json_file.exists():
                validate_safe_path(json_file, base_path=cachePath)
                try:
                    raw_json = await json_file.read_text()
                    data = json.loads(raw_json)
                    if not isinstance(data, dict):
                        raise ValueError(
                            f"Expected dict in {TYPES_CACHE_FILE}, got {type(data).__name__}"
                        )
                    if len(data) > 1000:
                        raise ValueError(f"Too many unit types in cache ({len(data)} > 1000)")
                    clean_types: dict[int, tuple[UnitType | None, datetime]] = {}
                    for key_str, entry in data.items():
                        if not isinstance(entry, dict):
                            raise ValueError(f"Expected dict for unit type entry {key_str}")
                        type_id = int(key_str)
                        expiry = datetime.fromisoformat(str(entry["expires"]))
                        unit_type_dict = entry.get("unit_type")
                        if unit_type_dict is not None:
                            if not isinstance(unit_type_dict, dict):
                                raise ValueError(f"Expected dict for unit_type in {key_str}")
                            controls_data = unit_type_dict.get("controls")
                            if not isinstance(controls_data, list):
                                raise ValueError(f"Expected list for controls in {key_str}")
                            controls = [
                                UnitControl(
                                    type=UnitControlType(c["type"]),
                                    offset=int(c["offset"]),
                                    length=int(c["length"]),
                                    default=int(c["default"]),
                                    readonly=bool(c["readonly"]),
                                    min=c.get("min"),
                                    max=c.get("max"),
                                )
                                for c in controls_data
                            ]
                            unit_type = UnitType(
                                id=int(unit_type_dict["id"]),
                                model=str(unit_type_dict["model"]),
                                manufacturer=str(unit_type_dict["manufacturer"]),
                                mode=str(unit_type_dict["mode"]),
                                stateLength=int(unit_type_dict["stateLength"]),
                                controls=controls,
                            )
                        else:
                            unit_type = None
                        clean_types[type_id] = (unit_type, expiry)
                    self._unitTypes = clean_types
                    self._logger.info("Unit type cache loaded from JSON.")
                    return
                except (json.JSONDecodeError, ValueError, KeyError, TypeError) as err:
                    self._logger.warning(
                        f"Failed to load unit type cache from JSON, resetting: {err}",
                        exc_info=True,
                    )
                    self._unitTypes = {}
                    return

            if await pickle_file.exists():
                msg = (
                    f"Legacy pickle unit type cache '{LEGACY_TYPES_CACHE_FILE}' found, but pickle support "
                    f"was removed in v0.6.0 for security. Legacy cache is ignored; please re-query unit types."
                )
                warnings.warn(msg, UserWarning, stacklevel=2)
                self._logger.warning(msg)

    async def _save_type_cache_to_cache(self, cachePath: Any) -> None:
        data: dict[str, Any] = {}
        for type_id, (unit_type, expiry) in self._unitTypes.items():
            if unit_type is not None:
                controls_data = [
                    {
                        "type": c.type.value if hasattr(c.type, "value") else int(c.type),
                        "offset": c.offset,
                        "length": c.length,
                        "default": c.default,
                        "readonly": c.readonly,
                        "min": c.min,
                        "max": c.max,
                    }
                    for c in unit_type.controls
                ]
                unit_type_data: dict[str, Any] | None = {
                    "id": unit_type.id,
                    "model": unit_type.model,
                    "manufacturer": unit_type.manufacturer,
                    "mode": unit_type.mode,
                    "stateLength": unit_type.stateLength,
                    "controls": controls_data,
                }
            else:
                unit_type_data = None

            data[str(type_id)] = {
                "expires": expiry.isoformat(),
                "unit_type": unit_type_data,
            }

        json_file = cachePath / TYPES_CACHE_FILE
        validate_safe_path(json_file, base_path=cachePath)
        await async_atomic_write_file(
            path=json_file,
            content=json.dumps(data, indent=2),
        )

    async def _saveTypeCache(self) -> None:
        self._logger.debug("Saving type cache...")
        async with self._cache as cachePath:
            await self._save_type_cache_to_cache(cachePath)

    async def get_network_id(self, *, force_offline: bool = False) -> None:
        self._logger.info("Getting network id...")

        async with self._cache as cachePath:
            networkCacheFile = cachePath / NETWORK_ID_CACHE_FILE
            legacyNetworkCacheFile = cachePath / LEGACY_NETWORK_ID_CACHE_FILE

            if await networkCacheFile.exists():
                validate_safe_path(networkCacheFile, base_path=cachePath)
                self._id = await networkCacheFile.read_text()
            elif await legacyNetworkCacheFile.exists():
                validate_safe_path(legacyNetworkCacheFile, base_path=cachePath)
                self._id = await legacyNetworkCacheFile.read_text()
                # Migrate to new file with secure permissions and atomic write
                await async_atomic_write_file(path=networkCacheFile, content=self._id)
                try:
                    await legacyNetworkCacheFile.unlink()
                except Exception as err:
                    self._logger.debug(f"Could not migrate legacy network ID cache: {err}")

        if force_offline:
            if not self._id:
                raise NetworkOnlineUpdateNeededError("Network isn't cached.")
            else:
                return

        getNetworkIdUrl = f"https://api.casambi.com/network/uuid/{self._uuid}"
        try:
            res = await self._httpClient.get(getNetworkIdUrl)
        except RequestError as err:
            if not self._id:
                raise NetworkOnlineUpdateNeededError from err
            else:
                self._logger.warning(
                    "Network error while fetching network id. Continuing with cache.",
                    exc_info=True,
                )
                return

        if res.status_code == httpx.codes.NOT_FOUND:
            raise NetworkNotFoundError(
                "API failed to find network. Is your network configured correctly?"
            )
        if res.status_code != httpx.codes.OK:
            raise NetworkNotFoundError(
                f"Getting network id returned unexpected status {res.status_code}"
            )

        new_id = cast(str, res.json()["id"])
        if not isinstance(new_id, str) or not new_id.strip() or "/" in new_id or ".." in new_id:
            raise NetworkNotFoundError(f"Received invalid network ID format: {new_id}")

        if self._id != new_id:
            self._logger.info(f"Network id changed from {self._id} to {new_id}.")
            async with self._cache as cachePath:
                networkCacheFile = cachePath / NETWORK_ID_CACHE_FILE
                validate_safe_path(networkCacheFile, base_path=cachePath)
                await async_atomic_write_file(path=networkCacheFile, content=new_id)
            self._id = new_id
        self._logger.info(f"Got network id {self._id}.")

    async def getNetworkId(self, *args: Any, **kwargs: Any) -> None:
        """Deprecated alias for get_network_id."""
        warnings.warn(
            "getNetworkId is deprecated; use get_network_id instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        force_offline = (
            args[0] if args else kwargs.get("force_offline", kwargs.get("forceOffline", False))
        )
        return await self.get_network_id(force_offline=force_offline)

    def authenticated(self) -> bool:
        if not self._session:
            return False
        return not self._session.expired()

    @property
    def keyStore(self) -> KeyStore:
        return self._keystore

    @property
    def protocolVersion(self) -> int:
        return self._protocolVersion

    async def log_in(self, *, password: str, force_offline: bool = False) -> None:
        await self.get_network_id(force_offline=force_offline)

        # No need to be authenticated if we try to be offline anyway.
        if self.authenticated() or force_offline:
            return

        self._logger.info("Logging in to network...")
        getSessionUrl = f"https://api.casambi.com/network/{self._id}/session"

        res = await self._httpClient.post(
            getSessionUrl, json={"password": password, "deviceName": DEVICE_NAME}
        )
        if res.status_code == httpx.codes.OK:
            # Parse session
            sessionJson = res.json()
            sessionJson["expires"] = datetime.fromtimestamp(sessionJson["expires"] / 1000, UTC)
            self._session = _NetworkSession(**sessionJson)
            self._logger.info("Login successful.")
            await self._save_session()
        else:
            raise AuthenticationError(f"Login failed: {res.status_code}\n{res.text}")

    async def logIn(self, *args: Any, **kwargs: Any) -> None:
        """Deprecated alias for log_in."""
        warnings.warn("logIn is deprecated; use log_in instead.", DeprecationWarning, stacklevel=2)
        password = args[0] if len(args) > 0 else kwargs.get("password", "")
        force_offline = (
            args[1]
            if len(args) > 1
            else kwargs.get("force_offline", kwargs.get("forceOffline", False))
        )
        return await self.log_in(password=password, force_offline=force_offline)

    async def update(
        self, *args: Any, force_offline: bool = False, forceOffline: bool = False
    ) -> None:
        target_offline = force_offline or forceOffline or (args[0] if args else False)
        self._logger.info("Updating network...")
        if not self.authenticated() and not target_offline:
            raise AuthenticationError("Not authenticated!")

        if self._id is None:
            raise RuntimeError("Network id must be set.")

        # TODO: Save and send revision to receive actual updates?

        async with self._cache as cachePath:
            cachedNetworkPah = cachePath / f"{self._id}.json"
            if await cachedNetworkPah.exists():
                network = json.loads(await cachedNetworkPah.read_bytes())
                self._networkRevision = network["network"]["revision"]
                self._logger.info(f"Loaded cached network. Revision: {self._networkRevision}")
            else:
                if target_offline:
                    raise NetworkOnlineUpdateNeededError("Network isn't cached.")
                self._networkRevision = 0

        if not target_offline:
            getNetworkUrl = f"https://api.casambi.com/network/{self._id}/"

            try:
                # **SECURITY**: Do not set session header for client! This could leak the session with external clients.
                res = await self._httpClient.put(
                    getNetworkUrl,
                    json={
                        "formatVersion": 1,
                        "deviceName": DEVICE_NAME,
                        "revision": self._networkRevision,
                    },
                    headers={"X-Casambi-Session": self._session.session},  # type: ignore[union-attr]
                )

                # Apparently this happens when the password changes.
                # In this case we should at least invalidate the session.
                # Currently we invalidate the whole cache for the network since recreating it doesn't cost much.
                if res.status_code == httpx.codes.GONE:
                    self._logger.error(
                        "API reports that network is gone. Deleting cache. Retry later."
                    )
                    await self._cache.invalidate_cache()

                if res.status_code != httpx.codes.OK:
                    self._logger.error(f"Update failed: {res.status_code}\n{res.text}")
                    raise NetworkUpdateError("Could not update network!")

                self._logger.debug(f"Network: {res.text}")

                updateResult = res.json()
                if updateResult["status"] != "UPTODATE":
                    self._networkRevision = updateResult["network"]["revision"]
                    async with self._cache as cachePath:
                        cachedNetworkPah = cachePath / f"{self._id}.json"
                        await cachedNetworkPah.write_bytes(res.content)
                        set_secure_file_permissions(path=cachedNetworkPah)
                    network = updateResult
                    self._logger.info(
                        f"Fetched updated network with revision {self._networkRevision}"
                    )
            except RequestError as err:
                if self._networkRevision == 0:
                    raise NetworkUpdateError from err
                self._logger.warning("Failed to update network. Continuing offline.", exc_info=True)

        # Prase general information
        self._networkName = network["network"]["name"]
        self._protocolVersion = network["network"]["protocolVersion"]

        # Parse keys if there are any. Otherwise the network is probably a classic network.
        if "keyStore" in network["network"]:
            keys = network["network"]["keyStore"]["keys"]
            for k in keys:
                await self._keystore.add_key(key_dict=k)

        # Parse legacy keys
        if "visitorKey" in network["network"]:
            await self._keystore.set_legacy_key(
                key=network["network"]["visitorKey"], is_visitor=True
            )
        if "managerKey" in network["network"]:
            await self._keystore.set_legacy_key(
                key=network["network"]["managerKey"], is_visitor=False
            )

        # Parse units
        self.units = []
        units = network["network"]["units"]
        for u in units:
            uType = await self._fetchUnitInfo(u["type"])
            if uType is None:
                self._logger.info("Failed to fetch type for unit %i. Skipping.", u["type"])
                continue
            uObj = Unit(
                u["type"],
                u["deviceID"],
                u["uuid"],
                u["address"],
                u["name"],
                str(u["firmware"]),
                uType,
                _isClassic=isClassicNetwork(self._protocolVersion),
            )
            self.units.append(uObj)

        # Parse cells
        self.groups = []
        cells = network["network"]["grid"]["cells"]
        for c in cells:
            # Only one type at top level is currently supported
            if c["type"] != 2:
                continue

            # Parse group members
            group_units = []
            # We assume no nested groups here
            for subC in c["cells"]:
                # Ignore everyting that isn't a unit
                if subC["type"] != 1:
                    continue

                unitMatch = list(filter(lambda u: u.deviceId == subC["unit"], self.units))
                if len(unitMatch) != 1:
                    self._logger.warning(
                        f"Incositent unit reference to {subC['unit']} in group {c['groupID']}. Got {len(unitMatch)} matches."
                    )
                    continue
                group_units.append(unitMatch[0])

            gObj = Group(c["groupID"], c["name"], group_units)
            self.groups.append(gObj)

        # Parse scenes
        self.scenes = []
        scenes = network["network"]["scenes"]
        for s in scenes:
            sObj = Scene(s["sceneID"], s["name"])
            self.scenes.append(sObj)

        # TODO: Parse more stuff

        await self._saveTypeCache()

        self._logger.info("Network updated.")

    async def _fetchUnitInfo(self, id: int) -> UnitType | None:
        self._logger.info(f"Fetching unit type for id {id}...")

        # Check whether unit type is already cached
        if id in self._unitTypes:
            cachedType, cacheExpiry = self._unitTypes[id]

            # We don't want to cache types forever so use an expiry date.
            if cacheExpiry < datetime.now(UTC):
                self._logger.info("Cache expiry for type %i. Refetching.", id)
                self._unitTypes.pop(id)
            else:
                self._logger.info("Using cached type.")
                return cachedType

        getUnitInfoUrl = f"https://api.casambi.com/fixture/{id}"
        res = await self._httpClient.get(getUnitInfoUrl)

        if res.status_code != httpx.codes.OK:
            self._logger.error(f"Getting unit info returned {res.status_code}")
            self._unitTypes[id] = (
                None,
                datetime.now(UTC) + timedelta(days=7),
            )
            return None

        unitTypeJson = res.json()

        # Parse UnitControls
        controls = []
        for controlJson in unitTypeJson["controls"]:
            typeStr = controlJson["type"].upper()
            try:
                type = UnitControlType[typeStr]
            except KeyError:
                self._logger.warning(f"Unsupported control mode {typeStr} in fixture {id}.")
                type = UnitControlType.UNIMPLEMENTED

            controlObj = UnitControl(
                type,
                controlJson["offset"],
                controlJson["length"],
                controlJson["default"],
                controlJson["readonly"],
                controlJson.get("min", None),
                controlJson.get("max", None),
            )

            controls.append(controlObj)

        # Parse UnitType
        unitTypeObj = UnitType(
            unitTypeJson["id"],
            unitTypeJson["model"],
            unitTypeJson["vendor"],
            unitTypeJson["mode"],
            unitTypeJson["stateLength"],
            controls,
        )

        # Chache unit type
        self._unitTypes[unitTypeObj.id] = (
            unitTypeObj,
            datetime.now(UTC) + timedelta(days=28),
        )

        self._logger.info("Sucessfully fetched unit type.")
        return unitTypeObj

    async def disconnect(self) -> None:
        return None
