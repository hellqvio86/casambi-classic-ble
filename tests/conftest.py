"""Pytest configuration and fixtures"""

import pytest

from unittest.mock import Mock, AsyncMock
from bleak import BleakClient, BLEDevice


@pytest.fixture
def mock_bleak_client():
    """Mock BleakClient for testing without real hardware"""
    client = AsyncMock(spec=BleakClient)
    client.is_connected = True
    client.address = "EE:F0:3D:B9:26:A9"
    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"test_data")
    return client


@pytest.fixture
def mock_adv_data():
    """Mock AdvertisementData"""
    adv_data = Mock()
    adv_data.service_uuids = ["0000fe3d-0000-1000-8000-00805f9b34fb"]
    return adv_data


@pytest.fixture
def mock_device():
    """Mock discovered BLE device"""
    device = Mock(spec=BLEDevice)
    device.address = "EE:F0:3D:B9:26:A9"
    device.name = "Husnummer"
    device.details = {}
    device.rssi = -60
    return device
