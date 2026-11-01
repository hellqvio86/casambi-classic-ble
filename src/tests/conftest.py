"""Pytest configuration and fixtures"""

from unittest.mock import AsyncMock, Mock

import pytest
from bleak import BleakClient
from bleak.backends.device import BLEDevice


@pytest.fixture
def mock_bleak_client():
    """Mock BleakClient for testing without real hardware"""
    client = AsyncMock(spec=BleakClient)
    client.is_connected = True
    client.address = "AA:BB:CC:DD:EE:FF"
    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"test_data")
    mock_service = Mock()
    mock_service.uuid = "0000fe4d-0000-1000-8000-00805f9b34fb"
    client.services = [mock_service]
    return client


@pytest.fixture
def mock_adv_data():
    """Mock AdvertisementData"""
    adv_data = Mock()
    adv_data.service_uuids = ["0000fe3d-0000-1000-8000-00805f9b34fb"]
    adv_data.manufacturer_data = {}
    return adv_data


@pytest.fixture
def mock_device():
    """Mock discovered BLE device"""
    device = Mock(spec=BLEDevice)
    device.address = "AA:BB:CC:DD:EE:FF"
    device.name = "MockDevice"
    device.details = {}
    device.rssi = -60
    return device
