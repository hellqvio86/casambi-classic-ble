import asyncio
import contextlib
import logging
import struct
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakAbortedError,
    BleakNotFoundError,
    BleakOutOfConnectionSlotsError,
    close_stale_connections,
    establish_connection,
    get_device,
)

from ._constants import (
    CASA_AUTH_CHAR_UUID,
    CLASSIC_AUTH_LEVEL_MANAGER,
    CLASSIC_AUTH_LEVEL_VISITOR,
    FIRST_UNSUPPORTED_PROTOCOL_VERSION,
    MIN_SUPPORTED_CLASSIC_VERSION,
    IncomingPacketType,
)
from ._constants import (
    ConnectionState as ConnectionState,
)
from ._encryption import ClassicEncryptor
from ._network import Network
from ._switch import SwitchEventDecoder

# We need to move these imports here to prevent a cycle.
from .exceptions import (
    BluetoothDeviceNotFoundError,
    BluetoothError,
    ConnectionStateError,
    ProtocolError,
    UnsupportedProtocolVersion,
)


class CasambiClient(ABC):
    def __init__(
        self,
        address_or_device: str | BLEDevice,
        dataCallback: Callable[[IncomingPacketType, Any], None],
        disconnected_callback: Callable[[], None] | None = None,
        network: Network | None = None,
        *,
        disonnectedCallback: Callable[[], None] | None = None,
    ) -> None:
        disc_cb = (
            disconnected_callback if disconnected_callback is not None else disonnectedCallback
        )
        if disc_cb is None:
            raise ValueError("disconnected_callback is required")
        if network is None:
            raise ValueError("network is required")

        self._gattClient: BleakClient = None  # type: ignore[assignment]
        self._network = network

        self._mtu: int
        self._unitId: int
        self._flags: int

        self._outPacketCount = 0
        self._inPacketCount = 0

        self._callbackQueue: asyncio.Queue[tuple[BleakGATTCharacteristic, bytearray]] | None = None
        self._callbackTask: asyncio.Task[None] | None = None

        self._address_or_device = address_or_device
        self._address_or_devive = address_or_device  # Deprecated alias
        self.address = (
            address_or_device.address
            if isinstance(address_or_device, BLEDevice)
            else address_or_device
        )
        self._logger = logging.getLogger(__name__)
        self._switch_decoder = SwitchEventDecoder()
        self._connectionState: ConnectionState = ConnectionState.NONE
        self._dataCallback = dataCallback
        self._disconnectedCallback = disc_cb
        self._activityLock = asyncio.Lock()

        self._logger.info(
            f"Initializing client for {self.address} with network version {network.protocolVersion}."
        )

        self._checkProtocolVersion(network.protocolVersion)

    @abstractmethod
    def _checkProtocolVersion(self, version: int) -> None:
        pass

    def _checkState(self, desired: ConnectionState) -> None:
        if self._connectionState != desired:
            raise ConnectionStateError(desired, self._connectionState)

    async def _cleanup_callback_task(self) -> None:
        """Cancel and wait for callback worker task."""
        if self._callbackTask is not None:
            self._callbackTask.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._callbackTask
            self._callbackTask = None

    async def connect(self) -> None:
        self._checkState(ConnectionState.NONE)

        self._logger.info(f"Connection to {self.address}")

        # Reset packet counters
        self._outPacketCount = 1
        self._inPacketCount = 1

        # To use bleak_retry_connector we need to have a BLEDevice so get one if we only have the address.
        device = (
            self._address_or_devive
            if isinstance(self._address_or_devive, BLEDevice)
            else await get_device(self.address)
        )

        if not device:
            self._logger.error("Failed to discover unit.")
            raise BluetoothDeviceNotFoundError

        try:
            # If we are already connected to the device the key exchange will fail.
            await close_stale_connections(device)
            # TODO: Should we try to get access to the network name here?
            # Using the service cache leads to bugs so disable it.
            self._gattClient = await establish_connection(
                BleakClient,
                device,
                "Casambi Network",
                self._on_disconnect,
                use_services_cache=False,
            )
            # Reset callback queue and spawn task only after connection succeeds
            self._callbackQueue = asyncio.Queue()
            self._callbackTask = asyncio.create_task(self._processCallbacks())
        except BleakNotFoundError as err:
            await self._cleanup_callback_task()
            # Guess that this is the error reason since there are no better error types
            self._logger.error("Failed to find unit.", exc_info=True)
            raise BluetoothDeviceNotFoundError("Device not found") from err
        except (BleakOutOfConnectionSlotsError, BleakAbortedError) as err:
            await self._cleanup_callback_task()
            self._logger.warning("Transient connection error", exc_info=True)
            raise BluetoothError(str(err) or "Transient connection error") from err
        except BleakError as err:
            await self._cleanup_callback_task()
            self._logger.error("Failed to connect.", exc_info=True)
            raise BluetoothError(str(err) or "Failed to connect") from err
        except BaseException as err:
            await self._cleanup_callback_task()
            if isinstance(err, Exception):
                self._logger.error("Unknown connection failure.", exc_info=True)
                raise BluetoothError(str(err) or "Unknown connection failure") from err
            raise

        self._logger.info(f"Connected to {self.address}")
        self._connectionState = ConnectionState.CONNECTED

    def _on_disconnect(self, client: BleakClient) -> None:
        previous_state = self._connectionState
        # Callbacks may start a reconnect eagerly, before this method returns.
        self._connectionState = ConnectionState.NONE
        if previous_state != ConnectionState.NONE:
            self._logger.info(f"Received disconnect callback from {self.address}")
        if previous_state == ConnectionState.AUTHENTICATED:
            self._logger.debug("Executing disconnect callback.")
            self._disconnectedCallback()

    def _queueCallback(self, handle: BleakGATTCharacteristic, data: bytearray) -> None:
        if self._callbackQueue is not None:
            self._callbackQueue.put_nowait((handle, data))

    async def _processCallbacks(self) -> None:
        try:
            while True:
                if self._callbackQueue is None:
                    break
                handle, data = await self._callbackQueue.get()

                # Try to loose any races here.
                # Otherwise a state change caused by the last packet might not have been handled yet
                await asyncio.sleep(0.001)
                async with self._activityLock:
                    try:
                        self._callback_multiplexer(handle, data)
                    except Exception:
                        self._logger.error("Failed to process callback.", exc_info=True)
                    finally:
                        if self._callbackQueue is not None:
                            self._callbackQueue.task_done()
        except asyncio.CancelledError:
            self._logger.info("Callback processing task cancelled.")
            raise

    def _callback_multiplexer(
        self, handle: BleakGATTCharacteristic, data: bytes | bytearray
    ) -> None:
        self._logger.debug(
            f"[CASAMBI_RAW_PACKET] Callback on handle {handle} in state {self._connectionState}: {data.hex()}"
        )

        if self._connectionState == ConnectionState.CONNECTED:
            self._exchNotifyCallback(handle, data)
        elif self._connectionState == ConnectionState.KEY_EXCHANGED:
            self._authNotifyCallback(handle, data)
        elif self._connectionState == ConnectionState.AUTHENTICATED:
            self._inPacketCount += 1
            self._establishedNotifyCallback(handle, data)
        else:
            self._logger.warning(
                "Unhandled notify in state %s (%d bytes)", self._connectionState, len(data)
            )

    # Backwards compatibility alias for typo
    _callbackMulitplexer = _callback_multiplexer

    @abstractmethod
    async def exchangeKey(self, retries: int = 2) -> None:
        pass

    @abstractmethod
    def _exchNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes | bytearray) -> None:
        pass

    @abstractmethod
    async def authenticate(self) -> None:
        pass

    @abstractmethod
    def _authNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes | bytearray) -> None:
        pass

    @abstractmethod
    def _establishedNotifyCallback(
        self, handle: BleakGATTCharacteristic, data: bytes | bytearray
    ) -> None:
        pass

    async def send(self, packet: bytes, retries: int = 2) -> None:
        self._checkState(ConnectionState.AUTHENTICATED)

        async with self._activityLock:
            self._logger.debug(f"Sending packet {packet.hex()} with counter {self._outPacketCount}")
            retry = 0
            while True:
                try:
                    await self._sendInternal(packet)
                    break
                except BluetoothError:
                    retry += 1
                    if retry > retries:
                        raise
                    await asyncio.sleep(0.5)

            self._outPacketCount += 1

    @abstractmethod
    async def _sendInternal(self, packet: bytes) -> None:
        pass

    async def disconnect(self) -> None:
        self._logger.info("Disconnecting...")

        await self._cleanup_callback_task()

        if self._gattClient is not None:
            try:
                await self._gattClient.disconnect()
            except BleakError:
                self._logger.debug("Failed to disconnect BleakClient.", exc_info=True)

        self._connectionState = ConnectionState.NONE
        self._switch_decoder.reset()
        self._logger.info("Disconnected.")


