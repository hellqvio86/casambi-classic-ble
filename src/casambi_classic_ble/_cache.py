import asyncio
import logging
import os
import pathlib
import shutil
import warnings
from types import TracebackType
from typing import Any, Final

from anyio import Path

from ._constants import (
    LEGACY_NETWORK_ID_CACHE_FILE,
    LEGACY_SESSION_CACHE_FILE,
    NETWORK_ID_CACHE_FILE,
    SESSION_CACHE_FILE,
)
from .exceptions import CasambiSecurityError
from .utils import (
    async_atomic_write_file,
    ensure_secure_directory,
    set_secure_dir_permissions,
    validate_safe_path,
)

_LOGGER = logging.getLogger(__name__)

CACHE_VERSION: Final = 4

# Registry of locks keyed by (event_loop, resolved_cache_path)
_cache_locks: dict[tuple[asyncio.AbstractEventLoop, str], asyncio.Lock] = {}


def _validate_cache_uuid(uuid: str) -> str:
    """Validate cache UUID preventing path traversal and invalid characters."""
    if not isinstance(uuid, str) or not uuid.strip():
        raise ValueError("Cache UUID must be a non-empty string.")
    cleaned = uuid.strip()
    if "\x00" in cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise CasambiSecurityError(
            f"Invalid cache UUID '{cleaned}': path traversal characters are forbidden."
        )
    return cleaned


def normalize_cache_uuid(address_or_uuid: str) -> str:
    """Normalize a Bluetooth MAC address or UUID into a validated lowercase cache key."""
    cleaned = _validate_cache_uuid(address_or_uuid)
    normalized = cleaned.replace(":", "").lower()
    return _validate_cache_uuid(normalized)


def has_cached_network_sync(
    *,
    cache_path: Path | pathlib.Path | None = None,
    address: str,
) -> bool:
    """Check synchronously whether a valid network ID cache entry exists for ``address``."""
    base = (
        pathlib.Path(cache_path)
        if cache_path is not None
        else pathlib.Path(get_default_cache_path())
    )
    validate_safe_path(base)
    if not base.exists():
        return False

    norm_uuid = normalize_cache_uuid(address)
    ver_file = base / ".cachever"
    if ver_file.exists():
        validate_safe_path(ver_file, base_path=base)
        try:
            if int(ver_file.read_text(encoding="utf-8").strip()) != CACHE_VERSION:
                return False
        except (ValueError, OSError):
            return False

    net_dir = base / norm_uuid
    if not net_dir.exists():
        return False
    validate_safe_path(net_dir, base_path=base)

    for filename in (NETWORK_ID_CACHE_FILE, LEGACY_NETWORK_ID_CACHE_FILE):
        candidate = net_dir / filename
        if candidate.exists():
            validate_safe_path(candidate, base_path=net_dir)
            try:
                if candidate.read_text(encoding="utf-8").strip():
                    return True
            except OSError:
                continue
    return False


def get_default_cache_path() -> Path:
    """Return default user data cache directory for casambi-classic-ble."""
    base_dir = os.environ.get("XDG_DATA_HOME")
    if base_dir:
        base_path = pathlib.Path(base_dir)
    else:
        base_path = pathlib.Path.home() / ".local" / "share"
    try:
        base_path.mkdir(parents=True, exist_ok=True)
        return Path(base_path / "casambi-classic-ble-store")
    except OSError:
        return Path(pathlib.Path.cwd() / "casambi-classic-ble-store")


CACHE_PATH_DEFAULT: Final = Path(pathlib.Path.cwd()) / "casambi-classic-ble-store"


def _get_cache_lock(path: Path) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    resolved = str(pathlib.Path(path).resolve())
    key = (loop, resolved)
    if key not in _cache_locks:
        _cache_locks[key] = asyncio.Lock()
    return _cache_locks[key]


def _blocking_delete(path: Path) -> None:
    shutil.rmtree(pathlib.Path(path))


