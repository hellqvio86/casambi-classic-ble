import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from casambi_classic_ble._cache import Cache
from casambi_classic_ble._network import (
    LEGACY_NETWORK_ID_CACHE_FILE,
    LEGACY_SESSION_CACHE_FILE,
    LEGACY_TYPES_CACHE_FILE,
    NETWORK_ID_CACHE_FILE,
    SESSION_CACHE_FILE,
    TYPES_CACHE_FILE,
    Network,
    _NetworkSession,
)
from casambi_classic_ble.exceptions import (
    AuthenticationError,
    NetworkNotFoundError,
    NetworkOnlineUpdateNeededError,
)
from casambi_classic_ble.utils import is_posix


@pytest.fixture
def mock_cache(tmp_path):
    cache = Cache(cache_path=tmp_path)
    cache._uuid = "00112233-4455-6677-8899-aabbccddeeff"
    return cache


def test_network_session_expired():
    sess_future = _NetworkSession(
        session="sess123",
        network="net1",
        manager=True,
        keyID=1,
        expires=datetime.now(UTC) + timedelta(hours=1),
    )
    assert not sess_future.expired()

    sess_past = _NetworkSession(
        session="sess123",
        network="net1",
        manager=True,
        keyID=1,
        expires=datetime.now(UTC) - timedelta(hours=1),
    )
    assert sess_past.expired()


@pytest.mark.asyncio
async def test_network_load_caches(mock_cache):
    # Pre-populate session and type cache in tmp_path using JSON format
    async with mock_cache as p:
        sess = _NetworkSession(
            session="abc",
            network="net1",
            manager=True,
            keyID=1,
            expires=datetime.now(UTC) + timedelta(hours=1),
        )
        await (p / SESSION_CACHE_FILE).write_text(json.dumps(sess.to_dict()))
        await (p / TYPES_CACHE_FILE).write_text(json.dumps({}))

    client = AsyncMock(spec=httpx.AsyncClient)
    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=client,
        cache=mock_cache,
    )
    await net.load()
    assert net.authenticated()
    assert net._session is not None
    assert net._session.session == "abc"


@pytest.mark.asyncio
async def test_network_get_network_id_success(mock_cache):
    client = AsyncMock(spec=httpx.AsyncClient)
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = httpx.codes.OK
    resp.json.return_value = {"id": "net-id-123"}
    client.get.return_value = resp

    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=client,
        cache=mock_cache,
    )
    await net.get_network_id(force_offline=False)
    assert net._id == "net-id-123"

    # Verify cached to disk
    async with mock_cache as p:
        cached_id = await (p / NETWORK_ID_CACHE_FILE).read_text()
        assert cached_id == "net-id-123"

    # Second call with force_offline=True uses cache
    await net.get_network_id(force_offline=True)
    assert net._id == "net-id-123"

    # Verify deprecated alias emits warning
    with pytest.deprecated_call():
        await net.getNetworkId(forceOffline=True)


@pytest.mark.asyncio
async def test_network_get_network_id_errors(mock_cache):
    client = AsyncMock(spec=httpx.AsyncClient)
    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=client,
        cache=mock_cache,
    )

    # forceOffline without cache
    with pytest.raises(NetworkOnlineUpdateNeededError):
        await net.get_network_id(force_offline=True)

    # 404 NOT_FOUND
    resp_404 = MagicMock(spec=httpx.Response)
    resp_404.status_code = httpx.codes.NOT_FOUND
    client.get.return_value = resp_404
    with pytest.raises(NetworkNotFoundError):
        await net.get_network_id(force_offline=False)

    # 500 SERVER ERROR
    resp_500 = MagicMock(spec=httpx.Response)
    resp_500.status_code = httpx.codes.INTERNAL_SERVER_ERROR
    client.get.return_value = resp_500
    with pytest.raises(NetworkNotFoundError):
        await net.get_network_id(force_offline=False)

    # RequestError without cache
    client.get.side_effect = httpx.RequestError("Network down")
    with pytest.raises(NetworkOnlineUpdateNeededError):
        await net.get_network_id(force_offline=False)


@pytest.mark.asyncio
async def test_network_login_success_and_failure(mock_cache):
    client = AsyncMock(spec=httpx.AsyncClient)
    # mock getNetworkId response
    resp_id = MagicMock(spec=httpx.Response)
    resp_id.status_code = httpx.codes.OK
    resp_id.json.return_value = {"id": "net-id-123"}

    # mock login response
    resp_login = MagicMock(spec=httpx.Response)
    resp_login.status_code = httpx.codes.OK
    expires_ts = (datetime.now(UTC) + timedelta(days=1)).timestamp() * 1000
    resp_login.json.return_value = {
        "session": "session-token-xyz",
        "network": "net-id-123",
        "manager": True,
        "keyID": 1,
        "expires": expires_ts,
    }

    client.get.return_value = resp_id
    client.post.return_value = resp_login

    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=client,
        cache=mock_cache,
    )
    await net.log_in(password="secret-pass", force_offline=False)
    assert net.authenticated()
    assert net._session is not None
    assert net._session.session == "session-token-xyz"

    # Calling again while authenticated returns immediately
    await net.log_in(password="secret-pass", force_offline=False)

    # Verify deprecated alias emits warning
    with pytest.deprecated_call():
        await net.logIn(password="secret-pass", forceOffline=False)

    # Login failure
    net._session = None
    resp_fail = MagicMock(spec=httpx.Response)
    resp_fail.status_code = httpx.codes.UNAUTHORIZED
    resp_fail.text = "Invalid password"
    client.post.return_value = resp_fail

    with pytest.raises(AuthenticationError):
        await net.log_in(password="wrong-pass", force_offline=False)


