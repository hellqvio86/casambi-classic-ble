import binascii
import json
import logging
import os
import pickle
import warnings
from dataclasses import asdict, dataclass
from typing import Any

from ._cache import Cache
from ._constants import (
    CLASSIC_AUTH_LEVEL_MANAGER,
    CLASSIC_AUTH_LEVEL_VISITOR,
    KEY_CACHE_FILE,
    LEGACY_KEY_CACHE_FILE,
)


@dataclass()
class Key:
    id: int
    type: int
    role: int
    name: str
    key: bytes


class KeyStore:
    def __init__(self, cache: Cache) -> None:
        self._keys: list[Key] = []
        self._logger = logging.getLogger(__name__)

        self._cache = cache

    async def load(self) -> None:
        self._logger.info("Loading keys...")
        async with self._cache as cachePath:
            json_file = cachePath / KEY_CACHE_FILE
            pickle_file = cachePath / LEGACY_KEY_CACHE_FILE

            if await json_file.exists():
                raw_json = await json_file.read_text()
                try:
                    data = json.loads(raw_json)
                    loaded_keys: list[Key] = []
                    for item in data:
                        loaded_keys.append(
                            Key(
                                id=int(item["id"]),
                                type=int(item["type"]),
                                role=int(item["role"]),
                                name=str(item["name"]),
                                key=bytes.fromhex(item["key"]),
                            )
                        )
                    self._keys = loaded_keys
                    self._logger.debug(f"Loaded {len(self._keys)} keys from JSON.")
                    return
                except Exception as err:
                    self._logger.warning(f"Failed to load keys from JSON cache: {err}")

            if await pickle_file.exists():
                warnings.warn(
                    f"Legacy pickle key cache '{LEGACY_KEY_CACHE_FILE}' is deprecated and will be removed "
                    f"in a future release. Migrating keys to secure JSON cache format.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                try:
                    key_bytes = await pickle_file.read_bytes()
                    self._keys = pickle.loads(key_bytes)
                    self._logger.debug(f"Loaded {len(self._keys)} keys from legacy pickle cache.")
                    # Automatically migrate to JSON format and remove old pickle file
                    key_data = []
                    for k in self._keys:
                        d = asdict(k)
                        d["key"] = k.key.hex()
                        key_data.append(d)

                    json_content = json.dumps(key_data, indent=2)
                    json_file = cachePath / KEY_CACHE_FILE
                    await json_file.write_text(json_content)
                    try:
                        os.chmod(str(json_file), 0o600)
                    except OSError as err:
                        self._logger.debug(f"Could not set permissions on {json_file}: {err}")

                    try:
                        await pickle_file.unlink()
                    except Exception as err:
                        self._logger.debug(f"Could not remove old pickle cache file: {err}")
                    return
                except Exception as err:
                    self._logger.warning(f"Failed to load legacy pickle key cache: {err}")

            self._logger.debug("No cached keys.")

    async def _save(self) -> None:
        await self._save_to_cache(self._cache)

    async def _save_to_cache(self, cache: Cache) -> None:
        self._logger.info("Saving keys...")
        async with cache as cachePath:
            key_data = []
            for k in self._keys:
                d = asdict(k)
                d["key"] = k.key.hex()
                key_data.append(d)

            json_content = json.dumps(key_data, indent=2)
            json_file = cachePath / KEY_CACHE_FILE
            await json_file.write_text(json_content)

            # Ensure secure file permissions (0600: read/write owner only)
            try:
                os.chmod(str(json_file), 0o600)
            except OSError as err:
                self._logger.debug(f"Could not set permissions on {json_file}: {err}")

            self._logger.debug(f"Saved {len(self._keys)} keys.")

    async def addKey(self, dict: dict[str, Any]) -> None:
        if "id" not in dict:
            raise KeyError("id")
        try:
            key_id = int(dict["id"])
        except (ValueError, TypeError) as err:
            raise ValueError(f"Invalid key id: {dict.get('id')}") from err
        if key_id < 0:
            raise ValueError("id")

        if any(k.id == key_id for k in self._keys):
            self._logger.debug(f"Key with id {key_id} already exists. Skipping...")
            return

        if "type" not in dict:
            raise KeyError("type")
        try:
            key_type = int(dict["type"])
        except (ValueError, TypeError) as err:
            raise ValueError(f"Invalid key type: {dict.get('type')}") from err
        if key_type < 0 or key_type > 0xFF:
            raise ValueError("type")

        if "role" not in dict:
            raise KeyError("role")
        try:
            role = int(dict["role"])
        except (ValueError, TypeError) as err:
            raise ValueError(f"Invalid key role: {dict.get('role')}") from err
        if role < 0 or role > 3:
            raise ValueError("role")

        if "name" not in dict:
            raise KeyError("name")
        name = str(dict["name"])

        if "key" not in dict:
            raise KeyError("key")
        try:
            key_bytes = binascii.a2b_hex(str(dict["key"]))
        except binascii.Error as err:
            raise ValueError("Invalid key hex format") from err

        keyObj = Key(key_id, key_type, role, name, key_bytes)
        self._keys.append(keyObj)
        self._logger.info(f"Added key {name} with role {role} to store.")
        await self._save()

    async def setLegacyKey(self, key: str, isVisitor: bool) -> None:
        keyRole = CLASSIC_AUTH_LEVEL_VISITOR if isVisitor else CLASSIC_AUTH_LEVEL_MANAGER
        try:
            keyBytes = binascii.a2b_hex(key)
        except binascii.Error as err:
            raise ValueError("Invalid key hex format") from err

        for i, k in enumerate(self._keys):
            if k.type != -1:  # Not a legacy key
                continue
            if k.role == keyRole:
                if k.key == keyBytes:
                    return
                _ = self._keys.pop(i)
                break

        self._keys.append(Key(-1, -1, keyRole, "legacy", keyBytes))
        self._logger.info(f"Added legacy key with role {keyRole} to store.")
        await self._save()

    async def clear(self, save: bool = False) -> None:
        self._keys.clear()
        self._logger.info("Keystore cleared.")
        if save:
            await self._save()

    def getKey(self) -> Key | None:
        key: Key | None = None
        for k in self._keys:
            if k.type == -1:  # Legacy key
                continue
            if not key:
                key = k
            elif key.role < k.role:
                key = k
        return key

    def getLegacyKey(self, role: int) -> Key | None:
        for k in self._keys:
            if k.type != -1:  # Not a legacy key
                continue
            elif k.role == role:
                return k
        return None
