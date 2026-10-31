"""Casambi BLE device implementation"""

import asyncio
import hashlib
import logging
import struct
from typing import Any, Callable, Dict, Optional, Union

from bleak import BleakClient, BleakScanner, BLEDevice

from .constants import CasambiCommands, CasambiUUIDs

logger = logging.getLogger(__name__)


class CasambiDevice:
    """Represents a Casambi BLE device"""

    def __init__(self, *, address: Union[str, BLEDevice], name: str = "Unknown"):
        if isinstance(address, BLEDevice):
            self.address = address.address
            self.name = address.name or name
            self._ble_device: Optional[BLEDevice] = address
        else:
            self.address = address
            self.name = name
            self._ble_device = None

        self.client: Optional[BleakClient] = None
        self.is_connected = False
        self._notification_callback: Optional[Callable[[bytearray], None]] = None
        self.last_state: dict[str, Any] = {}
        self._control_uuid = CasambiUUIDs.CONTROL_V1
        self._status_uuid = CasambiUUIDs.STATUS_V1
        self._session_key: Optional[bytes] = None

    async def connect(self, *, timeout: float = 30.0) -> bool:
        """Connect to the Casambi device"""
        try:
            # Ensure any old connection is closed
            if self.client:
                try:
                    await self.client.disconnect()
                except Exception:
                    pass

            # Use BLEDevice if we have it, otherwise try to find it
            if not self._ble_device:
                logger.info(f"Searching for device {self.address}...")

                # We'll do one scan and check multiple conditions for each discovered device
                # This is much more reliable than multiple sequential find_device calls
                discovered = await BleakScanner.discover(timeout=timeout / 2, return_adv=True)

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
                            mfr_addr = ":".join(f"{b:02X}" for b in mfr_data[:6]).upper()
                            if mfr_addr == target_upper:
                                logger.info(
                                    f"Matched internal ID in Manufacturer Data: {mfr_addr} (Device: {dev_addr})"
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
            self.client = BleakClient(self._ble_device, timeout=timeout)
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
            logger.info(
                f"Connected and services resolved for {self.name} at {self._ble_device.address}"
            )

            await self.client.start_notify(self._status_uuid, self._notification_handler)

            return True

        except Exception as e:
            logger.error(f"Failed to connect to {self.address}: {e}")
            self.is_connected = False
            # Try to cleanup if stalled
            if self.client:
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            return False

    async def authenticate(self, *, password: str) -> bool:
        """Authenticate with the network password"""
        if not password:
            return True

        # Conservative Classic Handshake: Plain MD5 hash
        # Some 26.x hardware in Classic mode is VERY sensitive to prefix bytes
        password_hash = hashlib.md5(password.encode("utf-8")).digest()
        self._session_key = None  # Disable XOR for standard Classic attempt

        logger.info("Authenticating with network password (Standard Classic)...")
        # Command 0x07 is the standard authentication opcode
        return await self._send_command(command=CasambiCommands.AUTHENTICATE, payload=password_hash)

    async def disconnect(self) -> None:
        """Disconnect from the device"""
        if self.client and self.is_connected:
            try:
                # Only stop notify if we are connected
                try:
                    await self.client.stop_notify(self._status_uuid)
                except Exception:
                    pass
                await self.client.disconnect()
                self.is_connected = False
                logger.info(f"Disconnected from {self.name}")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")

    async def read_status_char(self) -> Optional[bytes]:
        """Perform a direct GATT read on the status characteristic"""
        if not self.is_connected or not self.client:
            return None
        try:
            data = await self.client.read_gatt_char(self._status_uuid)
            logger.info(f"==> DIRECT READ STATUS: {data.hex()}")
            return bytes(data)
        except Exception as e:
            logger.error(f"Failed to read status char: {e}")
            return None

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

        if self._notification_callback:
            self._notification_callback(data)

    def update_from_advertisement(self, *, mfr_data: bytes) -> Optional[Dict[str, Any]]:
        """Update device state from passive advertisement data (ID 963)"""
        if len(mfr_data) < 8:
            return None

        # Verify this data belongs to us (first 6 bytes match address digits)
        addr_clean = self.address.replace(":", "").lower()
        mfr_id_hex = mfr_data[:6].hex().lower()

        # Note: Address can be reversed in some contexts, but internal ID is usually suffix-based
        if mfr_id_hex not in addr_clean and addr_clean not in mfr_id_hex:
            # Check if Reversed
            rev_mfr = "".join(reversed([mfr_id_hex[i : i + 2] for i in range(0, 12, 2)]))
            if rev_mfr not in addr_clean:
                return None

        flags = mfr_data[6]
        is_on = bool(flags & 0x01)
        level_byte = mfr_data[7]

        status = {
            "id": int(mfr_data[0]),  # Approximation of unit ID if needed, though usually internal
            "on": is_on,
            "dimLevel": round(level_byte / 255.0, 3),
            "level_percent": round((level_byte / 255.0) * 100),
            "source": "passive_adv",
        }

        self.last_state = status
        logger.debug(
            f"Passive Update for {self.name}: {'ON' if is_on else 'OFF'} ({status['level_percent']}%)"
        )

        if self._notification_callback:
            # Wrap in bytearray to satisfy callback expectations
            self._notification_callback(bytearray(mfr_data))

        return status

    def parse_status(self, *, data: Union[bytearray, bytes]) -> Dict[str, Any]:
        """
        Parse raw notification data into a dictionary.
        Enriched to match Casambi Cloud API structure.
        """
        if len(data) < 3:
            return {}

        opcode = data[0]
        # Casambi standard status fields
        status: Dict[str, Any] = {
            "opcode": f"{opcode:#02x}",
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

    async def _send_command(self, *, command: int, payload: bytes = b"") -> bool:
        """Send a command to the device"""
        if not self.is_connected or not self.client:
            logger.error("Device not connected")
            return False

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
            logger.debug(f"Sending command {command:#02x} to {self._control_uuid}: {packet.hex()}")

            await self.client.write_gatt_char(self._control_uuid, packet, response=True)
            logger.debug(f"Successfully wrote {len(packet)} bytes")
            return True

        except Exception as e:
            logger.error(f"Failed to send command: {e}")
            return False

    async def turn_on(self, *, unit_id: int = 1) -> bool:
        """Turn on a light unit (using Set Level 100%)"""
        logger.info(f"Switching Unit {unit_id} to state: ON")
        # For 26.xx firmware, Set Level (0x03) + 2-byte Unit + 1-byte Level is most reliable
        # Format: [0x03] [Unit Low] [Unit High] [0xFF]
        payload = struct.pack("<HB", unit_id, 0xFF)
        return await self._send_command(command=CasambiCommands.SET_LEVEL, payload=payload)

    async def turn_off(self, *, unit_id: int = 1) -> bool:
        """Turn off a light unit (using Set Level 0%)"""
        logger.info(f"Switching Unit {unit_id} to state: OFF")
        # Format: [0x03] [Unit Low] [Unit High] [0x00]
        payload = struct.pack("<HB", unit_id, 0x00)
        return await self._send_command(command=CasambiCommands.SET_LEVEL, payload=payload)

    async def turn_on_by_address(self, *, address: str) -> bool:
        """Turn on a light unit by its 6-byte address (Internal ID)"""
        # Command 0x81 (Turn On Long Address). format: [0x81] [6-byte address]
        logger.info(f"Switching Unit at address {address} to state: ON (Direct mode)")
        try:
            addr_bytes = bytes.fromhex(address.replace(":", ""))
            if len(addr_bytes) != 6:
                raise ValueError("Invalid address length")
            return await self._send_command(command=0x81, payload=addr_bytes)
        except Exception as e:
            logger.error(f"Failed to send by address: {e}")
            return False

    async def turn_off_by_address(self, *, address: str) -> bool:
        """Turn off a light unit by its 6-byte address (Internal ID)"""
        # Command 0x82 (Turn Off Long Address)
        logger.info(f"Switching Unit at address {address} to state: OFF (Direct mode)")
        try:
            addr_bytes = bytes.fromhex(address.replace(":", ""))
            if len(addr_bytes) != 6:
                raise ValueError("Invalid address length")
            return await self._send_command(command=0x82, payload=addr_bytes)
        except Exception as e:
            logger.error(f"Failed to send by address: {e}")
            return False

    async def turn_on_broadcast(self) -> bool:
        """Turn on all units in range (Broadcast)"""
        logger.info("Switching ALL reachable units to state: ON (Broadcast)")
        # Broadcast Unit ID is usually 0xFFFF (or 0xFFFE for groups)
        payload = struct.pack("<HB", 0xFFFF, 0xFF)
        return await self._send_command(command=CasambiCommands.SET_LEVEL, payload=payload)

    async def turn_off_broadcast(self) -> bool:
        """Turn off all units in range (Broadcast)"""
        logger.info("Switching ALL reachable units to state: OFF (Broadcast)")
        payload = struct.pack("<HB", 0xFFFF, 0x00)
        return await self._send_command(command=CasambiCommands.SET_LEVEL, payload=payload)

    async def get_state(self, *, unit_id: int) -> None:
        """Request state for a specific unit using multiple methods"""
        # Method 1: Global Get State (0x14)
        payload1 = struct.pack("B", unit_id)
        logger.debug(f"Requesting state via 0x14 for unit {unit_id}")
        await self._send_command(command=CasambiCommands.GET_STATE, payload=payload1)

        await asyncio.sleep(1)

        # Method 2: Specific Unit Query (0x0F)
        # Often required by 26.x hardware
        logger.debug(f"Requesting state via 0x0F for unit {unit_id}")
        await self._send_command(command=CasambiCommands.GET_UNIT_STATE, payload=payload1)

    async def set_level(self, *, unit_id: int, level: float) -> bool:
        """Set brightness level (0.0 - 1.0)"""
        level_byte = int(max(0, min(255, level * 255)))
        # Classic Command 0x03 (Set Level) + 1-byte unit ID + 1-byte level
        payload = struct.pack("BB", unit_id, level_byte)
        return await self._send_command(command=CasambiCommands.SET_LEVEL, payload=payload)

    async def set_color_temperature(self, *, unit_id: int, temp_kelvin: int) -> bool:
        """Set color temperature (2000-6500K)"""
        temp_kelvin = max(2000, min(6500, temp_kelvin))
        payload = struct.pack("BH", unit_id, temp_kelvin)
        return await self._send_command(command=CasambiCommands.SET_COLOR_TEMP, payload=payload)

    async def set_rgb(self, *, unit_id: int, r: int, g: int, b: int) -> bool:
        """Set RGB color (0-255 for each channel)"""
        payload = struct.pack("BBBB", unit_id, r, g, b)
        return await self._send_command(command=CasambiCommands.SET_RGB, payload=payload)

    async def get_device_info(self) -> Dict[str, str]:
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

        except Exception as e:
            logger.error(f"Failed to read device info: {e}")

        return info
