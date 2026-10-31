import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from casambi_classic_ble.cloud import CasambiCloud
from casambi_classic_ble.cloud.api import CasambiCloudAPI
from casambi_classic_ble.cloud.websocket import CasambiCloudWebsocket


@pytest.fixture
def casambi_cloud():
    return CasambiCloud(
        api_key="test_key",
        email="test@example.com",
        user_password="user_pw",
        network_password="net_pw",
    )


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
async def test_casambi_cloud_ws_open(casambi_cloud):
    # Setup mock API to provide network/session info
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


@pytest.mark.asyncio
async def test_casambi_cloud_control(casambi_cloud):
    mock_ws = AsyncMock(spec=CasambiCloudWebsocket)
    casambi_cloud._ws = mock_ws

    await casambi_cloud.turn_unit_on(unit_id=14)
    mock_ws.send_command.assert_called_once_with(
        unit_id=14, target_controls={"Dimmer": {"value": 1.0}}
    )


@pytest.mark.asyncio
async def test_api_unit_list():
    mock_session = MagicMock()
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = [{"id": 1}]

    # Properly mock the async context manager for self._session.get(...)
    mock_session.get.return_value.__aenter__.return_value = mock_resp

    api = CasambiCloudAPI(api_key="key", session=mock_session)
    api.network_id = "net1"

    units = await api.get_unit_list()
    assert len(units) == 1
    assert units[0]["id"] == 1


@pytest.mark.asyncio
async def test_ws_receive_messages():
    ws_handler = CasambiCloudWebsocket(api_key="key", network_id="net", session_id="sess")
    mock_ws = AsyncMock()
    mock_ws.recv.side_effect = [
        json.dumps({"method": "unitChanged", "id": 1}),
        AsyncMock(side_effect=Exception("stop")),  # Simplified stop
    ]
    ws_handler.web_sock = mock_ws

    with patch(
        "asyncio.wait_for",
        side_effect=[json.dumps({"method": "unitChanged", "id": 1}), TimeoutError()],
    ):
        messages = await ws_handler.receive_messages(timeout=0.1)
        assert len(messages) == 1
        assert messages[0]["method"] == "unitChanged"
