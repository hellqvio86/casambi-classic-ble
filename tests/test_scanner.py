"""Tests for CasambiScanner"""

from unittest.mock import AsyncMock, patch

import pytest

from casambi_classic_ble import CasambiDevice, CasambiScanner


class TestCasambiScanner:
    @pytest.mark.asyncio
    async def test_scan_finds_casambi_devices(self, mock_device, mock_adv_data):
        with patch(
            "casambi_classic_ble.scanner.BleakScanner.discover",
            new=AsyncMock(return_value={mock_device.address: (mock_device, mock_adv_data)}),
        ):
            scanner = CasambiScanner()
            devices = await scanner.scan(duration=1.0)

            assert len(devices) == 1
            assert isinstance(devices[0], CasambiDevice)
            assert devices[0].address == mock_device.address
