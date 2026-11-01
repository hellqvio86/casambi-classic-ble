import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from casambi_classic_ble.cloud import CasambiCloud
from casambi_classic_ble.cloud.api import CasambiCloudAPI
from casambi_classic_ble.cloud.websocket import CasambiCloudWebsocket
from casambi_classic_ble.exceptions import CasambiCloudApiException


@pytest.fixture
async def casambi_cloud():
    cloud = CasambiCloud(
        api_key="test_key",
        email="test@example.com",
        user_password="user_pw",
        network_password="net_pw",
    )
    yield cloud
    await cloud.close()


@pytest.mark.asyncio
async def test_casambi_cloud_session_creation(casambi_cloud):
    mock_api = AsyncMock(spec=CasambiCloudAPI)
    mock_api.create_user_session.return_value = "test_session"
    mock_api.network_id = "net1"

    with patch("casambi_classic_ble.cloud.CasambiCloudAPI", return_value=mock_api):
        session_id = await casambi_cloud.create_user_session()
        assert session_id == "test_session"
        assert casambi_cloud.network_id == "net1"
        mock_api.create_user_session.assert_called_once_with(
            email="test@example.com", password="user_pw"
        )


@pytest.mark.asyncio
async def test_casambi_cloud_context_manager():
    cloud = CasambiCloud(
        api_key="key",
        email="a@b.com",
        user_password="p1",
        network_password="p2",
    )
    async with cloud as c:
        assert c._session is not None
        assert c._api is not None
    assert cloud._session is None
    assert cloud._api is None


@pytest.mark.asyncio
async def test_casambi_cloud_network_session(casambi_cloud):
    mock_api = AsyncMock(spec=CasambiCloudAPI)
    mock_api.create_network_session.return_value = ["net1", "net2"]

    with patch("casambi_classic_ble.cloud.CasambiCloudAPI", return_value=mock_api):
        nets = await casambi_cloud.create_network_session()
        assert nets == ["net1", "net2"]


@pytest.mark.asyncio
async def test_casambi_cloud_facade_delegations(casambi_cloud):
    mock_api = AsyncMock(spec=CasambiCloudAPI)
    mock_api.get_network_information.return_value = {"info": "ok"}
    mock_api.get_network_state.return_value = {"state": "ok"}
    mock_api.get_unit_list.return_value = [{"id": 1}]
    mock_api.get_unit_state.return_value = {"id": 1, "on": True}
    mock_api.get_scenes_list.return_value = [{"name": "s1"}]

    casambi_cloud._api = mock_api
    assert await casambi_cloud.get_network_information() == {"info": "ok"}
    assert await casambi_cloud.get_network_state() == {"state": "ok"}
    assert await casambi_cloud.get_unit_list() == [{"id": 1}]
    assert await casambi_cloud.get_unit_state(unit_id=1) == {"id": 1, "on": True}
    assert await casambi_cloud.get_scenes_list() == [{"name": "s1"}]


@pytest.mark.asyncio
async def test_casambi_cloud_control_commands(casambi_cloud):
    mock_ws = AsyncMock(spec=CasambiCloudWebsocket)
    casambi_cloud._ws = mock_ws

    await casambi_cloud.turn_unit_on(unit_id=14)
    mock_ws.send_command.assert_called_with(unit_id=14, target_controls={"Dimmer": {"value": 1.0}})

    await casambi_cloud.turn_unit_off(unit_id=14)
    mock_ws.send_command.assert_called_with(unit_id=14, target_controls={"Dimmer": {"value": 0.0}})

    # Calling control without websocket raises
    casambi_cloud._ws = None
    with pytest.raises(CasambiCloudApiException):
        await casambi_cloud.turn_unit_on(unit_id=14)


@pytest.mark.asyncio
async def test_casambi_cloud_ws_open_and_close(casambi_cloud):
    # Missing login
    with pytest.raises(CasambiCloudApiException):
        await casambi_cloud.ws_open()

    casambi_cloud._api = MagicMock(spec=CasambiCloudAPI)
    casambi_cloud._api.network_id = "net1"
    casambi_cloud._api.session_id = "sess1"

    mock_ws = AsyncMock(spec=CasambiCloudWebsocket)
    mock_ws.open.return_value = True
    mock_ws.connected = True

    with patch("casambi_classic_ble.cloud.CasambiCloudWebsocket", return_value=mock_ws):
        success = await casambi_cloud.ws_open()
        assert success is True
        assert casambi_cloud.connected is True
        mock_ws.open.assert_called_once()

    # ws_close
    await casambi_cloud.ws_close()
    mock_ws.close.assert_called_once()


