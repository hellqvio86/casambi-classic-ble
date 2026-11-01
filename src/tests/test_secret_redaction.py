"""Tests for sensitive data masking, MAC sanitization, and credential leak prevention."""

import logging
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from casambi_classic_ble import (
    AuthenticationError,
    NetworkUpdateError,
    mask_mac,
    mask_sensitive_data,
)
from casambi_classic_ble._encryption import ClassicEncryptor
from casambi_classic_ble._keystore import Key, KeyStore
from casambi_classic_ble._network import Network, _NetworkSession
from casambi_classic_ble.scanner import CasambiScanner


def test_mask_mac_standard_and_debug() -> None:
    """Test MAC address masking preserves privacy in standard mode and details in debug mode."""
    mac = "AA:BB:CC:DD:EE:FF"
    # Standard mode masks middle octets
    assert mask_mac(mac, is_debug=False) == "AA:BB:**:**:EE:FF"
    # Debug mode preserves full address for troubleshooting
    assert mask_mac(mac, is_debug=True) == "AA:BB:CC:DD:EE:FF"

    # Hyphenated MAC
    hyphen_mac = "AA-BB-CC-DD-EE-FF"
    assert mask_mac(hyphen_mac, is_debug=False) == "AA-BB-**-**-EE-FF"
    assert mask_mac(hyphen_mac, is_debug=True) == "AA-BB-CC-DD-EE-FF"

    # 12-char hex string
    hex_mac = "AABBCCDDEEFF"
    assert mask_mac(hex_mac, is_debug=False) == "AABB****EEFF"
    assert mask_mac(hex_mac, is_debug=True) == "AABBCCDDEEFF"

    # Edge cases
    assert mask_mac(None) == ""
    assert mask_mac("") == ""
    assert mask_mac("invalid_format", is_debug=False) == "***"
    assert mask_mac("invalid_format", is_debug=True) == "invalid_format"


def test_mask_sensitive_data_nested_and_debug() -> None:
    """Test masking sensitive credentials in standard mode and unmasked in debug mode."""
    payload: dict[str, Any] = {
        "network": {
            "name": "Home Mesh",
            "password": "CANARY_PLAINTEXT_PASSWORD_123",
            "visitorKey": "CANARY_VISITOR_KEY_000",
            "managerKey": "CANARY_MANAGER_KEY_111",
            "keys": [
                {"id": 1, "key": "00112233445566778899aabbccddeeff", "role": "manager"},
                {"id": 2, "secret": "CANARY_SECRET_ABC", "role": "visitor"},
            ],
            "session": "CANARY_SESSION_TOKEN_XYZ",
            "auth": {"token": "CANARY_AUTH_TOKEN_789", "connhash": "CANARY_HASH_012"},
        },
        "safe_int": 42,
        "safe_str": "normal_data",
    }

    # In standard mode (is_debug=False), sensitive fields are redacted
    masked = mask_sensitive_data(payload, is_debug=False)
    assert masked["network"]["password"] == "***"
    assert masked["network"]["visitorKey"] == "***"
    assert masked["network"]["managerKey"] == "***"
    assert masked["network"]["keys"][0]["key"] == "***"
    assert masked["network"]["keys"][1]["secret"] == "***"
    assert masked["network"]["session"] == "***"
    assert masked["network"]["auth"]["token"] == "***"
    assert masked["network"]["auth"]["connhash"] == "***"
    assert masked["network"]["name"] == "Home Mesh"
    assert masked["network"]["keys"][0]["id"] == 1
    assert masked["safe_int"] == 42
    assert masked["safe_str"] == "normal_data"

    # In debug mode (is_debug=True), data is returned unmasked
    unmasked = mask_sensitive_data(payload, is_debug=True)
    assert unmasked["network"]["password"] == "CANARY_PLAINTEXT_PASSWORD_123"
    assert unmasked["network"]["visitorKey"] == "CANARY_VISITOR_KEY_000"
    assert unmasked["network"]["managerKey"] == "CANARY_MANAGER_KEY_111"
    assert unmasked["network"]["keys"][0]["key"] == "00112233445566778899aabbccddeeff"


def test_key_repr_does_not_reveal_secret_bytes() -> None:
    """Test that Key.__repr__ redacts raw cryptographic key bytes."""
    canary_key = b"\xca\xfe\xba\xbe" * 4
    key = Key(
        id=1,
        type=0,
        role=3,
        name="CanaryManager",
        key=canary_key,
    )

    repr_output = repr(key)

    assert "CanaryManager" in repr_output
    assert canary_key.hex() not in repr_output
    assert "cafebabe" not in repr_output
    assert "key=b'***'" in repr_output


def test_network_session_repr_does_not_reveal_session_token() -> None:
    """Test that _NetworkSession.__repr__ redacts the session token."""
    session = _NetworkSession(
        session="CANARY_SECRET_SESSION_TOKEN_999",
        network="canary_network_id",
        manager=True,
        keyID=1,
        expires=datetime(2030, 1, 1, 0, 0, tzinfo=UTC),
    )

    repr_output = repr(session)

    assert "CANARY_SECRET_SESSION_TOKEN_999" not in repr_output
    assert "session='***'" in repr_output
    assert "canary_network_id" in repr_output


