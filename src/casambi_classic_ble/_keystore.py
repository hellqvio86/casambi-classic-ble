import binascii
import json
import logging
import warnings
from dataclasses import asdict, dataclass
from typing import Any, Final

from ._cache import Cache
from ._constants import (
    CLASSIC_AUTH_LEVEL_MANAGER,
    CLASSIC_AUTH_LEVEL_VISITOR,
    KEY_CACHE_FILE,
    LEGACY_KEY_CACHE_FILE,
)
from .exceptions import CasambiCacheError
from .utils import (
    POSIX_FILE_PERMISSIONS,
    async_atomic_write_file,
    validate_safe_path,
)

MAX_KEY_CACHE_RECORDS: Final[int] = 256
MAX_KEY_NAME_LENGTH: Final[int] = 128


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
                validate_safe_path(json_file, base_path=cachePath)
                raw_json = await json_file.read_text()
                try:
                    data = json.loads(raw_json)
                except json.JSONDecodeError as err:
                    raise CasambiCacheError(
                        f"Failed to parse key cache JSON '{KEY_CACHE_FILE}': {err}"
                    ) from err

                if not isinstance(data, list):
                    raise CasambiCacheError(
                        f"Expected list in {KEY_CACHE_FILE}, got {type(data).__name__}"
                    )

                if len(data) > MAX_KEY_CACHE_RECORDS:
                    raise CasambiCacheError(
                        f"Key cache exceeds maximum allowed records ({len(data)} > {MAX_KEY_CACHE_RECORDS})"
                    )

                loaded_keys: list[Key] = []
                seen_ids: set[int] = set()
                seen_legacy_roles: set[int] = set()
                try:
                    for idx, item in enumerate(data):
                        if not isinstance(item, dict):
                            raise ValueError(
                                f"Record at index {idx} must be a dict, got {type(item).__name__}"
                            )

                        for required_field in ("id", "type", "role", "name", "key"):
                            if required_field not in item:
                                raise KeyError(
                                    f"Missing required field '{required_field}' at record {idx}"
                                )

                        key_id = int(item["id"])
                        if not (-1 <= key_id <= 65535):
                            raise ValueError(f"Key id at index {idx} out of range: {key_id}")

                        key_type = int(item["type"])
                        if not (-1 <= key_type <= 65535):
                            raise ValueError(f"Key type at index {idx} out of range: {key_type}")

                        role = int(item["role"])
                        if role < 0 or role > 3:
                            raise ValueError(f"Invalid key role at index {idx}: {role}")

                        if key_id == -1:
                            if role in seen_legacy_roles:
                                raise ValueError(
                                    f"Duplicate legacy key for role {role} at record {idx}"
                                )
                            seen_legacy_roles.add(role)
                        else:
                            if key_id in seen_ids:
                                raise ValueError(f"Duplicate key id {key_id} at record {idx}")
                            seen_ids.add(key_id)

                        name = str(item["name"])
                        if len(name) > MAX_KEY_NAME_LENGTH:
                            raise ValueError(
                                f"Key name at index {idx} exceeds maximum length {MAX_KEY_NAME_LENGTH}"
                            )

                        key_str = item["key"]
                        if not isinstance(key_str, str) or len(key_str) != 32:
                            raise ValueError(
                                f"Key hex string at index {idx} must be exactly 32 characters"
                            )

                        raw_key = bytes.fromhex(key_str)
                        if len(raw_key) != 16:
                            raise ValueError(
                                f"Decoded key length at index {idx} must be 16 bytes, got {len(raw_key)}"
                            )

                        loaded_keys.append(
                            Key(
                                id=key_id,
                                type=key_type,
                                role=role,
                                name=name,
                                key=raw_key,
                            )
                        )
                except (ValueError, KeyError, TypeError, binascii.Error) as err:
                    raise CasambiCacheError(
                        f"Validation failed for key cache '{KEY_CACHE_FILE}': {err}"
                    ) from err

                # Replace in-memory state only after ALL records pass validation
                self._keys = loaded_keys
                self._logger.debug(f"Loaded {len(self._keys)} keys from JSON.")
                return

            if await pickle_file.exists():
                msg = (
                    f"Legacy pickle key cache '{LEGACY_KEY_CACHE_FILE}' found, but pickle support "
                    f"was removed in v0.6.0 for security. Legacy cache is ignored; please re-authenticate."
                )
                warnings.warn(msg, UserWarning, stacklevel=2)
                self._logger.warning(msg)

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

            # Atomic write guarantees crash-safe persistence and secure permissions
            await async_atomic_write_file(
                path=json_file,
                content=json_content,
                mode=POSIX_FILE_PERMISSIONS,
            )

            self._logger.debug(f"Saved {len(self._keys)} keys.")

    async def add_key(self, *, key_dict: dict[str, Any]) -> None:
        """Add a key dictionary to the store."""
        if "id" not in key_dict:
            raise KeyError("id")
        try:
            key_id = int(key_dict["id"])
        except (ValueError, TypeError) as err:
            raise ValueError(f"Invalid key id: {key_dict.get('id')}") from err
        if key_id < 0:
            raise ValueError("id")

        if any(k.id == key_id for k in self._keys):
            self._logger.debug(f"Key with id {key_id} already exists. Skipping...")
            return

        if "type" not in key_dict:
            raise KeyError("type")
        try:
            key_type = int(key_dict["type"])
        except (ValueError, TypeError) as err:
            raise ValueError(f"Invalid key type: {key_dict.get('type')}") from err
        if key_type < 0 or key_type > 0xFF:
            raise ValueError("type")

        if "role" not in key_dict:
            raise KeyError("role")
        try:
            role = int(key_dict["role"])
        except (ValueError, TypeError) as err:
            raise ValueError(f"Invalid key role: {key_dict.get('role')}") from err
        if role < 0 or role > 3:
            raise ValueError("role")

        if "name" not in key_dict:
            raise KeyError("name")
        name = str(key_dict["name"])

        if "key" not in key_dict:
            raise KeyError("key")
        try:
            key_bytes = binascii.a2b_hex(str(key_dict["key"]))
        except binascii.Error as err:
            raise ValueError("Invalid key hex format") from err

        keyObj = Key(key_id, key_type, role, name, key_bytes)
        self._keys.append(keyObj)
        self._logger.info(f"Added key {name} with role {role} to store.")
        await self._save()

    async def addKey(self, *args: Any, **kwargs: Any) -> None:
        """Deprecated alias for add_key."""
        warnings.warn(
            "addKey is deprecated; use add_key instead.", DeprecationWarning, stacklevel=2
        )
        if args:
            return await self.add_key(key_dict=args[0])
        return await self.add_key(key_dict=kwargs.get("key_dict", kwargs.get("dict", {})))

    async def set_legacy_key(self, *, key: str, is_visitor: bool) -> None:
        """Store legacy visitor or manager key."""
        keyRole = CLASSIC_AUTH_LEVEL_VISITOR if is_visitor else CLASSIC_AUTH_LEVEL_MANAGER
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

    async def setLegacyKey(self, *args: Any, **kwargs: Any) -> None:
        """Deprecated alias for set_legacy_key."""
        warnings.warn(
            "setLegacyKey is deprecated; use set_legacy_key instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        key = args[0] if len(args) > 0 else kwargs.get("key", "")
        is_visitor = (
            args[1] if len(args) > 1 else kwargs.get("is_visitor", kwargs.get("isVisitor", False))
        )
        return await self.set_legacy_key(key=key, is_visitor=is_visitor)

    async def clear(self, *, save: bool = False) -> None:
        self._keys.clear()
        self._logger.info("Keystore cleared.")
        if save:
            await self._save()

    def get_key(self) -> Key | None:
        """Return the highest-role active key."""
        key: Key | None = None
        for k in self._keys:
            if k.type == -1:  # Legacy key
                continue
            if not key:
                key = k
            elif key.role < k.role:
                key = k
        return key

    def getKey(self) -> Key | None:
        """Deprecated alias for get_key."""
        warnings.warn(
            "getKey is deprecated; use get_key instead.", DeprecationWarning, stacklevel=2
        )
        return self.get_key()

    def get_legacy_key(self, *, role: int) -> Key | None:
        """Return legacy key matching the given role."""
        for k in self._keys:
            if k.type != -1:  # Not a legacy key
                continue
            elif k.role == role:
                return k
        return None

    def getLegacyKey(self, *args: Any, **kwargs: Any) -> Key | None:
        """Deprecated alias for get_legacy_key."""
        warnings.warn(
            "getLegacyKey is deprecated; use get_legacy_key instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        role = args[0] if args else kwargs.get("role", 0)
        return self.get_legacy_key(role=role)