@pytest.mark.asyncio
async def test_network_update_and_fetch_unit_info(mock_cache):
    client = AsyncMock(spec=httpx.AsyncClient)

    sample_network_payload = {
        "status": "SUCCESS",
        "network": {
            "name": "TestNetwork",
            "protocolVersion": 1,
            "revision": 5,
            "visitorKey": "aabbccddeeff00112233445566778899",
            "managerKey": "112233445566778899aabbccddeeff00",
            "units": [
                {
                    "type": 101,
                    "deviceID": 1,
                    "uuid": "unit-uuid-1",
                    "address": "AA:BB:CC:DD:EE:01",
                    "name": "Ceiling Light",
                    "firmware": "2.1",
                }
            ],
            "grid": {
                "cells": [
                    {
                        "type": 2,
                        "groupID": 1,
                        "name": "Living Room",
                        "cells": [{"type": 1, "unit": 1}],
                    }
                ]
            },
            "scenes": [
                {
                    "sceneID": 10,
                    "name": "Evening Scene",
                }
            ],
        },
    }

    sample_fixture_payload = {
        "id": 101,
        "model": "Model-X",
        "vendor": "Vendor-Y",
        "mode": "Dimmer Mode",
        "stateLength": 2,
        "controls": [
            {
                "type": "Dimmer",
                "offset": 0,
                "length": 8,
                "default": 0,
                "readonly": False,
            },
            {
                "type": "NonExistentControlMode",
                "offset": 8,
                "length": 8,
                "default": 0,
                "readonly": False,
            },
        ],
    }

    # Setup mock network put response
    resp_update = MagicMock(spec=httpx.Response)
    resp_update.status_code = httpx.codes.OK
    resp_update.content = json.dumps(sample_network_payload).encode()
    resp_update.text = json.dumps(sample_network_payload)
    resp_update.json.return_value = sample_network_payload
    client.put.return_value = resp_update

    # Setup mock fixture get response
    resp_fixture = MagicMock(spec=httpx.Response)
    resp_fixture.status_code = httpx.codes.OK
    resp_fixture.json.return_value = sample_fixture_payload
    client.get.return_value = resp_fixture

    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=client,
        cache=mock_cache,
    )
    net._id = "net-id-123"
    net._session = _NetworkSession(
        session="valid-sess",
        network="net-id-123",
        manager=True,
        keyID=1,
        expires=datetime.now(UTC) + timedelta(hours=1),
    )

    await net.load()
    await net.update(forceOffline=False)

    assert net.protocolVersion == 1
    assert len(net.units) == 1
    assert net.units[0].name == "Ceiling Light"
    assert net.units[0].deviceId == 1
    assert len(net.groups) == 1
    assert net.groups[0].name == "Living Room"
    assert len(net.scenes) == 1
    assert net.scenes[0].name == "Evening Scene"

    # Test disconnect
    assert await net.disconnect() is None


class ExploitBomb:
    def __init__(self) -> None:
        raise RuntimeError("EXPLOIT TRIGGERED: Arbitrary code execution via pickle")


class ExploitPayload:
    def __reduce__(self) -> tuple[type[ExploitBomb], tuple[()]]:
        return (ExploitBomb, ())


@pytest.mark.asyncio
async def test_legacy_types_pickle_rejected_safely(mock_cache):
    """Legacy types pickle cache must NEVER be deserialized and must fail closed."""
    import pickle

    async with mock_cache as p:
        await (p / LEGACY_TYPES_CACHE_FILE).write_bytes(pickle.dumps(ExploitPayload()))

    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=AsyncMock(),
        cache=mock_cache,
    )

    with pytest.warns(UserWarning, match="pickle support was removed in v0.6.0 for security"):
        await net._loadTypeCache()

    assert net._unitTypes == {}
    async with mock_cache as p:
        assert not await (p / TYPES_CACHE_FILE).exists()


