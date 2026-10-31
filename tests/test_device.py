"""Tests for CasambiDevice"""

from unittest.mock import AsyncMock, patch

import pytest

from casambi_classic_ble import CasambiDevice


class TestCasambiDevice:
    def test_device_initialization(self):
        device = CasambiDevice(address="EE:F0:3D:B9:26:A9", name="Husnummer")

        assert device.address == "EE:F0:3D:B9:26:A9"
        assert device.name == "Husnummer"
        assert device.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_bleak_client, mock_device):
        device = CasambiDevice(address="EE:F0:3D:B9:26:A9")

        with (
            patch("casambi_classic_ble.device.BleakClient", return_value=mock_bleak_client),
            patch(
                "casambi_classic_ble.device.BleakScanner.find_device_by_address",
                new_callable=AsyncMock,
            ) as mock_find,
        ):
            mock_find.return_value = mock_device
            result = await device.connect()

            assert result is True
            assert device.is_connected is True

    @pytest.mark.asyncio
    async def test_turn_on(self, mock_bleak_client):
        device = CasambiDevice(address="EE:F0:3D:B9:26:A9")
        device.client = mock_bleak_client
        device.is_connected = True

        result = await device.turn_on(unit_id=12)

        assert result is True
        mock_bleak_client.write_gatt_char.assert_called_once()