class CasambiClientClassic(CasambiClient):
    """This is a client implementation for conformant classic networks."""

    def __init__(
        self,
        address_or_device: str | BLEDevice,
        dataCallback: Callable[[IncomingPacketType, Any], None],
        disconnected_callback: Callable[[], None] | None = None,
        network: Network | None = None,
        *,
        disonnectedCallback: Callable[[], None] | None = None,
    ) -> None:
        disc_cb = (
            disconnected_callback if disconnected_callback is not None else disonnectedCallback
        )
        if disc_cb is None:
            raise ValueError("disconnected_callback is required")
        if network is None:
            raise ValueError("network is required")
        super().__init__(
            address_or_device,
            dataCallback,
            disconnected_callback=disc_cb,
            network=network,
        )
        self._connhash: bytes

        visitorKey = network.keyStore.getLegacyKey(CLASSIC_AUTH_LEVEL_VISITOR)
        if not visitorKey:
            raise ProtocolError("Can't continue without visitor key.")
        self._visitorEncryptor = ClassicEncryptor(visitorKey.key, 4)

        self._managerEncryptor: ClassicEncryptor | None
        managerKey = network.keyStore.getLegacyKey(CLASSIC_AUTH_LEVEL_MANAGER)
        if managerKey:
            self._managerEncryptor = ClassicEncryptor(managerKey.key, 16)
        else:
            self._managerEncryptor = None
            self._logger.warning(
                "No manager key in keystore. Manager level packets won't be handled correctly."
            )

    def _checkProtocolVersion(self, version: int) -> None:
        if version >= FIRST_UNSUPPORTED_PROTOCOL_VERSION:
            raise UnsupportedProtocolVersion(
                f"Protocol version {version} is not supported. This library is strictly for "
                f"Classic firmware (versions < {FIRST_UNSUPPORTED_PROTOCOL_VERSION}). "
                f"Use upstream casambi-bt for newer firmware."
            )

        if version < MIN_SUPPORTED_CLASSIC_VERSION:
            raise UnsupportedProtocolVersion(
                f"Network version {version} is too old. Nonconformant classic networks currently not supported."
                f"Minimum supported version is {MIN_SUPPORTED_CLASSIC_VERSION}."
            )

    async def exchangeKey(self, retries: int = 2) -> None:
        self._checkState(ConnectionState.CONNECTED)

        self._logger.info("Starting key exchange...")

        async with self._activityLock:
            # Initiate communication with device.  The initial GATT read can fail
            # transiently (e.g. ATT error 0x0e) if the device is not yet ready for
            # GATT operations immediately after connection.  Retry with the same
            # policy used by send().
            retry = 0
            while True:
                try:
                    firstResp = await self._gattClient.read_gatt_char(CASA_AUTH_CHAR_UUID)
                    break
                except BleakError as err:
                    retry += 1
                    if retry > retries:
                        raise BluetoothError("Failed to initiate GATT read.") from err
                    self._logger.debug("Transient error reading auth characteristic, retrying...")
                    await asyncio.sleep(0.5)
            self._logger.debug(f"Got {firstResp.hex()}")

            # Parse device info
            (
                self._connhash,
                self._unit,
                flags_lo,
                self._mtu,
                protocolVersion,
                flags_high,
            ) = struct.unpack_from(">8sBBBBB", firstResp)
            self._flags = flags_lo | (flags_high << 8)

            if protocolVersion != self._network.protocolVersion:
                self._logger.warning(
                    "Device reported unexpected version. Was %i, expected %i.",
                    protocolVersion,
                    self._network.protocolVersion,
                )

            self._checkProtocolVersion(protocolVersion)

            self._logger.debug(
                f"Parsed mtu {self._mtu}, unit {self._unit}, flags {self._flags}, connhash set (8 bytes)"
            )

            self._logger.debug("Starting notify")
            try:
                await self._gattClient.start_notify(
                    CASA_AUTH_CHAR_UUID,
                    self._queueCallback,
                    bluez={"use_start_notify": True},
                )
            except BleakError as err:
                raise BluetoothError("Failed to initiate GATT notify.") from err
            self._connectionState = ConnectionState.KEY_EXCHANGED

    def _exchNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes | bytearray) -> None:
        raise ProtocolError("Refusing to handle callback at this time for classic network.")

    async def authenticate(self) -> None:
        self._checkState(ConnectionState.KEY_EXCHANGED)

        async with self._activityLock:
            # We only send the version for now and not the time.
            self._logger.info("Sending version.")
            await self._sendInternal(b"\x00\x01\x0b")
            # Manually increment since we have to bypass send due to locking.
            self._outPacketCount += 1

            self._connectionState = ConnectionState.AUTHENTICATED

    def _authNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes | bytearray) -> None:
        raise ProtocolError("Refusing to handle callback at this time for classic network.")

    def _establishedNotifyCallback(
        self, handle: BleakGATTCharacteristic, data: bytes | bytearray
    ) -> None:
        self._logger.debug(f"Incoming data: {data.hex()}")

        if len(data) < 1:
            self._logger.error("Malformed packet: received empty notification frame. Ignoring.")
            return

        unitId = data[0]
        if unitId == 0x00:
            # Network config. Skipping.
            pass
        elif unitId == 0xFF:
            # Log marker. Skipping.
            pass
        elif unitId == 0xF0:
            # Response
            pass
        else:
            pos = 0
            while pos < len(data):
                if pos + 2 > len(data):
                    self._logger.error(
                        "Malformed packet: incomplete header at position %d (frame length %d, packet=%s). Abort.",
                        pos,
                        len(data),
                        data.hex(),
                    )
                    break

                flags = data[pos + 1]

                stateLen = flags & 0x0F
                prio = flags & 0x10 != 0
                extra1 = flags & 0x20 != 0
                extra2 = flags & 0x40 != 0
                online = flags & 0x80 != 0

                statePos = pos + 2
                extra1Val = -1
                extra2Val = -1

                if extra1:
                    if statePos >= len(data):
                        self._logger.error(
                            "Malformed packet: truncated frame reading extra1 at pos %d (packet=%s). Abort.",
                            pos,
                            data.hex(),
                        )
                        break
                    extra1Val = data[statePos]
                    statePos += 1
                if extra2:
                    if statePos >= len(data):
                        self._logger.error(
                            "Malformed packet: truncated frame reading extra2 at pos %d (packet=%s). Abort.",
                            pos,
                            data.hex(),
                        )
                        break
                    extra2Val = data[statePos]
                    statePos += 1

                if statePos + stateLen > len(data):
                    self._logger.error(
                        "Malformed packet: truncated payload of length %d at pos %d (frame length %d, packet=%s). Abort.",
                        stateLen,
                        pos,
                        len(data),
                        data.hex(),
                    )
                    break

                unitId = data[pos]
                state = data[statePos : statePos + stateLen]

                self._logger.debug(
                    f"Parsed state: Len {stateLen}, id {unitId}, prio {prio}, online {online}, extra1 {extra1Val}, extra2 {extra2Val}, state {state.hex()}."
                )

                # It's ok to pass anything as on. The value will only be used if no appropriate controls are available.
                self._dataCallback(
                    IncomingPacketType.UnitState,
                    {"id": unitId, "online": online, "on": True, "state": state},
                )

                pos = statePos + stateLen

    async def _sendInternal(self, packet: bytes) -> None:
        sequence = int.to_bytes(self._outPacketCount & 0xFFFF, 2, "big")
        if sequence == b"\x00\x00":
            sequence = b"\x00\x01"
            self._outPacketCount += 1

        outPacket = sequence + packet
        if self._managerEncryptor:
            outPacket = b"\x03" + self._managerEncryptor.digest(outPacket, self._connhash)
        else:
            outPacket = b"\x02" + self._visitorEncryptor.digest(outPacket, self._connhash)

        self._logger.debug(
            "Sending signed packet (%d bytes, auth_level=0x%02x)",
            len(outPacket),
            outPacket[0],
        )

        try:
            await self._gattClient.write_gatt_char(CASA_AUTH_CHAR_UUID, outPacket)
        except BleakError as err:
            if err.args and err.args[0] == "Not connected":
                self._logger.debug("Unexpected write while disconnected.", exc_info=True)
                self._connectionState = ConnectionState.NONE
                raise ConnectionStateError(
                    ConnectionState.AUTHENTICATED, ConnectionState.NONE
                ) from err
            raise BluetoothError from err
