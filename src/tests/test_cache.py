import pathlib

import pytest
from anyio import Path

from casambi_classic_ble._cache import CACHE_VERSION, Cache


@pytest.mark.asyncio
async def test_cache_init(tmp_path: pathlib.Path):
    c1 = Cache(cachePath=None)
    assert c1._cachePath is not None

    c2 = Cache(cachePath=tmp_path)
    assert c2._cachePath == Path(tmp_path)

    c3 = Cache(cachePath=Path(tmp_path))
    assert c3._cachePath == Path(tmp_path)


@pytest.mark.asyncio
async def test_cache_lifecycle(tmp_path: pathlib.Path):
    cache = Cache(cachePath=tmp_path)
    await cache.setUuid(uuid="test-network-uuid")

    async with cache as cache_dir:
        assert await cache_dir.exists()
        test_file = cache_dir / "data.txt"
        await test_file.write_text("hello cache")

    # Invalidate cache
    await cache.invalidateCache()
    assert not (tmp_path / "test-network-uuid").exists()


@pytest.mark.asyncio
async def test_cache_version_mismatch(tmp_path: pathlib.Path):
    cache = Cache(cachePath=tmp_path)
    await cache.setUuid(uuid="test-uuid")

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
    cache = Cache(cachePath=tmp_path)
    await cache.setUuid(uuid="test-uuid")

    async with cache as cache_dir:
        assert await cache_dir.exists()

    # Corrupt version file
    ver_file = tmp_path / ".cachever"
    ver_file.write_text("invalid-int")

    async with cache as cache_dir:
        assert await cache_dir.exists()


@pytest.mark.asyncio
async def test_cache_without_uuid(tmp_path: pathlib.Path):
    cache = Cache(cachePath=tmp_path)
    with pytest.raises(ValueError, match="UUID not set"):
        async with cache:
            pass

    with pytest.raises(ValueError, match="UUID not set"):
        await cache.invalidateCache()