@pytest.mark.asyncio
async def test_legacy_session_pickle_rejected_safely(mock_cache):
    """Legacy session pickle cache must NEVER be deserialized and must fail closed."""
    import pickle

    async with mock_cache as p:
        await (p / LEGACY_SESSION_CACHE_FILE).write_bytes(pickle.dumps(ExploitPayload()))

    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=AsyncMock(),
        cache=mock_cache,
    )

    with pytest.warns(UserWarning, match="pickle support was removed in v0.6.0 for security"):
        await net._loadSession()

    assert net._session is None
    async with mock_cache as p:
        assert not await (p / SESSION_CACHE_FILE).exists()


@pytest.mark.asyncio
async def test_load_type_cache_from_json(mock_cache):
    """Test loading and normalizing unit types from JSON cache."""
    from casambi_classic_ble._unit import UnitControlType

    types_json_data = {
        "859": {
            "expires": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            "unit_type": {
                "id": 859,
                "model": "TestModel",
                "manufacturer": "TestMfr",
                "mode": "Default",
                "stateLength": 2,
                "controls": [
                    {
                        "type": 0,
                        "offset": 2,
                        "length": 8,
                        "default": 0,
                        "readonly": False,
                        "min": 0,
                        "max": 100,
                    }
                ],
            },
        }
    }
    async with mock_cache as p:
        await (p / TYPES_CACHE_FILE).write_text(json.dumps(types_json_data))

    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=AsyncMock(),
        cache=mock_cache,
    )
    await net._loadTypeCache()

    loaded_type, _ = net._unitTypes[859]
    assert loaded_type is not None
    assert loaded_type.controls[0].type == UnitControlType.DIMMER
    assert isinstance(loaded_type.controls[0].type, UnitControlType)


@pytest.mark.asyncio
async def test_network_json_cache_validation_failures(mock_cache):
    """Corrupted or invalid JSON caches must fail gracefully without crash."""
    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=AsyncMock(),
        cache=mock_cache,
    )

    # 1. Invalid session JSON (not a dict)
    async with mock_cache as p:
        await (p / SESSION_CACHE_FILE).write_text('["not a dict"]')
    await net._loadSession()
    assert net._session is None

    # 2. Session JSON missing required fields
    async with mock_cache as p:
        await (p / SESSION_CACHE_FILE).write_text('{"missing": "fields"}')
    await net._loadSession()
    assert net._session is None

    # 3. Invalid types JSON (not a dict)
    async with mock_cache as p:
        await (p / TYPES_CACHE_FILE).write_text('["not a dict"]')
    await net._loadTypeCache()
    assert net._unitTypes == {}

    # 4. Types JSON with invalid controls
    async with mock_cache as p:
        bad_types = {
            "123": {
                "expires": datetime.now(UTC).isoformat(),
                "unit_type": {
                    "id": 123,
                    "model": "Bad",
                    "manufacturer": "Bad",
                    "mode": "M",
                    "stateLength": 1,
                    "controls": "not a list",
                },
            }
        }
        await (p / TYPES_CACHE_FILE).write_text(json.dumps(bad_types))
    await net._loadTypeCache()
    assert net._unitTypes == {}


@pytest.mark.asyncio
async def test_legacy_network_id_migration(mock_cache):
    async with mock_cache as p:
        await (p / LEGACY_NETWORK_ID_CACHE_FILE).write_text("migrated-net-id")

    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=AsyncMock(),
        cache=mock_cache,
    )
    await net.get_network_id(force_offline=True)
    assert net._id == "migrated-net-id"

    # Assert migrated to new file and legacy unlinked
    async with mock_cache as p:
        assert await (p / NETWORK_ID_CACHE_FILE).exists()
        assert not await (p / LEGACY_NETWORK_ID_CACHE_FILE).exists()
        assert await (p / NETWORK_ID_CACHE_FILE).read_text() == "migrated-net-id"


@pytest.mark.asyncio
async def test_network_cache_permissions(mock_cache):
    import stat

    sess = _NetworkSession(
        session="secure-token",
        network="net-sec",
        manager=True,
        keyID=1,
        expires=datetime.now(UTC) + timedelta(hours=1),
    )
    net = Network(
        uuid="00112233-4455-6677-8899-aabbccddeeff",
        httpClient=AsyncMock(),
        cache=mock_cache,
    )
    net._session = sess
    await net._saveSesion()
    await net._saveTypeCache()

    async with mock_cache as p:
        if is_posix():
            # Check directory permissions (0700)
            dir_stat = await p.stat()
            assert stat.S_IMODE(dir_stat.st_mode) == 0o700

            # Check session JSON permissions (0600)
            sess_stat = await (p / SESSION_CACHE_FILE).stat()
            assert stat.S_IMODE(sess_stat.st_mode) == 0o600

            # Check types JSON permissions (0600)
            types_stat = await (p / TYPES_CACHE_FILE).stat()
            assert stat.S_IMODE(types_stat.st_mode) == 0o600
        else:
            # On non-POSIX (Windows), verify files and directory exist without error
            assert await p.exists()
            assert await (p / SESSION_CACHE_FILE).exists()
            assert await (p / TYPES_CACHE_FILE).exists()
