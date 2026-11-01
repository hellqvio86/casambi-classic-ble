"""Casambi BLE device implementation"""

import asyncio
import contextlib
import hashlib
import logging
import platform
import struct
import warnings
from collections.abc import Callable
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection, get_device

from ._adv import _internal_address, matches_advertisement_address
from .constants import CasambiCommands, CasambiUUIDs
from .exceptions import (
    CasambiCommandError,
    CasambiConnectionError,
    CasambiDeviceError,
    CasambiDeviceNotFoundError,
)

logger = logging.getLogger(__name__)


def _parse_address_bytes(*, address: str) -> bytes:
    """Parse and validate a 6-byte hexadecimal address string into raw bytes.

    Args:
        address: Bluetooth MAC or internal address string (e.g. 'AA:BB:CC:DD:EE:FF' or 'aabbccddeeff').

    Returns:
        bytes: 6-byte address as raw bytes.

    Raises:
        CasambiDeviceError: If the address is invalid hex or does not have exactly 6 bytes.
    """
    cleaned = address.replace(":", "").replace("-", "").strip()
    try:
        addr_bytes = bytes.fromhex(cleaned)
    except ValueError as err:
        raise CasambiDeviceError(f"Invalid address format '{address}': {err}") from err

    if len(addr_bytes) != 6:
        raise CasambiDeviceError(
            f"Invalid address length for '{address}': expected 6 bytes, got {len(addr_bytes)}"
        )

    return addr_bytes


