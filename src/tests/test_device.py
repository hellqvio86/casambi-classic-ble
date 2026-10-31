"""Tests for CasambiDevice"""

from unittest.mock import AsyncMock, patch

import pytest

from casambi_classic_ble import CasambiDevice


class TestCasambiDevice:
    def test_device_initialization(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", name="MockDevice")

        assert device.address == "AA:BB:CC:DD:EE:FF"
        assert device.name == "MockDevice"
        assert device.is_connected is False

    def test_named_arguments_enforced(self):
        # Calling with positional arguments must raise TypeError
        with pytest.raises(TypeError):
            CasambiDevice("AA:BB:CC:DD:EE:FF")  # type: ignore[misc]

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_bleak_client, mock_device, mock_adv_data):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")

        with (
            patch("casambi_classic_ble.device.BleakClient", return_value=mock_bleak_client),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={mock_device.address: (mock_device, mock_adv_data)}),
            ),
        ):
            result = await device.connect()

            assert result is True
            assert device.is_connected is True

    @pytest.mark.asyncio
    async def test_turn_on(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        result = await device.turn_on(unit_id=12)

        assert result is True
        mock_bleak_client.write_gatt_char.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        result = await device.turn_off(unit_id=12)

        assert result is True
        mock_bleak_client.write_gatt_char.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_level(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        result = await device.set_level(unit_id=12, level=0.75)

        assert result is True
        mock_bleak_client.write_gatt_char.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        result = await device.authenticate(password="secret")

        assert result is True
        mock_bleak_client.write_gatt_char.assert_called_once()

    def test_parse_status(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        status = device.parse_status(data=bytearray([0x01, 0x05, 0x80]))

        assert status["id"] == 5
        assert status["on"] is True
        assert status["dimLevel"] == pytest.approx(0.502, abs=0.01)

    def test_update_from_advertisement(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        # 6 bytes address (AA:BB:CC:DD:EE:FF), 1 byte flags (0x01 = ON), 1 byte dim level (255)
        mfr_data = bytes.fromhex("aabbccddeeff") + bytes([0x01, 0xFF])
        status = device.update_from_advertisement(mfr_data=mfr_data)

        assert status is not None
        assert status["on"] is True
        assert status["level_percent"] == 100
