"""Casambi BLE device implementation"""

import asyncio
import hashlib
import logging
import platform
import struct
from collections.abc import Callable
from typing import Any

from bleak import BleakClient, BleakScanner, BLEDevice

from ._adv import _internal_address, matches_advertisement_address
from .constants import CasambiCommands, CasambiUUIDs
from .exceptions import (
    CasambiCommandError,
    CasambiConnectionError,
    CasambiDeviceError,
)

logger = logging.getLogger(__name__)


class CasambiDevice:
    """Represents a Casambi BLE device"""

    def __init__(
        self,
        *,
        address: str | BLEDevice,
        name: str = "Unknown",
        client: BleakClient | None = None,
    ):
        if isinstance(address, BLEDevice):
            self.address = address.address
            self.name = address.name or name
            self._ble_device: BLEDevice | None = address
        else:
            self.address = address
            self.name = name
            self._ble_device = None

        self._internal_address: str | None = None

        self.client: BleakClient | None = client
        self.is_connected = False
        self._notification_callback: Callable[[bytearray], None] | None = None
        self._disconnect_callback: Callable[[], None] | None = None
        self._write_lock: asyncio.Lock = asyncio.Lock()
        self.last_state: dict[str, Any] = {}
        self._state_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._last_notified_states: dict[Any, tuple[bool, float]] = {}
        self._control_uuid = CasambiUUIDs.CONTROL_V1
        self._status_uuid = CasambiUUIDs.STATUS_V1
        self._session_key: bytes | None = None

    def set_disconnected_callback(self, *, callback: Callable[[], None]) -> None:
        """Set callback invoked on unexpected disconnection"""
        self._disconnect_callback = callback

    def register_state_callback(
        self, *, callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback for state changes (with duplicate suppression). Returns unsubscribe callable."""
        self._state_callbacks.append(callback)

        def unsubscribe() -> None:
            if callback in self._state_callbacks:
                self._state_callbacks.remove(callback)

        return unsubscribe

    def _on_bleak_disconnect(self, client: BleakClient) -> None:
        """Internal callback invoked when Bleak drops connection"""
        self.is_connected = False
        logger.info(f"Device {self.name} disconnected from BLE stack")
        if self._disconnect_callback:
            try:
                self._disconnect_callback()
            except Exception as err:
                logger.warning(f"Error in disconnect callback: {err}", exc_info=True)

    async def connect(self, *, timeout: float = 30.0) -> bool:
        """Connect to the Casambi device (idempotent if already connected)"""
        if self.is_connected and self.client and getattr(self.client, "is_connected", False):
            logger.debug(f"Device {self.name} is already connected.")
            return True
        try:
            # If no pre-injected client, find/connect the device
            if not self.client:
                # Use BLEDevice if we have it, otherwise try to find it
                if not self._ble_device:
                    logger.info(f"Searching for device {self.address}...")

                    # We'll do one scan and check multiple conditions for each discovered device
                    # This is much more reliable than multiple sequential find_device calls
                    if platform.system() == "Darwin":
                        discovered = await BleakScanner.discover(
                            timeout=timeout / 2, return_adv=True, cb={"use_bdaddr": True}
                        )
                    else:
                        discovered = await BleakScanner.discover(
                            timeout=timeout / 2, return_adv=True
                        )

                    target_upper = self.address.upper()
                    target_reversed = None
                    if ":" in target_upper:
                        parts = target_upper.split(":")
                        if len(parts) == 6:
                            target_reversed = ":".join(reversed(parts))

                    for dev, adv in discovered.values():
                        found = False
                        dev_addr = dev.address.upper()
                        # 1. Match address
                        if dev_addr == target_upper:
                            logger.info(f"Matched target address: {dev_addr}")
                            found = True
                        # 2. Match reversed address
                        elif target_reversed and dev_addr == target_reversed:
                            logger.info(f"Matched reversed address: {dev_addr}")
                            found = True
                        # 3. Match Manufacturer Data (Casambi ID 963 = 0x03C3)
                        else:
                            mfr_data = adv.manufacturer_data.get(963)
                            if mfr_data and len(mfr_data) >= 6:
                                if matches_advertisement_address(
                                    target_address=self.address, mfr_data=mfr_data
                                ):
                                    logger.info(
                                        f"Matched internal ID in Manufacturer Data (Device: {dev_addr})"
                                    )
                                    found = True

                        if found:
                            self._ble_device = dev
                            break
                        else:
                            logger.debug(f"Skipping device {dev_addr} ({dev.name})")

                if not self._ble_device:
                    logger.error(f"Device {self.address} not found.")
                    return False

                logger.info(f"Connecting to {self._ble_device.address}...")
                try:
                    from bleak_retry_connector import establish_connection

                    self.client = await establish_connection(
                        client_class=BleakClient,
                        device=self._ble_device,
                        name=self.name,
                        timeout=timeout,
                        disconnected_callback=self._on_bleak_disconnect,
                    )
                except Exception as err:
                    logger.warning(
                        f"establish_connection failed, falling back to direct BleakClient: {err}"
                    )
                    self.client = BleakClient(
                        self._ble_device,
                        timeout=timeout,
                        disconnected_callback=self._on_bleak_disconnect,
                    )
                    await self.client.connect()
            elif not getattr(self.client, "is_connected", False):
                await self.client.connect()

            # Discover services to determine which characteristics to use
            services = self.client.services
            if CasambiUUIDs.SERVICE_V2.lower() in [s.uuid.lower() for s in services]:
                logger.info("Using protocol variant 2 (FE4D)")
                self._control_uuid = CasambiUUIDs.CONTROL_V2
                self._status_uuid = CasambiUUIDs.STATUS_V2
            else:
                logger.info("Using protocol variant 1 (FE3D)")
                self._control_uuid = CasambiUUIDs.CONTROL_V1
                self._status_uuid = CasambiUUIDs.STATUS_V1

            self.is_connected = True
            dev_addr = self._ble_device.address if self._ble_device else self.address
            logger.info(f"Connected and services resolved for {self.name} at {dev_addr}")

            await self.client.start_notify(self._status_uuid, self._notification_handler)

            return True

        except asyncio.CancelledError:
            self.is_connected = False
            raise
        except Exception as err:
            logger.error(f"Failed to connect to {self.address}: {err}")
            self.is_connected = False
            # Try to cleanup if stalled
            if self.client:
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            return False

    async def authenticate(self, *, password: str) -> None:
        """Authenticate with the network password"""
        if not password:
            return

        if not self.is_connected or not self.client:
            raise CasambiConnectionError("Device not connected")

        # Conservative Classic Handshake: Plain MD5 hash
        # Some 26.x hardware in Classic mode is VERY sensitive to prefix bytes
        # False positive: MD5 password hash is mandated by Casambi Classic BLE radio protocol
        # codeql[py/weak-sensitive-data-hashing]
        password_hash = hashlib.md5(password.encode("utf-8")).digest()
        self._session_key = None  # Disable XOR for standard Classic attempt

        logger.info("Authenticating with network password (Standard Classic)...")
        # Command 0x07 is the standard authentication opcode
        await self._send_command(command=CasambiCommands.AUTHENTICATE, payload=password_hash)

    async def disconnect(self) -> None:
        """Disconnect from the device"""
        if not self.is_connected:
            return

        if self.client:
            try:
                # Only stop notify if we are connected
                try:
                    await self.client.stop_notify(self._status_uuid)
                except Exception:
                    pass
                await self.client.disconnect()
                self.is_connected = False
                logger.info(f"Disconnected from {self.name}")
            except asyncio.CancelledError:
                self.is_connected = False
                raise
            except Exception as err:
                logger.error(f"Error disconnecting: {err}")
                self.is_connected = False

    async def read_status_char(self) -> bytes | None:
        """Perform a direct GATT read on the status characteristic"""
        if not self.is_connected or not self.client:
            return None
        try:
            data = await self.client.read_gatt_char(self._status_uuid)
            logger.info(f"==> DIRECT READ STATUS: {data.hex()}")
            return bytes(data)
        except Exception as err:
            logger.error(f"Failed to read status char: {err}")
            return None

    def _dispatch_state(self, *, status: dict[str, Any]) -> None:
        """Dispatch state update to registered state callbacks with per-unit duplicate suppression."""
        unit_key = status.get("id", self.address)
        is_on = bool(status.get("on", False))
        dim_level = float(status.get("dimLevel", 0.0))
        current_state_tuple = (is_on, dim_level)

        if self._last_notified_states.get(unit_key) != current_state_tuple:
            self._last_notified_states[unit_key] = current_state_tuple
            for cb in list(self._state_callbacks):
                try:
                    cb(status)
                except Exception as err:
                    logger.warning(f"Error in state change callback: {err}", exc_info=True)

    def _notification_handler(self, sender: Any, data: bytearray) -> None:
        """Handle incoming notifications from device"""
        hex_data = data.hex()
        logger.info(f"==> BLE NOTIFICATION: {hex_data} (from {sender})")

        status = self.parse_status(data=data)
        if status:
            self.last_state = status
            state_str = "ON" if status.get("on", False) else "OFF"
            level = status.get("level_percent", 0)
            unit = status.get("id", "Unknown")
            logger.info(f"    PARSED: Unit {unit} is {state_str} ({level}%)")
            self._dispatch_state(status=status)

        if self._notification_callback:
            try:
                self._notification_callback(data)
            except Exception as err:
                logger.warning(f"Error in notification callback: {err}", exc_info=True)

    def update_from_advertisement(
        self,
        *,
        mfr_data: bytes | bytearray,
        ble_device: BLEDevice | None = None,
    ) -> dict[str, Any] | None:
        """Update device state from passive advertisement data (ID 963)"""
        if not isinstance(mfr_data, (bytes, bytearray)) or len(mfr_data) < 8:
            return None

        matched = False
        # 1. Caller passed BLEDevice matching this instance (e.g. from scanner or macOS UUID)
        if ble_device is not None:
            if (
                self._ble_device is not None and ble_device == self._ble_device
            ) or ble_device.address.upper() == self.address.upper():
                matched = True

        # 2. Check cached internal address or target address against beacon MAC bytes
        if not matched:
            if self._internal_address and matches_advertisement_address(
                target_address=self._internal_address, mfr_data=mfr_data
            ):
                matched = True
            elif matches_advertisement_address(target_address=self.address, mfr_data=mfr_data):
                matched = True

        if not matched:
            return None

        # Cache internal address (reversed MAC order per quirk #1)
        _, rev_mac = _internal_address(mfr_data=mfr_data)
        self._internal_address = rev_mac

        flags = mfr_data[6]
        is_on = bool(flags & 0x01)
        level_byte = mfr_data[7]
        dim_level = round(level_byte / 255.0, 3)

        status: dict[str, Any] = {
            "on": is_on,
            "dimLevel": dim_level,
            "level_percent": round((level_byte / 255.0) * 100),
            "source": "passive_adv",
            "address_byte": int(mfr_data[0]),
        }

        self.last_state = status
        logger.debug(
            f"Passive Update for {self.name}: {'ON' if is_on else 'OFF'} ({status['level_percent']}%)"
        )

        if self._notification_callback:
            try:
                # Wrap in bytearray to satisfy callback expectations
                self._notification_callback(bytearray(mfr_data))
            except Exception as err:
                logger.warning(f"Error in notification callback: {err}", exc_info=True)

        self._dispatch_state(status=status)

        return status

    def parse_status(self, *, data: bytearray | bytes) -> dict[str, Any]:
        """
        Parse raw notification data into a dictionary.
        Enriched to match Casambi Cloud API structure.
        """
        if not isinstance(data, (bytes, bytearray)) or len(data) < 3:
            return {}

        opcode = data[0]
        # Only parse opcodes that have golden vector captures / hardware evidence (0x03)
        # TODO(hardware-capture): Add parsers for additional opcodes when hardware captures are available
        if opcode != 0x03:
            logger.debug(f"Ignoring notification frame with unhandled opcode: {opcode:#04x}")
            return {}

        # Casambi standard status fields
        status: dict[str, Any] = {
            "opcode": f"{opcode:#04x}",
            "id": data[1],  # unitId
            "on": data[2] > 0,
            "dimLevel": round((data[2] / 255.0), 3),
            "status": "ok",
            "online": True,
        }

        # Human readable level for logging
        level_pct = round((data[2] / 255.0) * 100)
        status["level_percent"] = level_pct

        return status

    def set_notification_callback(self, *, callback: Callable[[bytearray], None]) -> None:
        """Set callback for notifications"""
        self._notification_callback = callback

    async def _send_command(self, *, command: int, payload: bytes = b"") -> None:
        """Send a command to the device, serialized with write lock"""
        if not self.is_connected or not self.client:
            raise CasambiConnectionError("Device not connected")

        async with self._write_lock:
            try:
                # Opcode is the first byte, remains unencrypted
                # Payload follows and must be XORed if we are in a Protected mesh
                if self._session_key and command != CasambiCommands.AUTHENTICATE:
                    xor_payload = bytearray()
                    for i, byte in enumerate(payload):
                        # Rotate through 4-byte session key
                        xor_payload.append(byte ^ self._session_key[i % 4])
                    payload = bytes(xor_payload)

                packet = struct.pack("B", command) + payload
                logger.debug(
                    f"Sending command {command:#02x} to {self._control_uuid}: {packet.hex()}"
                )

                await self.client.write_gatt_char(self._control_uuid, packet, response=True)
                logger.debug(f"Successfully wrote {len(packet)} bytes")

            except asyncio.CancelledError:
                raise
            except Exception as err:
                logger.error(f"Failed to send command {command:#02x}: {err}")
                raise CasambiCommandError(f"Failed to send command {command:#02x}: {err}") from err

    async def turn_on(self, *, unit_id: int | None = None) -> None:
        """Turn on a light unit or all units if unit_id is None."""
        if unit_id is None:
            await self.turn_on_broadcast()
            return

        if not (0 <= unit_id <= 255):
            raise CasambiDeviceError(f"unit_id must be between 0 and 255, got {unit_id}")
        logger.info(f"Switching Unit {unit_id} to state: ON")
        # For 26.xx firmware, Set Level (0x03) + 2-byte Unit + 1-byte Level is most reliable
        # Format: [0x03] [Unit Low] [Unit High] [0xFF]
        payload = struct.pack("<HB", unit_id, 0xFF)
        await self._send_command(command=CasambiCommands.SET_LEVEL, payload=payload)

    async def turn_off(self, *, unit_id: int | None = None) -> None:
        """Turn off a light unit or all units if unit_id is None."""
        if unit_id is None:
            await self.turn_off_broadcast()
            return

        if not (0 <= unit_id <= 255):
            raise CasambiDeviceError(f"unit_id must be between 0 and 255, got {unit_id}")
        logger.info(f"Switching Unit {unit_id} to state: OFF")
        # Format: [0x03] [Unit Low] [Unit High] [0x00]
        payload = struct.pack("<HB", unit_id, 0x00)
        await self._send_command(command=CasambiCommands.SET_LEVEL, payload=payload)

    async def turn_on_by_address(self, *, address: str) -> None:
        """Turn on a light unit by its 6-byte address (Internal ID)"""
        # Command 0x81 (Turn On Long Address). format: [0x81] [6-byte address]
        logger.info(f"Switching Unit at address {address} to state: ON (Direct mode)")
        try:
            addr_bytes = bytes.fromhex(address.replace(":", ""))
            if len(addr_bytes) != 6:
                raise ValueError("Invalid address length")
        except Exception as err:
            raise CasambiDeviceError(f"Invalid address '{address}': {err}") from err
        await self._send_command(command=0x81, payload=addr_bytes)

    async def turn_off_by_address(self, *, address: str) -> None:
        """Turn off a light unit by its 6-byte address (Internal ID)"""
        # Command 0x82 (Turn Off Long Address)
        logger.info(f"Switching Unit at address {address} to state: OFF (Direct mode)")
        try:
            addr_bytes = bytes.fromhex(address.replace(":", ""))
            if len(addr_bytes) != 6:
                raise ValueError("Invalid address length")
        except Exception as err:
            raise CasambiDeviceError(f"Invalid address '{address}': {err}") from err
        await self._send_command(command=0x82, payload=addr_bytes)

    async def turn_on_broadcast(self) -> None:
        """Turn on all units in range (Broadcast)"""
        logger.info("Switching ALL reachable units to state: ON (Broadcast)")
        # Broadcast Unit ID is usually 0xFFFF (or 0xFFFE for groups)
        payload = struct.pack("<HB", 0xFFFF, 0xFF)
        await self._send_command(command=CasambiCommands.SET_LEVEL, payload=payload)

    async def turn_off_broadcast(self) -> None:
        """Turn off all units in range (Broadcast)"""
        logger.info("Switching ALL reachable units to state: OFF (Broadcast)")
        payload = struct.pack("<HB", 0xFFFF, 0x00)
        await self._send_command(command=CasambiCommands.SET_LEVEL, payload=payload)

    async def get_state(self, *, unit_id: int) -> None:
        """Request state for a specific unit using multiple methods"""
        if not (0 <= unit_id <= 255):
            raise CasambiDeviceError(f"unit_id must be between 0 and 255, got {unit_id}")
        # Method 1: Global Get State (0x14)
        payload1 = struct.pack("B", unit_id)
        logger.debug(f"Requesting state via 0x14 for unit {unit_id}")
        await self._send_command(command=CasambiCommands.GET_STATE, payload=payload1)

        await asyncio.sleep(1)

        # Method 2: Specific Unit Query (0x0F)
        # Often required by 26.x hardware
        logger.debug(f"Requesting state via 0x0F for unit {unit_id}")
        await self._send_command(command=CasambiCommands.GET_UNIT_STATE, payload=payload1)

    async def set_level(self, *, level: float, unit_id: int | None = None) -> None:
        """Set brightness level (0.0 - 1.0) for a unit or all units if unit_id is None."""
        if not (0.0 <= level <= 1.0):
            raise CasambiDeviceError(f"level must be between 0.0 and 1.0, got {level}")
        level_byte = round(level * 255)
        if unit_id is None:
            payload = struct.pack("<HB", 0xFFFF, level_byte)
        else:
            if not (0 <= unit_id <= 255):
                raise CasambiDeviceError(f"unit_id must be between 0 and 255, got {unit_id}")
            # Classic Command 0x03 (Set Level) + 1-byte unit ID + 1-byte level
            payload = struct.pack("BB", unit_id, level_byte)
        await self._send_command(command=CasambiCommands.SET_LEVEL, payload=payload)

    async def set_color_temperature(self, *, temp_kelvin: int, unit_id: int = 1) -> None:
        """Set color temperature (2000-6500K)"""
        if not (0 <= unit_id <= 255):
            raise CasambiDeviceError(f"unit_id must be between 0 and 255, got {unit_id}")
        if not (2000 <= temp_kelvin <= 6500):
            raise CasambiDeviceError(
                f"temp_kelvin must be between 2000 and 6500K, got {temp_kelvin}"
            )
        payload = struct.pack("<BH", unit_id, temp_kelvin)
        await self._send_command(command=CasambiCommands.SET_COLOR_TEMP, payload=payload)

    async def set_rgb(self, *, r: int, g: int, b: int, unit_id: int = 1) -> None:
        """Set RGB color (0-255 for each channel)"""
        if not (0 <= unit_id <= 255):
            raise CasambiDeviceError(f"unit_id must be between 0 and 255, got {unit_id}")
        for channel_name, val in (("r", r), ("g", g), ("b", b)):
            if not (0 <= val <= 255):
                raise CasambiDeviceError(
                    f"RGB channel '{channel_name}' must be between 0 and 255, got {val}"
                )
        payload = struct.pack("BBBB", unit_id, r, g, b)
        await self._send_command(command=CasambiCommands.SET_RGB, payload=payload)

    async def get_device_info(self) -> dict[str, str]:
        """Read device information"""
        info = {}
        try:
            if self.client:
                mfr = await self.client.read_gatt_char(CasambiUUIDs.MANUFACTURER_NAME)
                info["manufacturer"] = mfr.decode("utf-8")

                model = await self.client.read_gatt_char(CasambiUUIDs.MODEL_NUMBER)
                info["model"] = model.decode("utf-8")

                try:
                    fw = await self.client.read_gatt_char(CasambiUUIDs.FIRMWARE_REVISION)
                    info["firmware"] = fw.decode("utf-8")
                except Exception:
                    pass

        except Exception as err:
            logger.error(f"Failed to read device info: {err}")

        return info