class Cache:
    def __init__(
        self,
        *args: Any,
        cache_path: Path | pathlib.Path | None = None,
        cachePath: Path | pathlib.Path | None = None,
    ) -> None:
        target_path = (
            cache_path
            if cache_path is not None
            else (cachePath if cachePath is not None else (args[0] if len(args) > 0 else None))
        )
        if args or cachePath is not None:
            warnings.warn(
                "Cache positional arguments or cachePath are deprecated; use Cache(cache_path=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if target_path is None:
            self._cachePath = get_default_cache_path()
        elif not isinstance(target_path, Path):
            self._cachePath = Path(target_path)
        else:
            self._cachePath = target_path

        self._cacheVersionFile = self._cachePath / ".cachever"
        self._uuid: str | None = None
        _LOGGER.info("Selecting cache path %s", self._cachePath)

    @property
    def cache_path(self) -> Path:
        return self._cachePath

    @property
    def _cache_path(self) -> Path:
        return self._cachePath

    @property
    def cachePath(self) -> Path:
        warnings.warn(
            "cachePath is deprecated; use cache_path instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._cachePath

    @property
    def _lock(self) -> asyncio.Lock:
        return _get_cache_lock(self._cachePath)

    async def set_uuid(self, *, uuid: str) -> None:
        validated_uuid = _validate_cache_uuid(uuid)
        async with self._lock:
            self._uuid = validated_uuid

    async def setUuid(self, *args: Any, uuid: str | None = None) -> None:
        target_uuid = args[0] if args else uuid
        if target_uuid is None:
            raise ValueError("uuid is required")
        if args or uuid is not None:
            warnings.warn(
                "setUuid is deprecated; use set_uuid(uuid=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        await self.set_uuid(uuid=target_uuid)

    async def _ensureCacheValid(self) -> None:
        # We assume that we already have a lock when calling this function
        if not self._lock.locked():
            raise RuntimeError("Cache lock must be held before validating cache.")

        validate_safe_path(self._cachePath)

        if await self._cachePath.exists():
            cacheVer = None
            if await self._cacheVersionFile.exists():
                validate_safe_path(self._cacheVersionFile, base_path=self._cachePath)
                try:
                    cacheVer = int(await self._cacheVersionFile.read_text())
                    _LOGGER.debug("Read cache version %i.", cacheVer)
                except ValueError:
                    cacheVer = -1
                    _LOGGER.error("Failed to parse cache version.", exc_info=True)
            if cacheVer is None:
                cacheVer = 0
            if cacheVer != CACHE_VERSION:
                _LOGGER.warning(
                    "Cache is version %i, version %i is required. Recreating cache.",
                    cacheVer,
                    CACHE_VERSION,
                )
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _blocking_delete, self._cachePath)

        # This is not a redundant condition. We may have deleted the cache.
        if not await self._cachePath.exists():
            _LOGGER.info("Creating new cache.")
            ensure_secure_directory(self._cachePath)
            await async_atomic_write_file(path=self._cacheVersionFile, content=str(CACHE_VERSION))
        else:
            ensure_secure_directory(self._cachePath)

    async def __aenter__(self) -> Path:
        await self._lock.acquire()

        try:
            if self._uuid is None:
                raise ValueError("UUID not set.")

            await self._ensureCacheValid()

            cacheDir = Path(self._cachePath / self._uuid)
            validate_safe_path(cacheDir, base_path=self._cachePath)
            if not await cacheDir.exists():
                _LOGGER.debug("Creating cache entry for id %s", self._uuid)
                ensure_secure_directory(cacheDir)
            else:
                set_secure_dir_permissions(path=cacheDir)

            _LOGGER.debug("Returning cache path %s for id %s.", cacheDir, self._uuid)
            return cacheDir
        except BaseException:
            self._lock.release()
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._lock.release()

    async def invalidate_cache(self) -> None:
        async with self._lock:
            if self._uuid is None:
                raise ValueError("UUID not set.")
            await self._ensureCacheValid()
            target_entry = self._cachePath / self._uuid
            validate_safe_path(target_entry, base_path=self._cachePath)
            if not await target_entry.exists():
                return
            _LOGGER.info("Deleting cache entry %s", self._uuid)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _blocking_delete, target_entry)

    async def invalidateCache(self) -> None:
        warnings.warn(
            "invalidateCache is deprecated; use invalidate_cache instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.invalidate_cache()

    async def has_cached_network(self, *, uuid: str | None = None) -> bool:
        """Return True if cached network metadata exists for ``uuid`` (or the active UUID)."""
        target_uuid = uuid if uuid is not None else self._uuid
        if target_uuid is None:
            raise ValueError("UUID not set.")
        norm_uuid = normalize_cache_uuid(target_uuid)
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: has_cached_network_sync(
                    cache_path=self._cachePath,
                    address=norm_uuid,
                ),
            )

    async def clear_cached_session(self, *, uuid: str | None = None) -> None:
        """Delete cached session files for ``uuid`` (or the active UUID) without wiping unit types."""
        target_uuid = uuid if uuid is not None else self._uuid
        if target_uuid is None:
            raise ValueError("UUID not set.")
        norm_uuid = normalize_cache_uuid(target_uuid)
        async with self._lock:
            validate_safe_path(self._cachePath)
            if not await self._cachePath.exists():
                return
            target_entry = self._cachePath / norm_uuid
            validate_safe_path(target_entry, base_path=self._cachePath)
            if not await target_entry.exists():
                return
            for session_filename in (SESSION_CACHE_FILE, LEGACY_SESSION_CACHE_FILE):
                session_file = target_entry / session_filename
                if await session_file.exists():
                    validate_safe_path(session_file, base_path=target_entry)
                    await session_file.unlink()
