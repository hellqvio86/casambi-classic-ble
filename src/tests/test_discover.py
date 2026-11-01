from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakDBusError, BleakError

from casambi_classic_ble._constants import CASA_UUID
from casambi_classic_ble._discover import discover
from casambi_classic_ble.exceptions import BluetoothError


@pytest.mark.asyncio
async def test_discover_success():
    mock_dev1 = MagicMock()
    mock_dev1.address = "AA:BB:CC:DD:EE:01"
    mock_adv1 = MagicMock()
    mock_adv1.manufacturer_data = {963: b"some_mfr"}
    mock_adv1.service_uuids = [CASA_UUID]

    # Device without manufacturer data 963
    mock_dev2 = MagicMock()
    mock_dev2.address = "AA:BB:CC:DD:EE:02"
    mock_adv2 = MagicMock()
    mock_adv2.manufacturer_data = {123: b"other"}
    mock_adv2.service_uuids = [CASA_UUID]

    # Device with 963 but without CASA_UUID
    mock_dev3 = MagicMock()
    mock_dev3.address = "AA:BB:CC:DD:EE:03"
    mock_adv3 = MagicMock()
    mock_adv3.manufacturer_data = {963: b"some_mfr"}
    mock_adv3.service_uuids = ["00000000-0000-0000-0000-000000000000"]

    scan_result = {
        mock_dev1.address: (mock_dev1, mock_adv1),
        mock_dev2.address: (mock_dev2, mock_adv2),
        mock_dev3.address: (mock_dev3, mock_adv3),
    }

    with patch(
        "casambi_classic_ble._discover.BleakScanner.discover",
        new=AsyncMock(return_value=scan_result),
    ):
        devs = await discover()
        assert len(devs) == 1
        assert devs[0].address == "AA:BB:CC:DD:EE:01"


@pytest.mark.asyncio
async def test_discover_darwin_platform():
    with (
        patch("platform.system", return_value="Darwin"),
        patch(
            "casambi_classic_ble._discover.BleakScanner.discover", new=AsyncMock(return_value={})
        ) as mock_scan,
    ):
        devs = await discover()
        assert devs == []
        mock_scan.assert_called_once_with(return_adv=True, cb={"use_bdaddr": True})


@pytest.mark.asyncio
async def test_discover_errors():
    with (
        patch(
            "casambi_classic_ble._discover.BleakScanner.discover",
            side_effect=BleakDBusError("org.bluez.Error.Failed", ["DBus error"]),
        ),
        pytest.raises(BluetoothError),
    ):
        await discover()

    with (
        patch(
            "casambi_classic_ble._discover.BleakScanner.discover",
            side_effect=BleakError("Generic bleak error"),
        ),
        pytest.raises(BluetoothError),
    ):
        await discover()
