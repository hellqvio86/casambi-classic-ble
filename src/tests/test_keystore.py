import json
import pathlib

import pytest

from casambi_classic_ble._cache import Cache
from casambi_classic_ble._constants import (
    CLASSIC_AUTH_LEVEL_MANAGER,
    CLASSIC_AUTH_LEVEL_VISITOR,
)
from casambi_classic_ble._keystore import Key, KeyStore


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


class ExploitBomb:
    def __init__(self) -> None:
        raise RuntimeError("EXPLOIT TRIGGERED: Arbitrary code execution via pickle")


class ExploitPayload:
    def __reduce__(self) -> tuple[type[ExploitBomb], tuple[()]]:
        return (ExploitBomb, ())


@pytest.mark.asyncio
async def test_keystore_legacy_pickle_rejected_safely(test_cache: Cache):
    """Legacy pickle cache must NEVER be deserialized and must fail closed."""
    import pickle

    from casambi_classic_ble._constants import KEY_CACHE_FILE, LEGACY_KEY_CACHE_FILE
    from casambi_classic_ble.constants import (
        KEY_CACHE_FILE as PUB_KEY_CACHE_FILE,
    )
    from casambi_classic_ble.constants import (
        LEGACY_KEY_CACHE_FILE as PUB_LEGACY_KEY_CACHE_FILE,
    )

    assert PUB_KEY_CACHE_FILE == KEY_CACHE_FILE == "casambi_lookup.json"
    assert PUB_LEGACY_KEY_CACHE_FILE == LEGACY_KEY_CACHE_FILE == "keys.pck"

    await test_cache.set_uuid(uuid="test-legacy-net")
    async with test_cache as cachePath:
        legacy_file = cachePath / LEGACY_KEY_CACHE_FILE
        json_file = cachePath / KEY_CACHE_FILE
        # Write exploit payload to legacy pickle file
        await legacy_file.write_bytes(pickle.dumps(ExploitPayload()))
        assert await legacy_file.exists()
        assert not await json_file.exists()

    ks = KeyStore(cache=test_cache)

    with pytest.warns(UserWarning, match="pickle support was removed in v0.6.0 for security"):
        await ks.load()

    # Exploit was not triggered, no keys loaded, and no JSON cache created from untrusted pickle
    assert ks.get_key() is None
    async with test_cache as cachePath:
        assert not await (cachePath / KEY_CACHE_FILE).exists()


@pytest.mark.asyncio
async def test_keystore_json_validation_failures(test_cache: Cache):
    """Corrupted or invalid JSON key caches must be rejected safely with CasambiCacheError."""
    from casambi_classic_ble._constants import KEY_CACHE_FILE
    from casambi_classic_ble.exceptions import CasambiCacheError

    await test_cache.set_uuid(uuid="test-json-validation")

    # 1. Non-list root
    async with test_cache as cachePath:
        await (cachePath / KEY_CACHE_FILE).write_text('{"not": "a list"}')
    ks = KeyStore(cache=test_cache)
    with pytest.raises(CasambiCacheError, match="Expected list"):
        await ks.load()
    assert ks.get_key() is None

    # 2. Non-dict entry
    async with test_cache as cachePath:
        await (cachePath / KEY_CACHE_FILE).write_text('["not a dict"]')
    ks = KeyStore(cache=test_cache)
    with pytest.raises(CasambiCacheError, match="must be a dict"):
        await ks.load()
    assert ks.get_key() is None

    # 3. Invalid key length (must be 16 bytes / 32 hex chars)
    async with test_cache as cachePath:
        invalid_key_json = json.dumps(
            [{"id": 1, "type": 0, "role": 1, "name": "bad", "key": "aabbcc"}]
        )
        await (cachePath / KEY_CACHE_FILE).write_text(invalid_key_json)
    ks = KeyStore(cache=test_cache)
    with pytest.raises(CasambiCacheError, match="must be exactly 32 characters"):
        await ks.load()
    assert ks.get_key() is None

    # 4. Malformed JSON syntax
    async with test_cache as cachePath:
        await (cachePath / KEY_CACHE_FILE).write_text("{unquoted json:")
    ks = KeyStore(cache=test_cache)
    with pytest.raises(CasambiCacheError, match="Failed to parse key cache JSON"):
        await ks.load()
    assert ks.get_key() is None


@pytest.mark.asyncio
async def test_keystore_duplicate_id_rejected(test_cache: Cache):
    """Duplicate key IDs must be rejected by cache validation."""
    from casambi_classic_ble._constants import KEY_CACHE_FILE
    from casambi_classic_ble.exceptions import CasambiCacheError

    await test_cache.set_uuid(uuid="test-duplicate-id")
    payload = [
        {"id": 1, "type": 0, "role": 1, "name": "k1", "key": "00112233445566778899aabbccddeeff"},
        {"id": 1, "type": 0, "role": 2, "name": "k2", "key": "112233445566778899aabbccddeeff00"},
    ]
    async with test_cache as cachePath:
        await (cachePath / KEY_CACHE_FILE).write_text(json.dumps(payload))

    ks = KeyStore(cache=test_cache)
    with pytest.raises(CasambiCacheError, match="Duplicate key id 1"):
        await ks.load()
    assert ks.get_key() is None


@pytest.mark.asyncio
async def test_keystore_record_count_limit_rejected(test_cache: Cache):
    """Caches with > 256 keys must be rejected."""
    from casambi_classic_ble._constants import KEY_CACHE_FILE
    from casambi_classic_ble.exceptions import CasambiCacheError

    await test_cache.set_uuid(uuid="test-oversized-cache")
    payload = [
        {"id": i, "type": 0, "role": 1, "name": f"k{i}", "key": "00112233445566778899aabbccddeeff"}
        for i in range(257)
    ]
    async with test_cache as cachePath:
        await (cachePath / KEY_CACHE_FILE).write_text(json.dumps(payload))

    ks = KeyStore(cache=test_cache)
    with pytest.raises(CasambiCacheError, match="exceeds maximum allowed records"):
        await ks.load()
    assert ks.get_key() is None