@pytest.mark.asyncio
async def test_api_session_guard():
    api = CasambiCloudAPI(api_key="key", session=None)
    with pytest.raises(CasambiCloudApiException, match="HTTP session not initialized"):
        _ = api.session


@pytest.mark.asyncio
async def test_api_rest_endpoints():
    mock_session = MagicMock()
    api = CasambiCloudAPI(api_key="key", session=mock_session)

    # 1. create_user_session
    resp_user = AsyncMock()
    resp_user.status = 200
    resp_user.json.return_value = {
        "sessionId": "user_sess_1",
        "networks": {"net_abc": {"name": "Home"}},
    }
    mock_session.post.return_value.__aenter__.return_value = resp_user

    sess_id = await api.create_user_session(email="user@test.com", password="pass")
    assert sess_id == "user_sess_1"
    assert api.network_id == "net_abc"

    # Error case for user session
    resp_user_err = AsyncMock()
    resp_user_err.status = 401
    resp_user_err.text.return_value = "Unauthorized"
    mock_session.post.return_value.__aenter__.return_value = resp_user_err
    with pytest.raises(CasambiCloudApiException):
        await api.create_user_session(email="user@test.com", password="bad")

    # 2. create_network_session
    resp_net = AsyncMock()
    resp_net.status = 200
    resp_net.json.return_value = {"net_xyz": {"sessionId": "net_sess_1"}}
    mock_session.post.return_value.__aenter__.return_value = resp_net

    nets = await api.create_network_session(email="user@test.com", password="pass")
    assert nets == ["net_xyz"]
    assert api.network_id == "net_xyz"
    assert api.session_id == "net_sess_1"

    # Error case for network session
    mock_session.post.return_value.__aenter__.return_value = resp_user_err
    with pytest.raises(CasambiCloudApiException):
        await api.create_network_session(email="user@test.com", password="bad")

    # 3. get_network_information & get_network_state
    resp_ok = AsyncMock()
    resp_ok.status = 200
    resp_ok.json.return_value = {"data": 123}
    mock_session.get.return_value.__aenter__.return_value = resp_ok

    info = await api.get_network_information()
    assert info == {"data": 123}

    state = await api.get_network_state()
    assert state == {"data": 123}

    unit_state = await api.get_unit_state(unit_id=5)
    assert unit_state == {"data": 123}

    scenes = await api.get_scenes_list()
    assert scenes == {"data": 123}

    # Error when network_id is not set
    api.network_id = None
    with pytest.raises(CasambiCloudApiException):
        await api.get_network_information()
    with pytest.raises(CasambiCloudApiException):
        await api.get_network_state()
    with pytest.raises(CasambiCloudApiException):
        await api.get_unit_list()
    with pytest.raises(CasambiCloudApiException):
        await api.get_unit_state(unit_id=1)
    with pytest.raises(CasambiCloudApiException):
        await api.get_scenes_list()


@pytest.mark.asyncio
async def test_websocket_operations():
    ws = CasambiCloudWebsocket(api_key="key", network_id="net", session_id="sess")

    # Not connected errors
    with pytest.raises(RuntimeError):
        await ws.send_command(unit_id=1, target_controls={})

    assert await ws.receive_messages() == []

    # Mock connection open success
    mock_conn = AsyncMock()
    mock_conn.recv.return_value = json.dumps({"wireStatus": "openWireSucceed"})
    with patch("websockets.connect", new=AsyncMock(return_value=mock_conn)):
        assert await ws.open() is True
        assert ws.connected is True

        # send_command
        await ws.send_command(unit_id=2, target_controls={"Dimmer": {"value": 0.5}})
        mock_conn.send.assert_called()

        # receive_messages
        mock_conn.recv.side_effect = [
            json.dumps({"method": "controlUnit", "id": 2}),
            TimeoutError(),
        ]
        msgs = await ws.receive_messages(timeout=0.1)
        assert len(msgs) == 1

        # close
        await ws.close()
        assert ws.connected is False
        assert ws.web_sock is None


@pytest.mark.asyncio
async def test_websocket_open_failure():
    ws = CasambiCloudWebsocket(api_key="key", network_id="net", session_id="sess")
    mock_conn = AsyncMock()
    mock_conn.send = AsyncMock()
    mock_conn.recv.side_effect = Exception("ws fail")
    mock_conn.close = AsyncMock()
    with patch("websockets.connect", new=AsyncMock(return_value=mock_conn)):
        assert await ws.open() is False
        assert ws.connected is False