class CasambiDevice:
    """Represents a Casambi BLE device"""

    def __init__(
        self,
        *,
        address: str | BLEDevice,
        name: str = "Unknown",
        client: BleakClient | None = None,
    ):
        """Initialize a Casambi BLE device.

        Contract for injected BleakClient:
        When passing a pre-existing BleakClient via the `client` parameter (e.g. from
        Home Assistant's bluetooth manager), CasambiDevice does not manage its discovery
        lifecycle. If the external BLE stack disconnects the client, callers should invoke
        `handle_disconnect()` to reset internal connection and deduplication state.
        """
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
        self._injected_client: bool = client is not None
        self._is_connected: bool = False
        self._notification_callbacks: list[Callable[[bytearray], None]] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []
        self._write_lock: asyncio.Lock = asyncio.Lock()
        self.last_state: dict[str, Any] = {}
        self._state_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._last_notified_states: dict[Any, tuple[bool, float]] = {}
        self._control_uuid = CasambiUUIDs.CONTROL_V1
        self._status_uuid = CasambiUUIDs.STATUS_V1

    @property
    def is_connected(self) -> bool:
        """Whether the device is currently connected."""
        if self.client is not None:
            return self._is_connected and bool(getattr(self.client, "is_connected", False))
        return self._is_connected

    @is_connected.setter
    def is_connected(self, value: bool) -> None:
        """Set connection state (for testing/mocking)."""
        self._is_connected = bool(value)

    def handle_disconnect(self) -> None:
        """Handle disconnection event from external BLE stack or injected client."""
        self._is_connected = False
        self._last_notified_states.clear()
        if not self._injected_client:
            self.client = None
            self._ble_device = None
        logger.info(f"Device {self.name} disconnected from BLE stack")
        for cb in list(self._disconnect_callbacks):
            try:
                cb()
            except Exception as err:
                logger.warning(f"Error in disconnect callback: {err}", exc_info=True)

    def _on_bleak_disconnect(self, client: BleakClient) -> None:
        """Internal callback invoked when Bleak drops connection."""
        self.handle_disconnect()

    def register_disconnect_callback(self, *, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback invoked on unexpected disconnection. Returns unsubscribe callable."""
        self._disconnect_callbacks.append(callback)

        def unsubscribe() -> None:
            if callback in self._disconnect_callbacks:
                self._disconnect_callbacks.remove(callback)

        return unsubscribe

    def set_disconnected_callback(self, *, callback: Callable[[], None]) -> None:
        """Deprecated: use register_disconnect_callback instead."""
        warnings.warn(
            "set_disconnected_callback is deprecated; use register_disconnect_callback instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.register_disconnect_callback(callback=callback)

    def register_notification_callback(
        self, *, callback: Callable[[bytearray], None]
    ) -> Callable[[], None]:
        """Register a callback for raw GATT notifications. Returns unsubscribe callable."""
        self._notification_callbacks.append(callback)

        def unsubscribe() -> None:
            if callback in self._notification_callbacks:
                self._notification_callbacks.remove(callback)

        return unsubscribe

    def set_notification_callback(self, *, callback: Callable[[bytearray], None]) -> None:
        """Deprecated: use register_notification_callback instead."""
        warnings.warn(
            "set_notification_callback is deprecated; use register_notification_callback instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.register_notification_callback(callback=callback)

    def register_state_callback(
        self, *, callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback for state changes (with duplicate suppression). Returns unsubscribe callable."""
        self._state_callbacks.append(callback)

        def unsubscribe() -> None:
            if callback in self._state_callbacks:
                self._state_callbacks.remove(callback)

        return unsubscribe

    async def connect(self, *, timeout: float = 30.0) -> None:
        """Connect to the Casambi device (idempotent if already connected)."""
        if self._is_connected and self.client and getattr(self.client, "is_connected", False):
            logger.debug(f"Device {self.name} is already connected.")
            return

        self._last_notified_states.clear()

        try:
            # If no pre-injected client, find/connect the device
            if not self.client:
                # Fast lookup via bleak_retry_connector
                if not self._ble_device:
                    try:
                        self._ble_device = await get_device(self.address)
                    except Exception as err:
                        logger.debug(f"Fast lookup failed for {self.address}: {err}")
                        self._ble_device = None

                # Fallback to scanning if fast lookup did not find the device
                if not self._ble_device:
                    logger.debug("Searching for device %s...", self.address)
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
                            logger.debug("Matched target address: %s", dev_addr)
                            found = True
                        # 2. Match reversed address
                        elif target_reversed and dev_addr == target_reversed:
                            logger.debug("Matched reversed address: %s", dev_addr)
                            found = True
                        # 3. Match Manufacturer Data (Casambi ID 963 = 0x03C3)
                        else:
                            mfr_data = adv.manufacturer_data.get(963)
                            if mfr_data and len(mfr_data) >= 6:
                                if matches_advertisement_address(
                                    target_address=self.address, mfr_data=mfr_data
                                ):
                                    logger.debug(
                                        "Matched internal ID in Manufacturer Data (Device: %s)",
                                        dev_addr,
                                    )
                                    found = True

                        if found:
                            self._ble_device = dev
                            break
                        else:
                            logger.debug("Skipping device %s (%s)", dev_addr, dev.name)

                if not self._ble_device:
                    logger.error("Device %s not found.", self.address)
                    raise CasambiDeviceNotFoundError(f"Device {self.address} not found")

                logger.debug("Connecting to %s...", self._ble_device.address)
                try:
                    self.client = await establish_connection(
                        client_class=BleakClient,
                        device=self._ble_device,
                        name=self.name,
                        timeout=timeout,
                        disconnected_callback=self._on_bleak_disconnect,
                    )
                except Exception as err:
                    logger.error(f"Failed to establish connection to {self.address}: {err}")
                    raise CasambiConnectionError(
                        f"Failed to connect to {self.address}: {err}"
                    ) from err
            elif not getattr(self.client, "is_connected", False):
                try:
                    await self.client.connect()
                except Exception as err:
                    logger.error(f"Failed to connect injected client: {err}")
                    raise CasambiConnectionError(
                        f"Failed to connect to {self.address}: {err}"
                    ) from err

            # Discover services to determine which characteristics to use
            try:
                services = self.client.services
                service_uuids = [s.uuid.lower() for s in services]
                if CasambiUUIDs.SERVICE_V2.lower() in service_uuids:
                    logger.info("Using protocol variant 2 (FE4D)")
                    self._control_uuid = CasambiUUIDs.CONTROL_V2
                    self._status_uuid = CasambiUUIDs.STATUS_V2
                elif CasambiUUIDs.SERVICE_V1.lower() in service_uuids:
                    logger.info("Using protocol variant 1 (FE3D)")
                    self._control_uuid = CasambiUUIDs.CONTROL_V1
                    self._status_uuid = CasambiUUIDs.STATUS_V1
                else:
                    raise CasambiDeviceError(
                        f"Device {self.address} does not support Casambi Classic services "
                        f"({CasambiUUIDs.SERVICE_V2} or {CasambiUUIDs.SERVICE_V1}). "
                        "Evolution firmware or non-Casambi devices are not supported."
                    )

                self._is_connected = True
                dev_addr = self._ble_device.address if self._ble_device else self.address
                logger.info("Connected and services resolved for %s", self.name)
                logger.debug("Resolved device address: %s", dev_addr)

                await self.client.start_notify(self._status_uuid, self._notification_handler)
            except CasambiDeviceError:
                self._is_connected = False
                if self.client:
                    with contextlib.suppress(Exception):
                        await self.client.disconnect()
                raise
            except Exception as err:
                logger.error(f"Failed to resolve services or start notifications: {err}")
                self._is_connected = False
                if self.client:
                    with contextlib.suppress(Exception):
                        await self.client.disconnect()
                raise CasambiConnectionError(f"Failed to configure connection: {err}") from err

        except (CasambiDeviceNotFoundError, CasambiConnectionError, CasambiDeviceError):
            self._is_connected = False
            raise
        except asyncio.CancelledError:
            self._is_connected = False
            raise
        except Exception as err:
            logger.error(f"Failed to connect to {self.address}: {err}")
            self._is_connected = False
            if self.client:
                with contextlib.suppress(Exception):
                    await self.client.disconnect()
            raise CasambiConnectionError(f"Failed to connect to {self.address}: {err}") from err

    async def authenticate(self, *, password: str) -> None:
        """Authenticate with the network password.

        Note: In the Casambi Classic protocol, authentication is performed by
        transmitting the MD5-hashed network password opcode to the control characteristic.
        Successful completion of this write confirms that the BLE packet was transmitted
        and acknowledged by the GATT server, but the protocol does not return an explicit
        authentication success or failure response.
        """
        if not password:
            raise CasambiDeviceError("Password required")

        if not self.is_connected or not self.client:
            raise CasambiConnectionError("Device not connected")

        # Conservative Classic Handshake: Plain MD5 hash
        # Some 26.x hardware in Classic mode is VERY sensitive to prefix bytes
        # False positive: MD5 password hash is mandated by Casambi Classic BLE radio protocol
        # codeql[py/weak-sensitive-data-hashing]
        password_hash = hashlib.md5(password.encode("utf-8")).digest()

        logger.info("Authenticating with network password (Standard Classic)...")
        # Command 0x07 is the standard authentication opcode
        await self._send_command(command=CasambiCommands.AUTHENTICATE, payload=password_hash)

    async def disconnect(self) -> None:
        """Disconnect from the device"""
        if not self._is_connected and self.client is None:
            return

        if self.client:
            try:
                # Only stop notify if we are connected
                if getattr(self.client, "is_connected", False):
                    with contextlib.suppress(Exception):
                        await self.client.stop_notify(self._status_uuid)
                with contextlib.suppress(Exception):
                    await self.client.disconnect()
                logger.info(f"Disconnected from {self.name}")
            except asyncio.CancelledError:
                self.handle_disconnect()
                raise
            except Exception as err:
                logger.error(f"Error disconnecting: {err}")
            finally:
                self.handle_disconnect()
        else:
            self.handle_disconnect()

    async def read_status_char(self) -> bytes:
        """Perform a direct GATT read on the status characteristic"""
        if not self.is_connected or not self.client:
            raise CasambiConnectionError("Device not connected")
        try:
            data = await self.client.read_gatt_char(self._status_uuid)
            logger.debug("Direct read status char (%d bytes)", len(data))
            return bytes(data)
        except Exception as err:
            logger.error(f"Failed to read status char: {err}")
            raise CasambiDeviceError(f"Failed to read status char: {err}") from err

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
        logger.debug("BLE notification received from %s (%d bytes)", sender, len(data))

        status = self.parse_status(data=data)
        if status:
            self.last_state = status
            state_str = "ON" if status.get("on", False) else "OFF"
            level = status.get("level_percent", 0)
            unit = status.get("id", "Unknown")
            logger.debug("Parsed notification: Unit %s is %s (%s%%)", unit, state_str, level)
            self._dispatch_state(status=status)

        for cb in list(self._notification_callbacks):
            try:
                cb(data)
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

        self._dispatch_state(status=status)

        return status

    def parse_status(self, *, data: bytearray | bytes) -> dict[str, Any]:
        """
        Parse raw notification data into a dictionary.
        Enriched to match Casambi Cloud API structure.
        """
        if not isinstance(data, (bytes, bytearray)) or len(data) < 3:
            logger.error(
                "Malformed packet: status notification frame length %d is too short (expected >= 3 bytes).",
                len(data) if isinstance(data, (bytes, bytearray)) else 0,
            )
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

    async def _send_command(self, *, command: int, payload: bytes = b"") -> None:
        """Send a command to the device, serialized with write lock"""
        if not self.is_connected or not self.client:
            raise CasambiConnectionError("Device not connected")

        async with self._write_lock:
            try:
                packet = struct.pack("B", command) + payload
                logger.debug(
                    "Sending command %#02x to %s (%d bytes)",
                    command,
                    self._control_uuid,
                    len(packet),
                )

                await self.client.write_gatt_char(self._control_uuid, packet, response=True)
                logger.debug("Successfully wrote %d bytes", len(packet))

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
        """Turn on a light unit by its 6-byte address (Internal ID)."""
        logger.info("Switching Unit directly to state: ON")
        addr_bytes = _parse_address_bytes(address=address)
        await self._send_command(command=CasambiCommands.TURN_LIGHT_ON_LONG, payload=addr_bytes)

    async def turn_off_by_address(self, *, address: str) -> None:
        """Turn off a light unit by its 6-byte address (Internal ID)."""
        logger.info("Switching Unit directly to state: OFF")
        addr_bytes = _parse_address_bytes(address=address)
        await self._send_command(command=CasambiCommands.TURN_LIGHT_OFF_LONG, payload=addr_bytes)

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

    async def request_state(self, *, unit_id: int, settle: float = 1.0) -> None:
        """Request state for a specific unit using multiple methods.

        Queries the device for state via command 0x14 followed by 0x0F after settle duration.
        Incoming state updates will be delivered asynchronously via registered state callbacks.
        """
        if not (0 <= unit_id <= 255):
            raise CasambiDeviceError(f"unit_id must be between 0 and 255, got {unit_id}")
        # Method 1: Global Get State (0x14)
        payload1 = struct.pack("B", unit_id)
        logger.debug(f"Requesting state via 0x14 for unit {unit_id}")
        await self._send_command(command=CasambiCommands.GET_STATE, payload=payload1)

        if settle > 0:
            await asyncio.sleep(settle)

        # Method 2: Specific Unit Query (0x0F)
        # Often required by 26.x hardware
        logger.debug(f"Requesting state via 0x0F for unit {unit_id}")
        await self._send_command(command=CasambiCommands.GET_UNIT_STATE, payload=payload1)

    async def get_state(self, *, unit_id: int) -> None:
        """Deprecated: use request_state instead."""
        warnings.warn(
            "get_state is deprecated and will be removed in a future release; use request_state instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.request_state(unit_id=unit_id, settle=1.0)

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

    async def set_color_temperature(self, *, unit_id: int, temp_kelvin: int) -> None:
        """Set color temperature (2000-6500K)"""
        if not (0 <= unit_id <= 255):
            raise CasambiDeviceError(f"unit_id must be between 0 and 255, got {unit_id}")
        if not (2000 <= temp_kelvin <= 6500):
            raise CasambiDeviceError(
                f"temp_kelvin must be between 2000 and 6500K, got {temp_kelvin}"
            )
        payload = struct.pack("<BH", unit_id, temp_kelvin)
        await self._send_command(command=CasambiCommands.SET_COLOR_TEMP, payload=payload)

    async def set_rgb(self, *, unit_id: int, r: int, g: int, b: int) -> None:
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
        if not self.is_connected or not self.client:
            raise CasambiConnectionError("Device not connected")

        info: dict[str, str] = {}
        try:
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
            raise CasambiDeviceError(f"Failed to read device info: {err}") from err

        return info