def test_classic_encryptor_repr_does_not_reveal_key() -> None:
    """Test that ClassicEncryptor.__repr__ does not reveal AES key material."""
    canary_aes_key = b"\x01\x23\x45\x67\x89\xab\xcd\xef\xfe\xdc\xba\x98\x76\x54\x32\x10"
    encryptor = ClassicEncryptor(key=canary_aes_key, sig_len=4)

    repr_output = repr(encryptor)

    assert canary_aes_key.hex() not in repr_output
    assert "0123456789" not in repr_output
    assert repr_output == "ClassicEncryptor(sig_len=4)"


@pytest.mark.asyncio
async def test_login_and_update_errors_do_not_leak_response_body() -> None:
    """Test that login and update failure exceptions/errors do not leak raw response text."""
    mock_cache_dir = MagicMock()
    mock_cached_file = MagicMock()
    mock_cached_file.exists = AsyncMock(return_value=False)
    mock_cache_dir.__truediv__ = MagicMock(return_value=mock_cached_file)

    mock_cache = MagicMock()
    mock_cache.__aenter__ = AsyncMock(return_value=mock_cache_dir)
    mock_cache.__aexit__ = AsyncMock(return_value=None)

    mock_http = MagicMock()
    topology = Network(
        uuid="aabbccddeeff",
        httpClient=mock_http,
        cache=mock_cache,
    )
    topology._keystore = MagicMock(spec=KeyStore)
    topology._id = "test_net_id"

    # 1. Login failure should not embed raw body or password
    mock_login_res = MagicMock()
    mock_login_res.status_code = 403
    mock_login_res.text = "Echoed secret: CANARY_LEAKED_BODY_SECRET"
    mock_http.post = AsyncMock(return_value=mock_login_res)

    with (
        patch.object(topology, "get_network_id", new_callable=AsyncMock),
        pytest.raises(AuthenticationError) as exc_info,
    ):
        await topology.log_in(password="CANARY_PASSWORD_999", force_offline=False)

    assert "CANARY_PASSWORD_999" not in str(exc_info.value)
    assert "CANARY_LEAKED_BODY_SECRET" not in str(exc_info.value)
    assert "403" in str(exc_info.value)

    # 2. Update failure should not log raw error body
    topology._session = _NetworkSession(
        session="CANARY_SESSION_TOKEN",
        network="test_net_id",
        manager=True,
        keyID=1,
        expires=datetime(2030, 1, 1, 0, 0, tzinfo=UTC),
    )
    mock_update_res = MagicMock()
    mock_update_res.status_code = 500
    mock_update_res.text = "Internal error with CANARY_SERVER_SECRET"
    mock_http.put = AsyncMock(return_value=mock_update_res)

    with (
        patch.object(topology._logger, "error") as mock_error,
        pytest.raises(NetworkUpdateError),
    ):
        await topology.update(force_offline=False)

    for call_args in mock_error.call_args_list:
        assert "CANARY_SERVER_SECRET" not in str(call_args)


@pytest.mark.asyncio
async def test_scanner_masks_mac_only_when_not_debug() -> None:
    """Test that CasambiScanner masks MAC at INFO level unless DEBUG is enabled."""
    mock_dev = MagicMock()
    mock_dev.name = "MockDevice"
    mock_dev.address = "AA:BB:CC:DD:EE:FF"
    mock_dev.rssi = -55

    mock_adv = MagicMock()
    mock_adv.service_uuids = ["0000fe4d-0000-1000-8000-00805f9b34fb"]
    mock_adv.manufacturer_data = {0x03C3: bytes([0xFF, 0xEE, 0xDD, 0xCC, 0xBB, 0xAA, 0x01, 0xFF])}

    discovered_map = {"AA:BB:CC:DD:EE:FF": (mock_dev, mock_adv)}

    scanner_logger = logging.getLogger("casambi_classic_ble.scanner")

    # 1. Non-debug mode -> MAC is masked in INFO logs
    with (
        patch(
            "casambi_classic_ble.scanner.BleakScanner.discover", new_callable=AsyncMock
        ) as mock_disc,
        patch.object(scanner_logger, "isEnabledFor", return_value=False),
        patch.object(scanner_logger, "info") as mock_info,
    ):
        mock_disc.return_value = discovered_map
        await CasambiScanner.scan(duration=0.1)

        info_logs = " ".join(str(c) for c in mock_info.call_args_list)
        assert "AA:BB:**:**:EE:FF" in info_logs
        assert "AA:BB:CC:DD:EE:FF" not in info_logs

    # 2. Debug mode -> Full MAC is preserved in logs
    with (
        patch(
            "casambi_classic_ble.scanner.BleakScanner.discover", new_callable=AsyncMock
        ) as mock_disc,
        patch.object(scanner_logger, "isEnabledFor", return_value=True),
        patch.object(scanner_logger, "info") as mock_info,
    ):
        mock_disc.return_value = discovered_map
        await CasambiScanner.scan(duration=0.1)

        info_logs = " ".join(str(c) for c in mock_info.call_args_list)
        assert "AA:BB:CC:DD:EE:FF" in info_logs
