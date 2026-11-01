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