@pytest.mark.asyncio
async def test_keystore_field_validation_edge_cases(test_cache: Cache):
    """Field bounds (type, role, name, missing fields) must be enforced."""
    from casambi_classic_ble._constants import KEY_CACHE_FILE
    from casambi_classic_ble.exceptions import CasambiCacheError

    await test_cache.set_uuid(uuid="test-field-bounds")

    cases = [
        (
            {
                "id": -2,
                "type": 0,
                "role": 1,
                "name": "k",
                "key": "00112233445566778899aabbccddeeff",
            },
            "Key id",
        ),
        (
            {
                "id": 65536,
                "type": 0,
                "role": 1,
                "name": "k",
                "key": "00112233445566778899aabbccddeeff",
            },
            "Key id",
        ),
        (
            {
                "id": 1,
                "type": -2,
                "role": 1,
                "name": "k",
                "key": "00112233445566778899aabbccddeeff",
            },
            "Key type",
        ),
        (
            {
                "id": 1,
                "type": 65536,
                "role": 1,
                "name": "k",
                "key": "00112233445566778899aabbccddeeff",
            },
            "Key type",
        ),
        (
            {"id": 1, "type": 0, "role": 5, "name": "k", "key": "00112233445566778899aabbccddeeff"},
            "Invalid key role",
        ),
        (
            {
                "id": 1,
                "type": 0,
                "role": 1,
                "name": "a" * 129,
                "key": "00112233445566778899aabbccddeeff",
            },
            "exceeds maximum length",
        ),
        ({"id": 1, "type": 0, "role": 1, "name": "k"}, "Missing required field"),
        ({"id": 1, "type": 0, "role": 1, "name": "k", "key": "zz" * 16}, "Validation failed"),
    ]

    for item, match in cases:
        async with test_cache as cachePath:
            await (cachePath / KEY_CACHE_FILE).write_text(json.dumps([item]))
        ks = KeyStore(cache=test_cache)
        with pytest.raises(CasambiCacheError, match=match):
            await ks.load()


@pytest.mark.asyncio
async def test_keystore_load_atomicity_no_partial_state(test_cache: Cache):
    """Failed cache loading must leave existing in-memory keys completely untouched."""
    from casambi_classic_ble._constants import KEY_CACHE_FILE
    from casambi_classic_ble.exceptions import CasambiCacheError

    await test_cache.set_uuid(uuid="test-atomicity")
    ks = KeyStore(cache=test_cache)
    # Pre-populate with a valid key in memory
    await ks.add_key(
        key_dict={
            "id": 1,
            "type": 0,
            "role": 1,
            "name": "existing",
            "key": "00112233445566778899aabbccddeeff",
        }
    )
    initial_key = ks.get_key()
    assert initial_key is not None

    # Write a cache with 1 valid key followed by an invalid record
    corrupt_payload = [
        {
            "id": 10,
            "type": 0,
            "role": 2,
            "name": "valid",
            "key": "11111111222222223333333344444444",
        },
        {"id": 20, "type": 0, "role": 99, "name": "corrupt", "key": "bad"},
    ]
    async with test_cache as cachePath:
        await (cachePath / KEY_CACHE_FILE).write_text(json.dumps(corrupt_payload))

    with pytest.raises(CasambiCacheError, match="Invalid key role"):
        await ks.load()

    # Pre-existing in-memory keys must remain intact
    assert ks.get_key() == initial_key
    assert len(ks._keys) == 1
    assert ks._keys[0].key == initial_key.key


@pytest.mark.asyncio
async def test_keystore_concurrent_access(test_cache: Cache):
    """Multiple KeyStore instances accessing caches concurrently must not race or corrupt."""
    import asyncio

    from casambi_classic_ble._constants import CLASSIC_AUTH_LEVEL_VISITOR

    # 1. Concurrent independent KeyStores on the same base cache
    async def worker(worker_id: int) -> Key | None:
        c = Cache(cache_path=test_cache.cache_path)
        await c.set_uuid(uuid=f"concurrent-net-{worker_id}")
        ks = KeyStore(cache=c)
        hex_key = f"{worker_id:02x}" * 16
        await ks.set_legacy_key(key=hex_key, is_visitor=True)
        await ks.load()
        return ks.get_legacy_key(role=CLASSIC_AUTH_LEVEL_VISITOR)

    results = await asyncio.gather(*[worker(i) for i in range(1, 6)])
    for res in results:
        assert res is not None

    # 2. Concurrent readers on a shared KeyStore cache
    await test_cache.set_uuid(uuid="shared-net")
    ks_writer = KeyStore(cache=test_cache)
    await ks_writer.set_legacy_key(key="11" * 16, is_visitor=True)

    async def reader() -> Key | None:
        ks_reader = KeyStore(cache=test_cache)
        await ks_reader.load()
        return ks_reader.get_legacy_key(role=CLASSIC_AUTH_LEVEL_VISITOR)

    readers = await asyncio.gather(*[reader() for _ in range(5)])
    for r in readers:
        assert r is not None
        assert r.key == bytes.fromhex("11" * 16)


def test_no_pickle_imported_in_library():
    """Verify that pickle is never imported or referenced in casambi_classic_ble package."""
    import casambi_classic_ble._keystore
    import casambi_classic_ble._network

    assert "pickle" not in casambi_classic_ble._keystore.__dict__
    assert "pickle" not in casambi_classic_ble._network.__dict__
