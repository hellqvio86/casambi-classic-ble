import asyncio
import contextlib
import logging
import struct
import warnings
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

MAX_CALLBACK_QUEUE_SIZE: int = 256


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

        pv = getattr(network, "protocol_version", None)
        if not isinstance(pv, int):
            pv = getattr(network, "protocolVersion", 0)
        protocol_version = pv if isinstance(pv, int) else 0

        self._logger.info(
            f"Initializing client for {self.address} with network version {protocol_version}."
        )

        self._check_protocol_version(protocol_version)

    @property
    def _address_or_devive(self) -> str | BLEDevice:
        """Deprecated alias with typo for _address_or_device."""
        warnings.warn(
            "_address_or_devive is deprecated due to typo; use _address_or_device instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._address_or_device

    @abstractmethod
    def _check_protocol_version(self, version: int) -> None:
        pass

    def _checkProtocolVersion(self, version: int) -> None:
        warnings.warn(
            "_checkProtocolVersion is deprecated; use _check_protocol_version instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._check_protocol_version(version)

    def _check_state(self, desired: ConnectionState) -> None:
        if self._connectionState != desired:
            raise ConnectionStateError(desired, self._connectionState)

    def _checkState(self, desired: ConnectionState) -> None:
        warnings.warn(
            "_checkState is deprecated; use _check_state instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._check_state(desired)

    async def _cleanup_callback_task(self) -> None:
        """Cancel, await, and drain callback worker task and queue."""
        if self._callbackTask is not None:
            self._callbackTask.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._callbackTask
            self._callbackTask = None

        if self._callbackQueue is not None:
            while not self._callbackQueue.empty():
                try:
                    self._callbackQueue.get_nowait()
                    self._callbackQueue.task_done()
                except (asyncio.QueueEmpty, ValueError):
                    break
            self._callbackQueue = None

    def _on_callback_task_done(self, task: asyncio.Task[None]) -> None:
        """Observe worker completion to surface exceptions and prevent unhandled task warnings."""
        if task.cancelled():
            return
        err = task.exception()
        if err is not None:
            self._logger.error("Callback worker task failed unexpectedly: %s", err, exc_info=err)

    async def connect(self) -> None:
        self._check_state(ConnectionState.NONE)

        self._logger.info(f"Connection to {self.address}")

        # Reset packet counters
        self._outPacketCount = 1
        self._inPacketCount = 1

        # To use bleak_retry_connector we need to have a BLEDevice so get one if we only have the address.
        device = (
            self._address_or_device
            if isinstance(self._address_or_device, BLEDevice)
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
            self._callbackQueue = asyncio.Queue(maxsize=MAX_CALLBACK_QUEUE_SIZE)
            self._callbackTask = asyncio.create_task(self._process_callbacks())
            self._callbackTask.add_done_callback(self._on_callback_task_done)
            self._connectionState = ConnectionState.CONNECTED
        except BaseException as err:
            await self._cleanup_callback_task()
            if self._gattClient is not None:
                with contextlib.suppress(Exception):
                    await self._gattClient.disconnect()
                self._gattClient = None  # type: ignore[assignment]
            self._connectionState = ConnectionState.NONE
            if isinstance(err, BleakNotFoundError):
                # Guess that this is the error reason since there are no better error types
                self._logger.error("Failed to find unit.", exc_info=True)
                raise BluetoothDeviceNotFoundError("Device not found") from err
            elif isinstance(err, (BleakOutOfConnectionSlotsError, BleakAbortedError)):
                self._logger.warning("Transient connection error", exc_info=True)
                raise BluetoothError(str(err) or "Transient connection error") from err
            elif isinstance(err, BleakError):
                self._logger.error("Failed to connect.", exc_info=True)
                raise BluetoothError(str(err) or "Failed to connect") from err
            elif isinstance(err, Exception):
                self._logger.error("Unknown connection failure.", exc_info=True)
                raise BluetoothError(str(err) or "Unknown connection failure") from err
            raise

        self._logger.info(f"Connected to {self.address}")

    def _on_disconnect(self, client: BleakClient) -> None:
        previous_state = self._connectionState
        # Callbacks may start a reconnect eagerly, before this method returns.
        self._connectionState = ConnectionState.NONE
        if previous_state != ConnectionState.NONE:
            self._logger.info(f"Received disconnect callback from {self.address}")
        if previous_state == ConnectionState.AUTHENTICATED:
            self._logger.debug("Executing disconnect callback.")
            try:
                self._disconnectedCallback()
            except Exception as err:
                self._logger.warning("Error in disconnect callback: %s", err, exc_info=True)

    def _queue_callback(self, handle: BleakGATTCharacteristic, data: bytearray) -> None:
        if self._callbackQueue is not None:
            try:
                self._callbackQueue.put_nowait((handle, data))
            except asyncio.QueueFull:
                self._logger.warning(
                    "Callback queue full (%d items); dropping oldest notification frame to prevent memory leak.",
                    self._callbackQueue.qsize(),
                )
                with contextlib.suppress(asyncio.QueueEmpty, ValueError):
                    self._callbackQueue.get_nowait()
                    self._callbackQueue.task_done()
                with contextlib.suppress(asyncio.QueueFull):
                    self._callbackQueue.put_nowait((handle, data))

    def _queueCallback(self, handle: BleakGATTCharacteristic, data: bytearray) -> None:
        warnings.warn(
            "_queueCallback is deprecated; use _queue_callback instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._queue_callback(handle, data)

    async def _process_callbacks(self) -> None:
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

    async def _processCallbacks(self) -> None:
        warnings.warn(
            "_processCallbacks is deprecated; use _process_callbacks instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self._process_callbacks()

    def _callback_multiplexer(
        self, handle: BleakGATTCharacteristic, data: bytes | bytearray
    ) -> None:
        self._logger.debug(
            f"[CASAMBI_RAW_PACKET] Callback on handle {handle} in state {self._connectionState}: {data.hex()}"
        )

        if self._connectionState == ConnectionState.CONNECTED:
            self._exch_notify_callback(handle, data)
        elif self._connectionState == ConnectionState.KEY_EXCHANGED:
            self._auth_notify_callback(handle, data)
        elif self._connectionState == ConnectionState.AUTHENTICATED:
            self._inPacketCount += 1
            self._established_notify_callback(handle, data)
        else:
            self._logger.warning(
                "Unhandled notify in state %s (%d bytes)", self._connectionState, len(data)
            )

    # Backwards compatibility alias for typo
    _callbackMulitplexer = _callback_multiplexer

    @abstractmethod
    async def exchange_key(self, *, retries: int = 2) -> None:
        pass

    async def exchangeKey(self, *args: Any, **kwargs: Any) -> None:
        warnings.warn(
            "exchangeKey is deprecated; use exchange_key instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        retries = args[0] if args else kwargs.get("retries", 2)
        await self.exchange_key(retries=retries)

    @abstractmethod
    def _exch_notify_callback(
        self, handle: BleakGATTCharacteristic, data: bytes | bytearray
    ) -> None:
        pass

    def _exchNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes | bytearray) -> None:
        warnings.warn(
            "_exchNotifyCallback is deprecated; use _exch_notify_callback instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._exch_notify_callback(handle, data)

    @abstractmethod
    async def authenticate(self) -> None:
        pass

    @abstractmethod
    def _auth_notify_callback(
        self, handle: BleakGATTCharacteristic, data: bytes | bytearray
    ) -> None:
        pass

    def _authNotifyCallback(self, handle: BleakGATTCharacteristic, data: bytes | bytearray) -> None:
        warnings.warn(
            "_authNotifyCallback is deprecated; use _auth_notify_callback instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._auth_notify_callback(handle, data)

    @abstractmethod
    def _established_notify_callback(
        self, handle: BleakGATTCharacteristic, data: bytes | bytearray
    ) -> None:
        pass

    def _establishedNotifyCallback(
        self, handle: BleakGATTCharacteristic, data: bytes | bytearray
    ) -> None:
        warnings.warn(
            "_establishedNotifyCallback is deprecated; use _established_notify_callback instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._established_notify_callback(handle, data)

    async def send(self, packet: bytes, *, retries: int = 2) -> None:
        self._check_state(ConnectionState.AUTHENTICATED)

        async with self._activityLock:
            self._logger.debug(f"Sending packet {packet.hex()} with counter {self._outPacketCount}")
            retry = 0
            while True:
                try:
                    await self._send_internal(packet)
                    break
                except BluetoothError:
                    retry += 1
                    if retry > retries:
                        raise
                    await asyncio.sleep(0.5)

            self._outPacketCount += 1

    @abstractmethod
    async def _send_internal(self, packet: bytes) -> None:
        pass

    async def _sendInternal(self, packet: bytes) -> None:
        warnings.warn(
            "_sendInternal is deprecated; use _send_internal instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self._send_internal(packet)

    async def disconnect(self) -> None:
        self._logger.info("Disconnecting...")
        try:
            await self._cleanup_callback_task()
            if self._gattClient is not None:
                with contextlib.suppress(Exception):
                    await self._gattClient.stop_notify(CASA_AUTH_CHAR_UUID)
                try:
                    await self._gattClient.disconnect()
                except BleakError:
                    self._logger.debug("Failed to disconnect BleakClient.", exc_info=True)
                except Exception as err:
                    self._logger.warning("Unexpected error during BleakClient disconnect: %s", err)
        finally:
            self._callbackQueue = None
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

        keystore = getattr(network, "keystore", None)
        if keystore is None or (
            hasattr(network, "keyStore")
            and network.keyStore is not keystore
            and not hasattr(keystore, "get_legacy_key")
        ):
            keystore = getattr(network, "keyStore", None)

        visitorKey = None
        if keystore is not None:
            if hasattr(keystore, "get_legacy_key"):
                visitorKey = keystore.get_legacy_key(role=CLASSIC_AUTH_LEVEL_VISITOR)
            elif hasattr(keystore, "getLegacyKey"):
                visitorKey = keystore.getLegacyKey(CLASSIC_AUTH_LEVEL_VISITOR)

        if not visitorKey:
            raise ProtocolError("Can't continue without visitor key.")
        self._visitorEncryptor = ClassicEncryptor(visitorKey.key, 4)

        self._managerEncryptor: ClassicEncryptor | None = None
        managerKey = None
        if keystore is not None:
            if hasattr(keystore, "get_legacy_key"):
                managerKey = keystore.get_legacy_key(role=CLASSIC_AUTH_LEVEL_MANAGER)
            elif hasattr(keystore, "getLegacyKey"):
                managerKey = keystore.getLegacyKey(CLASSIC_AUTH_LEVEL_MANAGER)

        if managerKey:
            self._managerEncryptor = ClassicEncryptor(managerKey.key, 16)
        else:
            self._managerEncryptor = None
            self._logger.warning(
                "No manager key in keystore. Manager level packets won't be handled correctly."
            )

    def _check_protocol_version(self, version: int) -> None:
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

    async def exchange_key(self, *, retries: int = 2) -> None:
        self._check_state(ConnectionState.CONNECTED)
        if self._gattClient is None:
            self._connectionState = ConnectionState.NONE
            raise ConnectionStateError(ConnectionState.CONNECTED, ConnectionState.NONE)

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
            try:
                (
                    self._connhash,
                    self._unit,
                    flags_lo,
                    self._mtu,
                    protocolVersion,
                    flags_high,
                ) = struct.unpack_from(">8sBBBBB", firstResp)
            except struct.error as err:
                raise ProtocolError(
                    f"Malformed device info response in key exchange: {err}"
                ) from err
            self._flags = flags_lo | (flags_high << 8)

            pv = getattr(self._network, "protocol_version", None)
            if not isinstance(pv, int):
                pv = getattr(self._network, "protocolVersion", 0)
            expected_version = pv if isinstance(pv, int) else 0

            if protocolVersion != expected_version:
                self._logger.warning(
                    "Device reported unexpected version. Was %i, expected %i.",
                    protocolVersion,
                    expected_version,
                )

            self._check_protocol_version(protocolVersion)

            self._logger.debug(
                f"Parsed mtu {self._mtu}, unit {self._unit}, flags {self._flags}, connhash set (8 bytes)"
            )

            self._logger.debug("Starting notify")
            try:
                await self._gattClient.start_notify(
                    CASA_AUTH_CHAR_UUID,
                    self._queue_callback,
                    bluez={"use_start_notify": True},
                )
            except BleakError as err:
                raise BluetoothError("Failed to initiate GATT notify.") from err
            self._connectionState = ConnectionState.KEY_EXCHANGED

    def _exch_notify_callback(
        self, handle: BleakGATTCharacteristic, data: bytes | bytearray
    ) -> None:
        raise ProtocolError("Refusing to handle callback at this time for classic network.")

    async def authenticate(self) -> None:
        self._check_state(ConnectionState.KEY_EXCHANGED)

        async with self._activityLock:
            # We only send the version for now and not the time.
            self._logger.info("Sending version.")
            await self._send_internal(b"\x00\x01\x0b")
            # Manually increment since we have to bypass send due to locking.
            self._outPacketCount += 1

            self._connectionState = ConnectionState.AUTHENTICATED

    def _auth_notify_callback(
        self, handle: BleakGATTCharacteristic, data: bytes | bytearray
    ) -> None:
        raise ProtocolError("Refusing to handle callback at this time for classic network.")

    def _established_notify_callback(
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

    async def _send_internal(self, packet: bytes) -> None:
        if self._gattClient is None:
            self._connectionState = ConnectionState.NONE
            raise ConnectionStateError(ConnectionState.AUTHENTICATED, ConnectionState.NONE)

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
