"""Tests for CasambiDevice"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from casambi_classic_ble import CasambiDevice
from casambi_classic_ble.constants import CasambiUUIDs
from casambi_classic_ble.exceptions import (
    CasambiCommandError,
    CasambiConnectionError,
    CasambiDeviceError,
    CasambiDeviceNotFoundError,
)


class TestCasambiDevice:
    def test_device_initialization(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", name="MockDevice")

        assert device.address == "AA:BB:CC:DD:EE:FF"
        assert device.name == "MockDevice"
        assert device.is_connected is False

    def test_device_initialization_with_ble_device(self, mock_device, mock_bleak_client):
        # Initializing with BLEDevice and pre-injected client (Home Assistant pattern)
        device = CasambiDevice(
            address=mock_device,
            name="External Name",
            client=mock_bleak_client,
        )
        assert device.address == mock_device.address
        assert device.name == mock_device.name
        assert device.client is mock_bleak_client

    @pytest.mark.asyncio
    async def test_connect_with_ble_device_uses_establish_connection(
        self, mock_device, mock_bleak_client
    ):
        device = CasambiDevice(address=mock_device)

        with (
            patch(
                "casambi_classic_ble.device.establish_connection",
                new=AsyncMock(return_value=mock_bleak_client),
            ) as mock_establish,
            patch("casambi_classic_ble.device.BleakScanner.discover") as mock_discover,
        ):
            await device.connect(timeout=10.0)

            assert device.is_connected is True
            mock_establish.assert_called_once()
            # Ensure scanner was NOT called because BLEDevice was already supplied
            mock_discover.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_uses_get_device_fast_lookup_without_scanning(
        self, mock_device, mock_bleak_client
    ):
        """T-012: connect() uses get_device(address) first, avoiding BleakScanner.discover when resolved."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")

        with (
            patch(
                "casambi_classic_ble.device.get_device", new=AsyncMock(return_value=mock_device)
            ) as mock_get_device,
            patch(
                "casambi_classic_ble.device.establish_connection",
                new=AsyncMock(return_value=mock_bleak_client),
            ) as mock_establish,
            patch("casambi_classic_ble.device.BleakScanner.discover") as mock_discover,
        ):
            await device.connect()
            assert device.is_connected is True
            mock_get_device.assert_called_once_with("AA:BB:CC:DD:EE:FF")
            mock_establish.assert_called_once()
            mock_discover.assert_not_called()

    def test_named_arguments_enforced(self):
        # Calling with positional arguments must raise TypeError
        with pytest.raises(TypeError):
            CasambiDevice("AA:BB:CC:DD:EE:FF")  # type: ignore[misc]

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_bleak_client, mock_device, mock_adv_data):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")

        with (
            patch("casambi_classic_ble.device.get_device", new=AsyncMock(return_value=None)),
            patch(
                "casambi_classic_ble.device.establish_connection",
                new=AsyncMock(return_value=mock_bleak_client),
            ),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={mock_device.address: (mock_device, mock_adv_data)}),
            ),
        ):
            await device.connect()
            assert device.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_reversed_and_mfr_data(self, mock_bleak_client, mock_device):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")

        # 1. Match reversed address: FF:EE:DD:CC:BB:AA
        dev_rev = MagicMock()
        dev_rev.address = "FF:EE:DD:CC:BB:AA"
        adv_rev = MagicMock()
        adv_rev.manufacturer_data = {}

        with (
            patch("casambi_classic_ble.device.get_device", new=AsyncMock(return_value=None)),
            patch(
                "casambi_classic_ble.device.establish_connection",
                new=AsyncMock(return_value=mock_bleak_client),
            ),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={dev_rev.address: (dev_rev, adv_rev)}),
            ),
        ):
            await device.connect()
            assert device.is_connected is True

        # 2. Match manufacturer data
        dev_mfr = MagicMock()
        dev_mfr.address = "11:22:33:44:55:66"
        adv_mfr = MagicMock()
        adv_mfr.manufacturer_data = {963: bytes.fromhex("aabbccddeeff")}
        device._ble_device = None

        with (
            patch("casambi_classic_ble.device.get_device", new=AsyncMock(return_value=None)),
            patch(
                "casambi_classic_ble.device.establish_connection",
                new=AsyncMock(return_value=mock_bleak_client),
            ),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={dev_mfr.address: (dev_mfr, adv_mfr)}),
            ),
        ):
            await device.connect()
            assert device.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_v2_and_not_found(self, mock_bleak_client, mock_device):
        # V2 service
        srv_v2 = MagicMock()
        srv_v2.uuid = CasambiUUIDs.SERVICE_V2
        mock_bleak_client.services = [srv_v2]

        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        adv = MagicMock()
        adv.manufacturer_data = {}
        with (
            patch("casambi_classic_ble.device.get_device", new=AsyncMock(return_value=None)),
            patch(
                "casambi_classic_ble.device.establish_connection",
                new=AsyncMock(return_value=mock_bleak_client),
            ),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover",
                new=AsyncMock(return_value={mock_device.address: (mock_device, adv)}),
            ),
        ):
            await device.connect()
            assert device._control_uuid == CasambiUUIDs.CONTROL_V2

        # Device not found raises CasambiDeviceNotFoundError
        device_missing = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        with (
            patch("casambi_classic_ble.device.get_device", new=AsyncMock(return_value=None)),
            patch(
                "casambi_classic_ble.device.BleakScanner.discover", new=AsyncMock(return_value={})
            ),
        ):
            with pytest.raises(CasambiDeviceNotFoundError):
                await device_missing.connect()
            assert device_missing.is_connected is False

        # Exception during connect raises CasambiConnectionError
        device_err = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device_err._ble_device = mock_device
        with patch(
            "casambi_classic_ble.device.establish_connection",
            new=AsyncMock(side_effect=Exception("Connect error")),
        ):
            with pytest.raises(CasambiConnectionError) as exc_info:
                await device_err.connect()
            assert "Connect error" in str(exc_info.value.__cause__)
            assert device_err.is_connected is False

    @pytest.mark.asyncio
    async def test_turn_on(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        await device.turn_on(unit_id=12)
        mock_bleak_client.write_gatt_char.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        await device.turn_off(unit_id=12)
        mock_bleak_client.write_gatt_char.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_level(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        await device.set_level(unit_id=12, level=0.75)
        mock_bleak_client.write_gatt_char.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        await device.authenticate(password="secret")
        mock_bleak_client.write_gatt_char.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_empty_password_raises(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        with pytest.raises(CasambiDeviceError, match="Password required"):
            await device.authenticate(password="")

    def test_parse_status(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        # Opcode 0x03 is the verified status response opcode
        status = device.parse_status(data=bytearray([0x03, 0x05, 0x80]))

        assert status["id"] == 5
        assert status["on"] is True
        assert status["dimLevel"] == pytest.approx(0.502, abs=0.01)

        # T-003: Unknown opcodes return empty dict
        assert device.parse_status(data=bytearray([0x07, 0x05, 0x80])) == {}
        assert device.parse_status(data=bytearray([0x01, 0x05, 0x80])) == {}

    def test_notification_handler_unknown_opcode_preserves_last_state(self):
        """T-003: Unknown opcode frames must not overwrite last_state or trigger state callbacks."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        # Initialize with known state
        device.last_state = {"id": 1, "on": True, "dimLevel": 1.0, "level_percent": 100}

        cb = MagicMock()
        device.register_state_callback(callback=cb)

        # Send unknown opcode 0x07 notification frame
        device._notification_handler(sender="char_uuid", data=bytearray([0x07, 0x02, 0x00]))

        # last_state remains intact and state callback not dispatched
        assert device.last_state == {"id": 1, "on": True, "dimLevel": 1.0, "level_percent": 100}
        cb.assert_not_called()

        # Send valid 0x03 opcode notification frame
        device._notification_handler(sender="char_uuid", data=bytearray([0x03, 0x02, 0x80]))
        assert device.last_state["id"] == 2
        assert device.last_state["dimLevel"] == pytest.approx(0.502, abs=0.01)
        cb.assert_called_once()

    def test_update_from_advertisement(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        # 6 bytes address (AA:BB:CC:DD:EE:FF), 1 byte flags (0x01 = ON), 1 byte dim level (255)
        mfr_data = bytes.fromhex("aabbccddeeff") + bytes([0x01, 0xFF])
        status = device.update_from_advertisement(mfr_data=mfr_data)

        assert status is not None
        assert status["on"] is True
        assert status["level_percent"] == 100

        # Too short (< 8 bytes)
        assert device.update_from_advertisement(mfr_data=b"\x00" * 7) is None

        # Address mismatch
        assert (
            device.update_from_advertisement(
                mfr_data=bytes.fromhex("112233445566") + bytes([0x01, 0xFF])
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_turn_by_address(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        await device.turn_on_by_address(address="AA:BB:CC:DD:EE:FF")
        await device.turn_off_by_address(address="AA:BB:CC:DD:EE:FF")

        # Invalid address length raises CasambiDeviceError
        with pytest.raises(CasambiDeviceError, match="Invalid address"):
            await device.turn_on_by_address(address="AA:BB")
        with pytest.raises(CasambiDeviceError, match="Invalid address"):
            await device.turn_off_by_address(address="AA:BB")

    @pytest.mark.asyncio
    async def test_broadcast_commands(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        await device.turn_on_broadcast()
        await device.turn_off_broadcast()
        assert mock_bleak_client.write_gatt_char.call_count == 2

    @pytest.mark.asyncio
    async def test_set_color_temp_and_rgb(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True

        await device.set_color_temperature(unit_id=1, temp_kelvin=3500)
        await device.set_rgb(unit_id=1, r=255, g=128, b=0)
        assert mock_bleak_client.write_gatt_char.call_count == 2

    @pytest.mark.asyncio
    async def test_request_state(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await device.request_state(unit_id=2, settle=0.5)
            assert mock_bleak_client.write_gatt_char.call_count == 2
            mock_sleep.assert_called_once_with(0.5)

    @pytest.mark.asyncio
    async def test_get_state_deprecated_alias(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.deprecated_call():
                await device.get_state(unit_id=2)
            assert mock_bleak_client.write_gatt_char.call_count == 2

    @pytest.mark.asyncio
    async def test_disconnect_and_read_status_char(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        mock_bleak_client.read_gatt_char = AsyncMock(return_value=bytearray(b"\x01\x02\x03"))
        data = await device.read_status_char()
        assert data == b"\x01\x02\x03"

        await device.disconnect()
        assert device.is_connected is False
        with pytest.raises(CasambiConnectionError, match="Device not connected"):
            await device.read_status_char()

    @pytest.mark.asyncio
    async def test_read_status_char_error_raises_device_error(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True
        mock_bleak_client.read_gatt_char = AsyncMock(side_effect=RuntimeError("Read failure"))

        with pytest.raises(CasambiDeviceError, match="Failed to read status char"):
            await device.read_status_char()

    @pytest.mark.asyncio
    async def test_get_device_info(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True
        mock_bleak_client.read_gatt_char = AsyncMock(side_effect=[b"Casambi", b"CBU-ASD", b"26.5"])

        info = await device.get_device_info()
        assert info["manufacturer"] == "Casambi"
        assert info["model"] == "CBU-ASD"
        assert info["firmware"] == "26.5"

    @pytest.mark.asyncio
    async def test_get_device_info_disconnected_raises_connection_error(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        assert device.is_connected is False

        with pytest.raises(CasambiConnectionError, match="Device not connected"):
            await device.get_device_info()

    @pytest.mark.asyncio
    async def test_get_device_info_read_failure_raises_device_error(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True
        mock_bleak_client.read_gatt_char = AsyncMock(side_effect=RuntimeError("GATT read crash"))

        with pytest.raises(CasambiDeviceError, match="Failed to read device info"):
            await device.get_device_info()

    @pytest.mark.asyncio
    async def test_send_command(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True
        assert not hasattr(device, "_session_key")

        # Send command with payload
        await device._send_command(command=0x03, payload=b"\x10\x20")
        mock_bleak_client.write_gatt_char.assert_called_once()

    def test_notification_callback(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        received = []
        unsubscribe = device.register_notification_callback(callback=lambda d: received.append(d))
        # Status response opcode 0x03
        device._notification_handler("test-sender", bytearray([0x03, 0x05, 0xFF]))
        assert len(received) == 1
        assert device.last_state["id"] == 5

        unsubscribe()
        device._notification_handler("test-sender", bytearray([0x03, 0x05, 0x00]))
        assert len(received) == 1

    def test_notification_callback_deprecated_setter(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        received = []
        with pytest.deprecated_call():
            device.set_notification_callback(callback=lambda d: received.append(d))
        device._notification_handler("test-sender", bytearray([0x03, 0x05, 0xFF]))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_input_validation_set_level_rejects_out_of_bounds(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        with pytest.raises(CasambiDeviceError, match=r"level must be between 0\.0 and 1\.0"):
            await device.set_level(unit_id=1, level=-0.1)

        with pytest.raises(CasambiDeviceError, match=r"level must be between 0\.0 and 1\.0"):
            await device.set_level(unit_id=1, level=1.01)

        with pytest.raises(CasambiDeviceError, match="unit_id must be between 0 and 255"):
            await device.set_level(unit_id=-1, level=0.5)

        with pytest.raises(CasambiDeviceError, match="unit_id must be between 0 and 255"):
            await device.set_level(unit_id=256, level=0.5)

    @pytest.mark.asyncio
    async def test_input_validation_turn_on_off_rejects_invalid_unit_id(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        with pytest.raises(CasambiDeviceError, match="unit_id must be between 0 and 255"):
            await device.turn_on(unit_id=-1)

        with pytest.raises(CasambiDeviceError, match="unit_id must be between 0 and 255"):
            await device.turn_off(unit_id=300)

        with pytest.raises(CasambiDeviceError, match="unit_id must be between 0 and 255"):
            await device.request_state(unit_id=-5)

    @pytest.mark.asyncio
    async def test_input_validation_color_temperature_rejects_out_of_bounds(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        with pytest.raises(CasambiDeviceError, match="temp_kelvin must be between 2000 and 6500K"):
            await device.set_color_temperature(unit_id=1, temp_kelvin=1999)

        with pytest.raises(CasambiDeviceError, match="temp_kelvin must be between 2000 and 6500K"):
            await device.set_color_temperature(unit_id=1, temp_kelvin=6501)

    @pytest.mark.asyncio
    async def test_color_temperature_and_rgb_require_unit_id(self):
        """T-013: set_color_temperature and set_rgb require unit_id keyword argument."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        with pytest.raises(TypeError):
            await device.set_color_temperature(temp_kelvin=3500)  # type: ignore[call-arg]

        with pytest.raises(TypeError):
            await device.set_rgb(r=255, g=128, b=0)  # type: ignore[call-arg]

    @pytest.mark.asyncio
    async def test_input_validation_rgb_rejects_out_of_bounds(self):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        with pytest.raises(CasambiDeviceError, match="RGB channel 'r'"):
            await device.set_rgb(unit_id=1, r=-1, g=100, b=100)

        with pytest.raises(CasambiDeviceError, match="RGB channel 'g'"):
            await device.set_rgb(unit_id=1, r=100, g=256, b=100)

        with pytest.raises(CasambiDeviceError, match="RGB channel 'b'"):
            await device.set_rgb(unit_id=1, r=100, g=100, b=999)

    @pytest.mark.asyncio
    async def test_connect_idempotent(self, mock_bleak_client):
        """Calling connect() when already connected returns immediately without reconnecting."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True
        mock_bleak_client.is_connected = True

        await device.connect()
        mock_bleak_client.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_safe_when_unconnected(self):
        """Calling disconnect() when not connected is safe and does not raise."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.is_connected = False
        device.client = None

        await device.disconnect()
        assert device.is_connected is False

    def test_disconnect_callback_handling(self, mock_bleak_client):
        """Triggering _on_bleak_disconnect invokes registered callback and isolates errors."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.is_connected = True

        disconnections = []
        unsubscribe = device.register_disconnect_callback(
            callback=lambda: disconnections.append(True)
        )
        device._on_bleak_disconnect(mock_bleak_client)

        assert len(disconnections) == 1
        assert device.is_connected is False

        unsubscribe()
        device._on_bleak_disconnect(mock_bleak_client)
        assert len(disconnections) == 1

        # If subscriber callback raises an error, _on_bleak_disconnect does not crash
        failing_device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        failing_device.register_disconnect_callback(
            callback=MagicMock(side_effect=RuntimeError("Subscriber error"))
        )
        failing_device._on_bleak_disconnect(mock_bleak_client)
        assert failing_device.is_connected is False

    def test_disconnect_callback_deprecated_setter(self, mock_bleak_client):
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.is_connected = True
        disconnections = []
        with pytest.deprecated_call():
            device.set_disconnected_callback(callback=lambda: disconnections.append(True))
        device._on_bleak_disconnect(mock_bleak_client)
        assert len(disconnections) == 1

    @pytest.mark.asyncio
    async def test_gatt_writes_serialized_with_lock(self, mock_bleak_client):
        """Simultaneous GATT write operations must acquire _write_lock sequentially."""
        import asyncio

        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        execution_order = []

        async def fake_write(*args, **kwargs):
            execution_order.append("start")
            await asyncio.sleep(0.01)
            execution_order.append("end")

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=fake_write)

        # Launch two commands concurrently
        await asyncio.gather(
            device.set_level(unit_id=1, level=0.5),
            device.set_level(unit_id=2, level=0.8),
        )

        # Because writes are locked, execution must not interleave: start, end, start, end
        assert execution_order == ["start", "end", "start", "end"]

    @pytest.mark.asyncio
    async def test_cancellation_propagates(self, mock_bleak_client):
        """asyncio.CancelledError must propagate and not be swallowed by broad except."""
        import asyncio

        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True
        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            await device.set_level(unit_id=1, level=0.5)

    @pytest.mark.asyncio
    async def test_commands_raise_when_disconnected(self):
        """Commands must raise CasambiConnectionError when called on disconnected device."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.is_connected = False

        with pytest.raises(CasambiConnectionError, match="Device not connected"):
            await device.turn_on(unit_id=1)

        with pytest.raises(CasambiConnectionError, match="Device not connected"):
            await device.turn_off(unit_id=1)

        with pytest.raises(CasambiConnectionError, match="Device not connected"):
            await device.set_level(unit_id=1, level=0.5)

        with pytest.raises(CasambiConnectionError, match="Device not connected"):
            await device.authenticate(password="secret")

    @pytest.mark.asyncio
    async def test_command_ble_failure_raises_command_error(self, mock_bleak_client):
        """BLE write failure during command execution raises CasambiCommandError."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True
        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=RuntimeError("BLE write failed"))

        with pytest.raises(CasambiCommandError, match="Failed to send command"):
            await device.set_level(unit_id=1, level=0.5)

    @pytest.mark.asyncio
    async def test_unit_targeting_all_vs_single(self, mock_bleak_client):
        """Verifies targeting all units (broadcast) vs single unit produces exact frames."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        written_packets = []

        async def fake_write(char_uuid, data, response=True):
            written_packets.append(data)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=fake_write)

        # 1. turn_on() without unit_id targets all units (broadcast 0xFFFF)
        await device.turn_on()
        assert written_packets[-1].hex() == "03ffffff"

        # 2. turn_on(unit_id=5) targets unit 5
        await device.turn_on(unit_id=5)
        assert written_packets[-1].hex() == "030500ff"

        # 3. turn_off() without unit_id targets all units (broadcast 0xFFFF)
        await device.turn_off()
        assert written_packets[-1].hex() == "03ffff00"

        # 4. turn_off(unit_id=5) targets unit 5
        await device.turn_off(unit_id=5)
        assert written_packets[-1].hex() == "03050000"

        # 5. set_level() without unit_id targets all units
        await device.set_level(level=0.5)
        assert written_packets[-1].hex() == "03ffff80"

        # 6. set_level(unit_id=5, level=0.5) targets unit 5
        await device.set_level(unit_id=5, level=0.5)
        assert written_packets[-1].hex() == "030580"

    def test_state_subscription_and_duplicate_suppression(self):
        """State subscribers receive updates on state changes and suppress duplicate frames."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        updates = []

        unsubscribe = device.register_state_callback(callback=lambda state: updates.append(state))

        # Frame 1: Light ON (0x01), Level 255 (0xFF), rolling counter 0x01
        mfr_data_1 = bytes.fromhex("aabbccddeeff") + bytes([0x01, 0xFF, 0x01])
        device.update_from_advertisement(mfr_data=mfr_data_1)
        assert len(updates) == 1
        assert updates[-1]["on"] is True
        assert updates[-1]["level_percent"] == 100

        # Frame 2: Identical state with rolling counter incremented to 0x02 (must be suppressed)
        mfr_data_2 = bytes.fromhex("aabbccddeeff") + bytes([0x01, 0xFF, 0x02])
        device.update_from_advertisement(mfr_data=mfr_data_2)
        assert len(updates) == 1  # No duplicate dispatched!

        # Frame 3: State change (dimmed to 50%)
        mfr_data_3 = bytes.fromhex("aabbccddeeff") + bytes([0x01, 0x80, 0x03])
        device.update_from_advertisement(mfr_data=mfr_data_3)
        assert len(updates) == 2
        assert updates[-1]["level_percent"] == 50

        # Frame 4: State change (turned OFF)
        mfr_data_4 = bytes.fromhex("aabbccddeeff") + bytes([0x00, 0x00, 0x04])
        device.update_from_advertisement(mfr_data=mfr_data_4)
        assert len(updates) == 3
        assert updates[-1]["on"] is False

        # Unsubscribe removes callback
        unsubscribe()
        mfr_data_5 = bytes.fromhex("aabbccddeeff") + bytes([0x01, 0xFF, 0x05])
        device.update_from_advertisement(mfr_data=mfr_data_5)
        assert len(updates) == 3  # Not called after unsubscribe

    def test_state_subscription_isolated_exceptions(self):
        """Errors in subscriber callbacks are safely isolated and do not prevent other subscribers."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        successful_updates = []

        def failing_cb(state):
            raise RuntimeError("Subscriber explosion")

        def working_cb(state):
            successful_updates.append(state)

        device.register_state_callback(callback=failing_cb)
        device.register_state_callback(callback=working_cb)

        mfr_data = bytes.fromhex("aabbccddeeff") + bytes([0x01, 0xFF])
        # Should not raise exception
        result = device.update_from_advertisement(mfr_data=mfr_data)
        assert result is not None
        assert len(successful_updates) == 1

    def test_notification_handler_dispatches_to_state_subscribers(self):
        """Active GATT notifications reach state subscribers with per-unit deduplication."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        updates = []
        raw_notifications = []

        unsubscribe = device.register_state_callback(callback=lambda state: updates.append(state))
        device.register_notification_callback(callback=lambda data: raw_notifications.append(data))

        # (a) Notification: opcode 0x03, unit 1, level 128 (0x80)
        # format: [opcode (0x03), unit_id (0x01), level (0x80)]
        pkt_unit_1 = bytearray([0x03, 0x01, 0x80])
        device._notification_handler(sender="handle_8", data=pkt_unit_1)

        assert len(updates) == 1
        assert updates[-1]["id"] == 1
        assert updates[-1]["on"] is True
        assert updates[-1]["level_percent"] == 50
        assert len(raw_notifications) == 1

        # Identical repeat for unit 1 must be suppressed by state subscribers
        device._notification_handler(sender="handle_8", data=pkt_unit_1)
        assert len(updates) == 1  # suppressed
        assert len(raw_notifications) == 2  # raw callback still gets packet

        # (b) Unit 2 reporting identical state (on, 50%) must fire because unit ID is different
        pkt_unit_2 = bytearray([0x03, 0x02, 0x80])
        device._notification_handler(sender="handle_8", data=pkt_unit_2)
        assert len(updates) == 2
        assert updates[-1]["id"] == 2
        assert updates[-1]["level_percent"] == 50

        # Alternate back to unit 1 with changed state
        pkt_unit_1_off = bytearray([0x03, 0x01, 0x00])
        device._notification_handler(sender="handle_8", data=pkt_unit_1_off)
        assert len(updates) == 3
        assert updates[-1]["id"] == 1
        assert updates[-1]["on"] is False

        # (c) Callback raising does not break the handler or raw notification callback
        def raising_subscriber(state):
            raise ValueError("Boom")

        device.register_state_callback(callback=raising_subscriber)
        device.register_notification_callback(callback=lambda data: None)
        # Should not raise
        device._notification_handler(sender="handle_8", data=bytearray([0x03, 0x01, 0xFF]))
        assert len(updates) == 4
        assert updates[-1]["level_percent"] == 100

        # Raw notification callback raising does not bubble up or break state
        def raising_raw(data):
            raise RuntimeError("Raw boom")

        device.register_notification_callback(callback=raising_raw)
        device._notification_handler(sender="handle_8", data=bytearray([0x03, 0x01, 0x10]))
        assert len(updates) == 5

        # (d) Unsubscribe works
        unsubscribe()
        device._notification_handler(sender="handle_8", data=bytearray([0x03, 0x01, 0x20]))
        assert len(updates) == 5  # No new updates recorded

    def test_is_connected_reflects_injected_client_state(self, mock_bleak_client):
        """T-011: is_connected property reflects injected client's connection drop immediately."""
        device = CasambiDevice(
            address="AA:BB:CC:DD:EE:FF",
            client=mock_bleak_client,
        )
        device.is_connected = True
        mock_bleak_client.is_connected = True
        assert device.is_connected is True

        # Injected client disconnects externally
        mock_bleak_client.is_connected = False
        assert device.is_connected is False

    def test_handle_disconnect_clears_dedupe_and_resets_client(self, mock_bleak_client):
        """T-011: handle_disconnect resets deduplication cache and clears non-injected client."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")
        device.client = mock_bleak_client
        device.is_connected = True
        device._last_notified_states[1] = (True, 1.0)

        device.handle_disconnect()
        assert device.is_connected is False
        assert len(device._last_notified_states) == 0
        assert device.client is None
        assert device._ble_device is None

    def test_handle_disconnect_retains_injected_client_reference(self, mock_bleak_client):
        """T-011: handle_disconnect retains injected client object for caller lifecycle."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True
        device._last_notified_states[1] = (True, 1.0)

        device.handle_disconnect()
        assert device.is_connected is False
        assert len(device._last_notified_states) == 0
        assert device.client is mock_bleak_client

    @pytest.mark.asyncio
    async def test_reconnect_delivers_first_state_without_suppression(self, mock_bleak_client):
        """T-011: Reconnecting resets deduplication state so first state packet is delivered."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True
        mock_bleak_client.is_connected = True

        updates = []
        device.register_state_callback(callback=lambda state: updates.append(state))

        # Send state notification
        device._notification_handler("test", bytearray([0x03, 0x01, 0xFF]))
        assert len(updates) == 1

        # Disconnect and reconnect
        await device.disconnect()
        assert device.is_connected is False

        mock_bleak_client.is_connected = True
        await device.connect()
        assert device.is_connected is True

        # Send identical state after reconnect -> must NOT be suppressed
        device._notification_handler("test", bytearray([0x03, 0x01, 0xFF]))
        assert len(updates) == 2
