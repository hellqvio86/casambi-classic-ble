import pathlib

import pytest
from anyio import Path

from casambi_classic_ble._cache import CACHE_VERSION, Cache


@pytest.mark.asyncio
async def test_cache_init(tmp_path: pathlib.Path):
    c1 = Cache(cache_path=None)
    assert c1.cache_path is not None

    c2 = Cache(cache_path=tmp_path)
    assert c2.cache_path == Path(tmp_path)

    c3 = Cache(cache_path=Path(tmp_path))
    assert c3.cache_path == Path(tmp_path)


@pytest.mark.asyncio
async def test_cache_deprecated_aliases(tmp_path: pathlib.Path):
    with pytest.deprecated_call():
        c = Cache(cachePath=tmp_path)
    with pytest.deprecated_call():
        assert c.cachePath == Path(tmp_path)
    with pytest.deprecated_call():
        await c.setUuid(uuid="test-deprecated-uuid")
    with pytest.deprecated_call():
        await c.invalidateCache()


@pytest.mark.asyncio
async def test_cache_lifecycle(tmp_path: pathlib.Path):
    cache = Cache(cache_path=tmp_path)
    await cache.set_uuid(uuid="test-network-uuid")

    async with cache as cache_dir:
        assert await cache_dir.exists()
        test_file = cache_dir / "data.txt"
        await test_file.write_text("hello cache")

    # Invalidate cache
    await cache.invalidate_cache()
    assert not (tmp_path / "test-network-uuid").exists()


@pytest.mark.asyncio
async def test_cache_version_mismatch(tmp_path: pathlib.Path):
    cache = Cache(cache_path=tmp_path)
    await cache.set_uuid(uuid="test-uuid")

    # First run creates cache and .cachever
    async with cache as cache_dir:
        assert await cache_dir.exists()

    # Tamper with cachever
    ver_file = tmp_path / ".cachever"
    ver_file.write_text("1")  # older version

    # Re-entering triggers cache recreation
    async with cache as cache_dir:
        assert await cache_dir.exists()

    assert ver_file.read_text() == str(CACHE_VERSION)


@pytest.mark.asyncio
async def test_cache_version_invalid_text(tmp_path: pathlib.Path):
    cache = Cache(cache_path=tmp_path)
    await cache.set_uuid(uuid="test-uuid")

    async with cache as cache_dir:
        assert await cache_dir.exists()

    # Corrupt version file
    ver_file = tmp_path / ".cachever"
    ver_file.write_text("invalid-int")

    async with cache as cache_dir:
        assert await cache_dir.exists()


@pytest.mark.asyncio
async def test_cache_without_uuid(tmp_path: pathlib.Path):
    cache = Cache(cache_path=tmp_path)
    with pytest.raises(ValueError, match="UUID not set"):
        async with cache:
            pass

    with pytest.raises(ValueError, match="UUID not set"):
        await cache.invalidate_cache()


def test_cache_multiple_event_loops(tmp_path: pathlib.Path):
    import asyncio
    import gc

    async def run_cache_ops(path: pathlib.Path, uid: str):
        c = Cache(cache_path=path)
        await c.set_uuid(uuid=uid)
        async with c as cache_dir:
            assert await cache_dir.exists()
            f = cache_dir / f"{uid}.txt"
            await f.write_text("ok")

    for uid in ("loop1", "loop2"):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run_cache_ops(tmp_path, uid))
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
    gc.collect()

    assert (tmp_path / "loop1" / "loop1.txt").exists()
    assert (tmp_path / "loop2" / "loop2.txt").exists()


@pytest.mark.asyncio
async def test_cache_uuid_validation_and_path_traversal(tmp_path: pathlib.Path):
    from casambi_classic_ble.exceptions import CasambiSecurityError

    cache = Cache(cache_path=tmp_path)

    # Empty UUID
    with pytest.raises(ValueError, match="non-empty string"):
        await cache.set_uuid(uuid="")

    with pytest.raises(ValueError, match="non-empty string"):
        await cache.set_uuid(uuid="   ")

    # Path traversal attempts
    with pytest.raises(CasambiSecurityError, match="path traversal characters are forbidden"):
        await cache.set_uuid(uuid="../escape")

    with pytest.raises(CasambiSecurityError, match="path traversal characters are forbidden"):
        await cache.set_uuid(uuid="sub/dir")

    with pytest.raises(CasambiSecurityError, match="path traversal characters are forbidden"):
        await cache.set_uuid(uuid="sub\\dir")

    with pytest.raises(CasambiSecurityError, match="path traversal characters are forbidden"):
        await cache.set_uuid(uuid="uuid\x00null")


