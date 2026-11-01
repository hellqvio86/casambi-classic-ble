import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from casambi_classic_ble._encryption import ClassicEncryptor
from casambi_classic_ble.cloud.api import CasambiCloudAPI
from casambi_classic_ble.device import CasambiDevice


@pytest.mark.asyncio
async def test_device_no_sensitive_logging_at_info_or_warning(
    caplog: pytest.LogCaptureFixture,
    mock_bleak_client: AsyncMock,
) -> None:
    """Verify that device flows do not leak raw hex payloads, passwords, or hardware addresses at INFO/WARNING."""
    caplog.set_level(logging.INFO)

    device = CasambiDevice(
        address="AA:BB:CC:DD:EE:FF",
        name="Test Lamp",
        client=mock_bleak_client,
    )
    device.is_connected = True

    # 1. Authenticate flow
    await device.authenticate(password="super_secret_network_password")

    # 2. Status read flow
    mock_bleak_client.read_gatt_char = AsyncMock(return_value=bytes.fromhex("0301ff00"))
    await device.read_status_char()

    # 3. Notification handler flow (opcode 0x03 unit 1 level 100%)
    notification_data = bytearray(bytes.fromhex("0301ff"))
    device._notification_handler(sender="test-char", data=notification_data)

    # 4. Turn on / off flows
    await device.turn_on(unit_id=1)
    await device.turn_off(unit_id=1)
    await device.turn_on_by_address(address="11:22:33:44:55:66")
    await device.turn_off_by_address(address="11:22:33:44:55:66")

    # Assert no hex payload dumps in INFO or WARNING
    for record in caplog.records:
        if record.levelno in (logging.INFO, logging.WARNING):
            msg = record.getMessage()
            # Raw notification dump marker should never appear at INFO
            assert "==> BLE NOTIFICATION" not in msg
            assert "==> DIRECT READ STATUS" not in msg
            # No secret password or MD5 hash in INFO/WARNING
            assert "super_secret_network_password" not in msg
            assert "0301ff" not in msg
            assert "0301ff00" not in msg


def test_classic_encryptor_verify_does_not_log_computed_mac(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify that signature failure does not reveal the computed MAC at WARNING level."""
    from cryptography.exceptions import InvalidSignature

    caplog.set_level(logging.WARNING)

    encryptor = ClassicEncryptor(key=b"\x00" * 16, sig_len=4)
    # Packet with invalid signature (all 0xFF)
    bad_packet = b"\xff\xff\xff\xff" + b"\x01\x02\x03\x04"
    connhash = b"\x11" * 8

    with pytest.raises(InvalidSignature):
        encryptor.verify(packet=bad_packet, connhash=connhash)

    # Check logs
    for record in caplog.records:
        msg = record.getMessage()
        # Should not reveal "Computed: " or the computed hex MAC
        assert "Computed:" not in msg
        assert "packet:" not in msg


@pytest.mark.asyncio
async def test_cloud_logging_no_session_leak(caplog: pytest.LogCaptureFixture) -> None:
    """Verify cloud api and websocket do not log session IDs."""
    caplog.set_level(logging.DEBUG)

    mock_http_session = AsyncMock()
    api = CasambiCloudAPI(api_key="mock_key", session=mock_http_session)
    # Mock post response
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={"sessionId": "sensitive-session-id-9999", "networks": {}}
    )
    mock_http_session.post = MagicMock(return_value=mock_resp)
    mock_resp.__aenter__.return_value = mock_resp

    await api.create_user_session(email="user@example.com", password="password")

    for record in caplog.records:
        assert "sensitive-session-id-9999" not in record.getMessage()
