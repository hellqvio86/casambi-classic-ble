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
    c = Cache(cache_path=tmp_path)
    return c


@pytest.mark.asyncio
async def test_keystore_load_empty(test_cache: Cache):
    await test_cache.set_uuid(uuid="test-net")
    ks = KeyStore(cache=test_cache)
    await ks.load()
    assert ks.get_key() is None
    assert ks.get_legacy_key(role=CLASSIC_AUTH_LEVEL_VISITOR) is None

    # Verify deprecated aliases emit warnings
    with pytest.deprecated_call():
        assert ks.getKey() is None
    with pytest.deprecated_call():
        assert ks.getLegacyKey(role=CLASSIC_AUTH_LEVEL_VISITOR) is None


@pytest.mark.asyncio
async def test_keystore_add_and_save_load(test_cache: Cache):
    await test_cache.set_uuid(uuid="test-net")
    ks = KeyStore(cache=test_cache)

    key_dict = {
        "id": 1,
        "type": 0,
        "role": 2,
        "name": "AdminKey",
        "key": "aabbccddeeff00112233445566778899",
    }
    await ks.add_key(key_dict=key_dict)

    # Duplicate should be ignored
    await ks.add_key(key_dict=key_dict)

    retrieved = ks.get_key()
    assert retrieved is not None
    assert retrieved.name == "AdminKey"
    assert retrieved.role == 2
    assert retrieved.key == bytes.fromhex("aabbccddeeff00112233445566778899")

    # Load in a new keystore instance
    ks2 = KeyStore(cache=test_cache)
    await ks2.load()
    k = ks2.get_key()
    assert k is not None
    assert k.name == "AdminKey"

    # Verify deprecated alias emits warning
    with pytest.deprecated_call():
        await ks.addKey(dict=key_dict)


@pytest.mark.asyncio
async def test_keystore_add_key_validations(test_cache: Cache):
    await test_cache.set_uuid(uuid="test-net")
    ks = KeyStore(cache=test_cache)

    with pytest.raises(KeyError, match="id"):
        await ks.add_key(key_dict={})

    with pytest.raises(ValueError, match="id"):
        await ks.add_key(key_dict={"id": -1})

    with pytest.raises(KeyError, match="type"):
        await ks.add_key(key_dict={"id": 1})

    with pytest.raises(ValueError, match="type"):
        await ks.add_key(key_dict={"id": 1, "type": -1})

    with pytest.raises(KeyError, match="role"):
        await ks.add_key(key_dict={"id": 1, "type": 0})

    with pytest.raises(ValueError, match="role"):
        await ks.add_key(key_dict={"id": 1, "type": 0, "role": 10})

    with pytest.raises(KeyError, match="name"):
        await ks.add_key(key_dict={"id": 1, "type": 0, "role": 1})

    with pytest.raises(KeyError, match="key"):
        await ks.add_key(key_dict={"id": 1, "type": 0, "role": 1, "name": "k"})

    with pytest.raises(ValueError, match="key"):
        await ks.add_key(key_dict={"id": 1, "type": 0, "role": 1, "name": "k", "key": "not-hex"})


@pytest.mark.asyncio
async def test_keystore_legacy_key(test_cache: Cache):
    await test_cache.set_uuid(uuid="test-net")
    ks = KeyStore(cache=test_cache)

    hex_key = "112233445566778899aabbccddeeff00"
    await ks.set_legacy_key(key=hex_key, is_visitor=True)
    assert ks.get_legacy_key(role=CLASSIC_AUTH_LEVEL_VISITOR) is not None

    # Setting identical legacy key returns early
    await ks.set_legacy_key(key=hex_key, is_visitor=True)

    # Update legacy key
    new_hex_key = "ffffffffffffffffffffffffffffffff"
    await ks.set_legacy_key(key=new_hex_key, is_visitor=True)
    vis_k = ks.get_legacy_key(role=CLASSIC_AUTH_LEVEL_VISITOR)
    assert vis_k is not None
    assert vis_k.key == bytes.fromhex(new_hex_key)

    # Manager key
    await ks.set_legacy_key(key=hex_key, is_visitor=False)
    assert ks.get_legacy_key(role=CLASSIC_AUTH_LEVEL_MANAGER) is not None

    # Verify deprecated alias emits warning
    with pytest.deprecated_call():
        await ks.setLegacyKey(key=hex_key, isVisitor=True)


@pytest.mark.asyncio
async def test_keystore_clear(test_cache: Cache):
    await test_cache.set_uuid(uuid="test-net")
    ks = KeyStore(cache=test_cache)
    await ks.set_legacy_key(key="112233445566778899aabbccddeeff00", is_visitor=True)
    assert ks.get_legacy_key(role=CLASSIC_AUTH_LEVEL_VISITOR) is not None

    await ks.clear(save=True)
    assert ks.get_legacy_key(role=CLASSIC_AUTH_LEVEL_VISITOR) is None


@pytest.mark.asyncio
async def test_keystore_legacy_pickle_migration_with_deprecation_warning(test_cache: Cache):
    """Loading legacy pickle cache emits DeprecationWarning and migrates cleanly to JSON."""
    import pickle

    from casambi_classic_ble._constants import KEY_CACHE_FILE, LEGACY_KEY_CACHE_FILE
    from casambi_classic_ble._keystore import Key

    await test_cache.set_uuid(uuid="test-legacy-net")
    async with test_cache as cachePath:
        legacy_file = cachePath / LEGACY_KEY_CACHE_FILE
        json_file = cachePath / KEY_CACHE_FILE
        # Pre-populate legacy pickle cache
        legacy_keys = [
            Key(
                id=10,
                type=0,
                role=1,
                name="LegacyAdmin",
                key=bytes.fromhex("11223344556677889900112233445566"),
            )
        ]
        await legacy_file.write_bytes(pickle.dumps(legacy_keys))
        assert await legacy_file.exists()
        assert not await json_file.exists()

    ks = KeyStore(cache=test_cache)

    with pytest.deprecated_call(match="Legacy pickle key cache 'keys.pck' is deprecated"):
        await ks.load()

    retrieved = ks.get_key()
    assert retrieved is not None
    assert retrieved.name == "LegacyAdmin"
    assert retrieved.key == bytes.fromhex("11223344556677889900112233445566")

    # Verify JSON cache exists and legacy file was unlinked
    from casambi_classic_ble.constants import (
        KEY_CACHE_FILE as PUB_KEY_CACHE_FILE,
    )
    from casambi_classic_ble.constants import (
        LEGACY_KEY_CACHE_FILE as PUB_LEGACY_KEY_CACHE_FILE,
    )

    assert PUB_KEY_CACHE_FILE == KEY_CACHE_FILE == "casambi_lookup.json"
    assert PUB_LEGACY_KEY_CACHE_FILE == LEGACY_KEY_CACHE_FILE == "keys.pck"

    async with test_cache as cachePath:
        assert await (cachePath / KEY_CACHE_FILE).exists()
        assert not await (cachePath / LEGACY_KEY_CACHE_FILE).exists()