@pytest.mark.asyncio
async def test_cache_symlink_rejection(tmp_path: pathlib.Path):
    from casambi_classic_ble.exceptions import CasambiSecurityError

    cache = Cache(cache_path=tmp_path)
    await cache.set_uuid(uuid="init_net")
    async with cache:
        pass  # Ensures cache version 4 file exists

    await cache.set_uuid(uuid="symlink_net")

    # Create target as symlink
    real_target = tmp_path / "real_store"
    real_target.mkdir()
    sym_dir = tmp_path / "symlink_net"
    sym_dir.symlink_to(real_target)

    with pytest.raises(CasambiSecurityError, match="Symlinks are forbidden"):
        async with cache:
            pass


@pytest.mark.asyncio
async def test_cache_lock_released_on_cancellation(tmp_path: pathlib.Path):
    import asyncio

    cache = Cache(cache_path=tmp_path)
    await cache.set_uuid(uuid="cancel_net")

    async def cancelled_worker() -> None:
        async with cache:
            await asyncio.sleep(10)

    task = asyncio.create_task(cancelled_worker())
    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Lock must be free for next caller
    async with cache as cache_dir:
        assert await cache_dir.exists()


@pytest.mark.asyncio
async def test_cache_has_cached_network_and_clear_session(tmp_path: pathlib.Path):
    from casambi_classic_ble._cache import has_cached_network_sync
    from casambi_classic_ble._constants import (
        LEGACY_NETWORK_ID_CACHE_FILE,
        LEGACY_SESSION_CACHE_FILE,
        NETWORK_ID_CACHE_FILE,
        SESSION_CACHE_FILE,
        TYPES_CACHE_FILE,
    )

    cache = Cache(cache_path=tmp_path)
    with pytest.raises(ValueError, match="UUID not set"):
        await cache.has_cached_network()
    with pytest.raises(ValueError, match="UUID not set"):
        await cache.clear_cached_session()

    # Non-existent base directory
    assert not has_cached_network_sync(
        cache_path=tmp_path / "does_not_exist",
        address="AA:BB:CC:DD:EE:FF",
    )

    # Clear session on non-existent base directory or entry is a safe no-op
    non_existent_cache = Cache(cache_path=tmp_path / "missing_base")
    await non_existent_cache.clear_cached_session(uuid="AA:BB:CC:DD:EE:FF")
    await cache.clear_cached_session(uuid="AA:BB:CC:DD:EE:FF")

    await cache.set_uuid(uuid="aabbccddeeff")
    assert not await cache.has_cached_network()

    async with cache as cache_dir:
        # Empty network ID file does not count as valid cached network
        net_id_file = cache_dir / NETWORK_ID_CACHE_FILE
        await net_id_file.write_text("   ")
        assert not has_cached_network_sync(cache_path=tmp_path, address="AA:BB:CC:DD:EE:FF")

        # Valid network ID file
        await net_id_file.write_text("net-123")
        session_file = cache_dir / SESSION_CACHE_FILE
        legacy_session_file = cache_dir / LEGACY_SESSION_CACHE_FILE
        types_file = cache_dir / TYPES_CACHE_FILE
        await session_file.write_text('{"session": "tok"}')
        await legacy_session_file.write_text("legacy")
        await types_file.write_text("{}")

    assert await cache.has_cached_network()
    assert await cache.has_cached_network(uuid="AA:BB:CC:DD:EE:FF")
    assert has_cached_network_sync(cache_path=tmp_path, address="AA:BB:CC:DD:EE:FF")

    # Clear cached session removes session files while preserving network ID and types
    await cache.clear_cached_session(uuid="AA:BB:CC:DD:EE:FF")
    assert not (tmp_path / "aabbccddeeff" / SESSION_CACHE_FILE).exists()
    assert not (tmp_path / "aabbccddeeff" / LEGACY_SESSION_CACHE_FILE).exists()
    assert (tmp_path / "aabbccddeeff" / TYPES_CACHE_FILE).exists()
    assert await cache.has_cached_network()

    # Legacy networkid file is also recognized
    (tmp_path / "aabbccddeeff" / NETWORK_ID_CACHE_FILE).unlink()
    (tmp_path / "aabbccddeeff" / LEGACY_NETWORK_ID_CACHE_FILE).write_text("legacy-net-123")
    assert await cache.has_cached_network()

    # Mismatched or corrupt .cachever returns False
    (tmp_path / ".cachever").write_text("1")
    assert not await cache.has_cached_network()
    (tmp_path / ".cachever").write_text("not-an-int")
    assert not await cache.has_cached_network()
