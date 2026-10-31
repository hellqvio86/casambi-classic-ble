import pathlib

import pytest

from casambi_classic_ble._cache import Cache
from casambi_classic_ble._constants import (
    CLASSIC_AUTH_LEVEL_MANAGER,
    CLASSIC_AUTH_LEVEL_VISITOR,
)
from casambi_classic_ble._keystore import KeyStore


@pytest.fixture
def test_cache(tmp_path: pathlib.Path) -> Cache:
    c = Cache(cachePath=tmp_path)
    return c


@pytest.mark.asyncio
async def test_keystore_load_empty(test_cache: Cache):
    await test_cache.setUuid(uuid="test-net")
    ks = KeyStore(cache=test_cache)
    await ks.load()
    assert ks.getKey() is None
    assert ks.getLegacyKey(role=CLASSIC_AUTH_LEVEL_VISITOR) is None


@pytest.mark.asyncio
async def test_keystore_add_and_save_load(test_cache: Cache):
    await test_cache.setUuid(uuid="test-net")
    ks = KeyStore(cache=test_cache)

    key_dict = {
        "id": 1,
        "type": 0,
        "role": 2,
        "name": "AdminKey",
        "key": "aabbccddeeff00112233445566778899",
    }
    await ks.addKey(dict=key_dict)

    # Duplicate should be ignored
    await ks.addKey(dict=key_dict)

    retrieved = ks.getKey()
    assert retrieved is not None
    assert retrieved.name == "AdminKey"
    assert retrieved.role == 2
    assert retrieved.key == bytes.fromhex("aabbccddeeff00112233445566778899")

    # Load in a new keystore instance
    ks2 = KeyStore(cache=test_cache)
    await ks2.load()
    k = ks2.getKey()
    assert k is not None
    assert k.name == "AdminKey"


@pytest.mark.asyncio
async def test_keystore_add_key_validations(test_cache: Cache):
    await test_cache.setUuid(uuid="test-net")
    ks = KeyStore(cache=test_cache)

    with pytest.raises(KeyError, match="id"):
        await ks.addKey(dict={})

    with pytest.raises(ValueError, match="id"):
        await ks.addKey(dict={"id": -1})

    with pytest.raises(KeyError, match="type"):
        await ks.addKey(dict={"id": 1})

    with pytest.raises(ValueError, match="type"):
        await ks.addKey(dict={"id": 1, "type": -1})

    with pytest.raises(KeyError, match="role"):
        await ks.addKey(dict={"id": 1, "type": 0})

    with pytest.raises(ValueError, match="role"):
        await ks.addKey(dict={"id": 1, "type": 0, "role": 10})

    with pytest.raises(KeyError, match="name"):
        await ks.addKey(dict={"id": 1, "type": 0, "role": 1})

    with pytest.raises(KeyError, match="key"):
        await ks.addKey(dict={"id": 1, "type": 0, "role": 1, "name": "k"})

    with pytest.raises(ValueError, match="key"):
        await ks.addKey(dict={"id": 1, "type": 0, "role": 1, "name": "k", "key": "not-hex"})


@pytest.mark.asyncio
async def test_keystore_legacy_key(test_cache: Cache):
    await test_cache.setUuid(uuid="test-net")
    ks = KeyStore(cache=test_cache)

    hex_key = "112233445566778899aabbccddeeff00"
    await ks.setLegacyKey(key=hex_key, isVisitor=True)
    assert ks.getLegacyKey(role=CLASSIC_AUTH_LEVEL_VISITOR) is not None

    # Setting identical legacy key returns early
    await ks.setLegacyKey(key=hex_key, isVisitor=True)

    # Update legacy key
    new_hex_key = "ffffffffffffffffffffffffffffffff"
    await ks.setLegacyKey(key=new_hex_key, isVisitor=True)
    vis_k = ks.getLegacyKey(role=CLASSIC_AUTH_LEVEL_VISITOR)
    assert vis_k is not None
    assert vis_k.key == bytes.fromhex(new_hex_key)

    # Manager key
    await ks.setLegacyKey(key=hex_key, isVisitor=False)
    assert ks.getLegacyKey(role=CLASSIC_AUTH_LEVEL_MANAGER) is not None


@pytest.mark.asyncio
async def test_keystore_clear(test_cache: Cache):
    await test_cache.setUuid(uuid="test-net")
    ks = KeyStore(cache=test_cache)
    await ks.setLegacyKey(key="112233445566778899aabbccddeeff00", isVisitor=True)
    assert ks.getLegacyKey(role=CLASSIC_AUTH_LEVEL_VISITOR) is not None

    await ks.clear(save=True)
    assert ks.getLegacyKey(role=CLASSIC_AUTH_LEVEL_VISITOR) is None
