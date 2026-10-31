import json
import pickle
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from casambi_classic_ble._cache import Cache
from casambi_classic_ble._network import (
    SESSION_CACHE_FILE,
    TYPES_CACHE_FILE,
    Network,
    _NetworkSession,
)
from casambi_classic_ble.errors import (
    AuthenticationError,
    NetworkNotFoundError,
    NetworkOnlineUpdateNeededError,
)


@pytest.fixture
def mock_cache(tmp_path):
    cache = Cache(cachePath=tmp_path)
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
    # Pre-populate session and type cache in tmp_path
    async with mock_cache as p:
        sess = _NetworkSession(
            session="abc",
            network="net1",
            manager=True,
            keyID=1,
            expires=datetime.now(UTC) + timedelta(hours=1),
        )
        await (p / SESSION_CACHE_FILE).write_bytes(pickle.dumps(sess))
        await (p / TYPES_CACHE_FILE).write_bytes(pickle.dumps({}))

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
    await net.getNetworkId(forceOffline=False)
    assert net._id == "net-id-123"

    # Verify cached to disk
    async with mock_cache as p:
        cached_id = await (p / "networkid").read_text()
        assert cached_id == "net-id-123"

    # Second call with forceOffline=True uses cache
    await net.getNetworkId(forceOffline=True)
    assert net._id == "net-id-123"


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
        await net.getNetworkId(forceOffline=True)

    # 404 NOT_FOUND
    resp_404 = MagicMock(spec=httpx.Response)
    resp_404.status_code = httpx.codes.NOT_FOUND
    client.get.return_value = resp_404
    with pytest.raises(NetworkNotFoundError):
        await net.getNetworkId(forceOffline=False)

    # 500 SERVER ERROR
    resp_500 = MagicMock(spec=httpx.Response)
    resp_500.status_code = httpx.codes.INTERNAL_SERVER_ERROR
    client.get.return_value = resp_500
    with pytest.raises(NetworkNotFoundError):
        await net.getNetworkId(forceOffline=False)

    # RequestError without cache
    client.get.side_effect = httpx.RequestError("Network down")
    with pytest.raises(NetworkOnlineUpdateNeededError):
        await net.getNetworkId(forceOffline=False)


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
    await net.logIn(password="secret-pass", forceOffline=False)
    assert net.authenticated()
    assert net._session is not None
    assert net._session.session == "session-token-xyz"

    # Calling again while authenticated returns immediately
    await net.logIn(password="secret-pass", forceOffline=False)

    # Login failure
    net._session = None
    resp_fail = MagicMock(spec=httpx.Response)
    resp_fail.status_code = httpx.codes.UNAUTHORIZED
    resp_fail.text = "Invalid password"
    client.post.return_value = resp_fail

    with pytest.raises(AuthenticationError):
        await net.logIn(password="wrong-pass", forceOffline=False)


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
