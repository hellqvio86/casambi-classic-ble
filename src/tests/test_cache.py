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
