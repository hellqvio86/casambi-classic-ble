import asyncio
import logging
import warnings
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

from bleak.backends.device import BLEDevice
from httpx import AsyncClient, RequestError

from ._cache import Cache
from ._client import (
    CasambiClient,
    CasambiClientClassic,
)
from ._constants import ConnectionState, IncomingPacketType, isClassicNetwork
from ._network import Network
from ._operation import (
    OpCode,
    OperationsContext,
    OperationsContextClassic,
)
from ._switch import SwitchEvent
from ._unit import Group, Scene, Unit, UnitControl, UnitControlType, UnitState
from .exceptions import ConnectionStateError, UnsupportedProtocolVersion


class Casambi:
    """Class to manage one Casambi network.

    This is the central point of interaction and should be preferred to dealing with the internal components,
    e.g. ``Network`` or ``CasambiClient``, directly.
    """

    def __init__(
        self,
        *args: Any,
        http_client: AsyncClient | None = None,
        cache_path: Path | None = None,
        httpClient: AsyncClient | None = None,
        cachePath: Path | None = None,
    ) -> None:
        target_http = (
            http_client
            if http_client is not None
            else (httpClient if httpClient is not None else (args[0] if len(args) > 0 else None))
        )
        target_cache = (
            cache_path
            if cache_path is not None
            else (cachePath if cachePath is not None else (args[1] if len(args) > 1 else None))
        )
        if args or httpClient is not None or cachePath is not None:
            warnings.warn(
                "Casambi positional arguments or camelCase parameters are deprecated; "
                "use Casambi(http_client=..., cache_path=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        self._casaClient: CasambiClient | None = None
        self._casaNetwork: Network | None = None

        self._unitChangedCallbacks: list[Callable[[Unit], None]] = []
        self._switchEventCallbacks: list[Callable[[SwitchEvent], None]] = []
        self._disconnectCallbacks: list[Callable[[], None]] = []
        self._connectionLock = asyncio.Lock()

        self._logger = logging.getLogger(__name__)
        self._opContext: OperationsContext
        self._ownHttpClient = target_http is None
        self._httpClient = target_http

        self._cache = Cache(cache_path=target_cache)

    def _check_network(self) -> None:
        if not self._casaNetwork or not self._casaNetwork._networkRevision:
            raise ConnectionStateError(
                ConnectionState.AUTHENTICATED,
                ConnectionState.NONE,
                "Network information missing.",
            )

    def _checkNetwork(self) -> None:
        warnings.warn(
            "_checkNetwork is deprecated; use _check_network instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._check_network()

    @property
    def network_name(self) -> str:
        self._check_network()
        return self._casaNetwork._networkName  # type: ignore

    @property
    def networkName(self) -> str:
        warnings.warn(
            "networkName is deprecated; use network_name instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.network_name

    @property
    def network_id(self) -> str:
        self._check_network()
        return self._casaNetwork._id  # type: ignore

    @property
    def networkId(self) -> str:
        warnings.warn(
            "networkId is deprecated; use network_id instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.network_id

    @property
    def units(self) -> list[Unit]:
        """Get the units in the network if connected.

        :return: A list of all units in the network.
        :raises ConnectionStateError: There is no connection to the network.
        """
        self._check_network()
        return self._casaNetwork.units  # type: ignore

    @property
    def groups(self) -> list[Group]:
        """Get the groups in the network if connected.

        :return: A list of all groups in the network.
        :raises ConnectionStateError: There is no connection to the network.
        """
        self._check_network()
        return self._casaNetwork.groups  # type: ignore

    @property
    def scenes(self) -> list[Scene]:
        """Get the scenes of the network if connected.

        :return: A list of all scenes in the network.
        :raises ConnectionStateError: There is no connection to the network.
        """
        self._check_network()
        return self._casaNetwork.scenes  # type: ignore

    @property
    def connected(self) -> bool:
        """Check whether there is an active connection to the network."""
        return (
            self._casaClient is not None
            and self._casaClient._connectionState == ConnectionState.AUTHENTICATED
        )

    async def connect(
        self,
        *args: Any,
        address: str | BLEDevice | None = None,
        password: str | None = None,
        force_offline: bool = False,
        addr_or_device: str | BLEDevice | None = None,
        forceOffline: bool = False,
    ) -> None:
        """Connect and authenticate to a network.

        :param address: The MAC address of the network or a BLEDevice.
        :param password: The password for the network.
        :param force_offline: Whether to avoid contacting the casambi servers.
        :raises AuthenticationError: The supplied password is invalid.
        :raises ProtocolError: The network did not follow the expected protocol.
        :raises NetworkNotFoundError: No network was found under the supplied address.
        :raises NetworkOnlineUpdateNeededError: An offline update isn't possible in the current state.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        :raises BluetoothDeviceNotFoundError: The bluetooth device belonging to the network can't be found.
        """
        target_addr = (
            address
            if address is not None
            else (
                addr_or_device
                if addr_or_device is not None
                else (args[0] if len(args) > 0 else None)
            )
        )
        target_pw = password if password is not None else (args[1] if len(args) > 1 else None)
        target_offline = force_offline or forceOffline or (args[2] if len(args) > 2 else False)

        if target_addr is None:
            raise ValueError("address is required")
        if target_pw is None:
            raise ValueError("password is required")

        if args or addr_or_device is not None or forceOffline:
            warnings.warn(
                "connect positional arguments or camelCase parameters are deprecated; "
                "use connect(address=..., password=..., force_offline=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        if isinstance(target_addr, BLEDevice):
            addr = target_addr.address
        else:
            # Add colons if necessary.
            if ":" not in target_addr:
                target_addr = ":".join(["".join(p) for p in pairwise(target_addr)][::2])
            addr = target_addr

        self._logger.info(f"Trying to connect to casambi network {addr}...")

        if not self._httpClient:
            self._httpClient = AsyncClient()

        # Retrieve network information
        uuid = addr.replace(":", "").lower()
        await self._cache.set_uuid(uuid=uuid)
        self._casaNetwork = Network(uuid, self._httpClient, self._cache)
        await self._casaNetwork.load()
        try:
            await self._casaNetwork.log_in(password=target_pw, force_offline=target_offline)
        except RequestError:
            self._logger.warning(
                "Network error while logging in. Trying to continue offline.",
                exc_info=True,
            )
            target_offline = True

        await self._casaNetwork.update(force_offline=target_offline)
        await self._connect_client(target_addr)

    async def reconnect(
        self,
        *args: Any,
        address: str | BLEDevice | None = None,
        addr_or_device: str | BLEDevice | None = None,
    ) -> None:
        """Reestablish the bluetooth connection.

        :param address: The MAC address of the network or a BLEDevice.
        :raises ProtocolError: The network did not follow the expected protocol.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        :raises BluetoothDeviceNotFoundError: The bluetooth device belonging to the network can't be found.
        """
        target_addr = (
            address
            if address is not None
            else (addr_or_device if addr_or_device is not None else (args[0] if args else None))
        )
        if target_addr is None:
            raise ValueError("address is required")
        if args or addr_or_device is not None:
            warnings.warn(
                "reconnect positional arguments or addr_or_device are deprecated; use reconnect(address=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        self._check_network()
        async with self._connectionLock:
            if self._casaClient is None:
                raise ConnectionStateError(
                    ConnectionState.CONNECTED,
                    ConnectionState.NONE,
                    "Reconnect only possible after initial connection and before disconnect.",
                )
            if self.connected:
                return
            await self._casaClient.disconnect()
            await self._connect_client(target_addr)

    async def _connect_client(self, addr_or_device: str | BLEDevice) -> None:
        """Initiate the bluetooth connection."""
        self._casaNetwork = cast(Network, self._casaNetwork)

        pv = getattr(self._casaNetwork, "protocol_version", None)
        if not isinstance(pv, int):
            pv = getattr(self._casaNetwork, "protocolVersion", 0)
        net_version = pv if isinstance(pv, int) else 0

        if isClassicNetwork(net_version):
            self._casaClient = CasambiClientClassic(
                addr_or_device,
                self._data_callback,
                self._disconnect_callback,
                self._casaNetwork,
            )
            self._opContext = OperationsContextClassic()
        else:
            raise UnsupportedProtocolVersion(
                f"Protocol version {net_version} is not supported. "
                "This library is strictly for Classic firmware. "
                "Use upstream casambi-bt for newer firmware."
            )
        try:
            await self._casaClient.connect()
            await self._casaClient.exchange_key()
            await self._casaClient.authenticate()
        except BaseException:
            await self._casaClient.disconnect()
            raise

    async def _connectClient(self, addr_or_device: str | BLEDevice) -> None:
        warnings.warn(
            "_connectClient is deprecated; use _connect_client instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self._connect_client(addr_or_device)

    async def set_unit_state(
        self,
        *args: Any,
        target: Unit | None = None,
        state: UnitState | None = None,
    ) -> None:
        """Set the state of one unit directly.

        :param target: The targeted unit.
        :param state: The desired state.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        state_val = args[1] if len(args) > 1 else state
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use set_unit_state(target=..., state=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if target_val is None or state_val is None:
            raise ValueError("target and state are required")

        for c in target_val.unitType.controls:
            c_val = c.type.value if hasattr(c.type, "value") else c.type
            if c_val == UnitControlType.DIMMER.value and state_val.dimmer is not None:
                await self.set_level(target=target_val, level=state_val.dimmer)
            elif c_val == UnitControlType.TEMPERATURE.value and state_val.temperature is not None:
                await self.set_temperature(target=target_val, temperature=state_val.temperature)
            elif c_val == UnitControlType.VERTICAL.value and state_val.vertical is not None:
                await self.set_vertical(target=target_val, vertical=state_val.vertical)
            elif c_val == UnitControlType.WHITE.value and state_val.white is not None:
                await self.set_white(target=target_val, level=state_val.white)
            elif c_val == UnitControlType.RGB.value and state_val.rgb is not None:
                await self.set_color(target=target_val, rgb_color=state_val.rgb)

    async def setUnitState(
        self,
        *args: Any,
        target: Unit | None = None,
        state: UnitState | None = None,
    ) -> None:
        """Deprecated alias for set_unit_state."""
        warnings.warn(
            "setUnitState is deprecated; use set_unit_state instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_unit_state(*args, target=target, state=state)

    async def set_control_value(
        self,
        *args: Any,
        unit: Unit | None = None,
        control: UnitControl | None = None,
        value: int | None = None,
    ) -> None:
        """Set a single control's value and send the updated state.

        The state is built from the unit's current raw state bytes with only
        the bits described by ``control`` overwritten.  All other controls —
        including UNKNOWN ones — remain unchanged.

        :param unit: The target unit.
        :param control: A :class:`UnitControl` from ``unit.unitType.controls``.
        :param value: Raw integer value to write into the control's bit field.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        unit_val = args[0] if len(args) > 0 else unit
        control_val = args[1] if len(args) > 1 else control
        value_val = args[2] if len(args) > 2 else value
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use set_control_value(unit=..., control=..., value=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if unit_val is None or control_val is None or value_val is None:
            raise ValueError("unit, control, and value are required")

        if unit_val.state is not None and unit_val.state.raw_state is not None:
            raw = bytearray(unit_val.state.raw_state)
        else:
            raw = bytearray(unit_val.unitType.stateLength)

        # Clear the target bits then write the new value (little-endian bytes).
        byte_start = control_val.offset // 8
        bit_start = control_val.offset % 8
        n_bytes = (control_val.length + bit_start + 7) // 8

        current = int.from_bytes(raw[byte_start : byte_start + n_bytes], byteorder="little")
        mask = ((1 << control_val.length) - 1) << bit_start
        current = (current & ~mask) | ((value_val & ((1 << control_val.length) - 1)) << bit_start)
        raw[byte_start : byte_start + n_bytes] = current.to_bytes(n_bytes, byteorder="little")

        state_bytes = bytes(raw)
        await self._send(unit_val, state_bytes, OpCode.SetState)
        unit_val.set_state_from_bytes(value=state_bytes)

    async def setControlValue(
        self,
        *args: Any,
        unit: Unit | None = None,
        control: UnitControl | None = None,
        value: int | None = None,
    ) -> None:
        """Deprecated alias for set_control_value."""
        warnings.warn(
            "setControlValue is deprecated; use set_control_value instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_control_value(*args, unit=unit, control=control, value=value)

    async def set_white_color_balance(
        self,
        *args: Any,
        unit: Unit | None = None,
        value: int | None = None,
    ) -> None:
        """Set the white/color balance for a unit with a WHITECOLORBALANCE control.

        ``value`` is the raw 6-bit cross-fade level in the range [0, 63].
        0 = pure white channel, 63 = pure color channel.

        The balance is written via :meth:`set_control_value` which manipulates the
        raw state bytes in-place and sends a ``SetState`` opcode, so all other
        controls (brightness, colour, temperature) are preserved.

        :param unit: The target unit.  Must have a ``WHITECOLORBALANCE`` control.
        :param value: Raw balance level in range [0, 63].
        :raises ValueError: The unit does not support ``WHITECOLORBALANCE``, or value out of range.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        unit_val = args[0] if len(args) > 0 else unit
        value_val = args[1] if len(args) > 1 else value
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use set_white_color_balance(unit=..., value=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if unit_val is None or value_val is None:
            raise ValueError("unit and value are required")
        if value_val < 0 or value_val > 63:
            raise ValueError(f"White/color balance value {value_val} is not in range [0, 63].")
        control = unit_val.unitType.get_control(UnitControlType.WHITECOLORBALANCE)
        if control is None:
            raise ValueError("The unit does not support WHITECOLORBALANCE.")
        await self.set_control_value(unit=unit_val, control=control, value=value_val)

    async def setWhiteColorBalance(
        self,
        *args: Any,
        unit: Unit | None = None,
        value: int | None = None,
    ) -> None:
        """Deprecated alias for set_white_color_balance."""
        warnings.warn(
            "setWhiteColorBalance is deprecated; use set_white_color_balance instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_white_color_balance(*args, unit=unit, value=value)

    async def set_level(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        level: int | None = None,
    ) -> None:
        """Set the level (brightness) for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param level: The desired level in range [0, 255]. If 0 the unit is turned off.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied level isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        level_val = args[1] if len(args) > 1 else level
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use set_level(target=..., level=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if level_val is None:
            raise ValueError("level is required")
        if level_val < 0 or level_val > 255:
            raise ValueError()

        payload = level_val.to_bytes(1, byteorder="big", signed=False)
        await self._send(target_val, payload, OpCode.SetLevel)

    async def setLevel(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        level: int | None = None,
    ) -> None:
        """Deprecated alias for set_level."""
        warnings.warn(
            "setLevel is deprecated; use set_level instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_level(*args, target=target, level=level)

    async def set_vertical(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        vertical: int | None = None,
    ) -> None:
        """Set the vertical (balance between top and bottom LED) for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param vertical: The desired vertical balance in range [0, 255]. If 0 the unit is turned off.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied level isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        vertical_val = args[1] if len(args) > 1 else vertical
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use set_vertical(target=..., vertical=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if vertical_val is None:
            raise ValueError("vertical is required")
        if vertical_val < 0 or vertical_val > 255:
            raise ValueError()

        payload = vertical_val.to_bytes(1, byteorder="big", signed=False)
        await self._send(target_val, payload, OpCode.SetVertical)

    async def setVertical(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        vertical: int | None = None,
    ) -> None:
        """Deprecated alias for set_vertical."""
        warnings.warn(
            "setVertical is deprecated; use set_vertical instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_vertical(*args, target=target, vertical=vertical)

    async def set_slider(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        value: int | None = None,
    ) -> None:
        """Set the slider for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param value: The desired value in range [0, 255].
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied level isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        value_val = args[1] if len(args) > 1 else value
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use set_slider(target=..., value=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if value_val is None:
            raise ValueError("value is required")
        if value_val < 0 or value_val > 255:
            raise ValueError()

        payload = value_val.to_bytes(1, byteorder="big", signed=False)
        await self._send(target_val, payload, OpCode.SetSlider)

    async def setSlider(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        value: int | None = None,
    ) -> None:
        """Deprecated alias for set_slider."""
        warnings.warn(
            "setSlider is deprecated; use set_slider instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_slider(*args, target=target, value=value)

    async def set_white(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        level: int | None = None,
    ) -> None:
        """Set the white level for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param level: The desired level in range [0, 255].
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied level isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        level_val = args[1] if len(args) > 1 else level
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use set_white(target=..., level=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if level_val is None:
            raise ValueError("level is required")
        if level_val < 0 or level_val > 255:
            raise ValueError()

        payload = level_val.to_bytes(1, byteorder="big", signed=False)
        await self._send(target_val, payload, OpCode.SetWhite)

    async def setWhite(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        level: int | None = None,
    ) -> None:
        """Deprecated alias for set_white."""
        warnings.warn(
            "setWhite is deprecated; use set_white instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_white(*args, target=target, level=level)

    async def set_color(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        rgb_color: tuple[int, int, int] | None = None,
        rgbColor: tuple[int, int, int] | None = None,
    ) -> None:
        """Set the rgb color for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param rgb_color: The desired color as a tuple of three ints in range [0, 255].
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied rgb_color isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        color_val = args[1] if len(args) > 1 else (rgb_color if rgb_color is not None else rgbColor)
        if args or rgbColor is not None:
            warnings.warn(
                "Positional arguments or rgbColor are deprecated; use set_color(target=..., rgb_color=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if color_val is None:
            raise ValueError("rgb_color is required")

        payload = UnitState.payload_from_rgb(color_val)
        await self._send(target_val, payload, OpCode.SetColor)

    async def setColor(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        rgbColor: tuple[int, int, int] | None = None,
        rgb_color: tuple[int, int, int] | None = None,
    ) -> None:
        """Deprecated alias for set_color."""
        warnings.warn(
            "setColor is deprecated; use set_color instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_color(*args, target=target, rgb_color=rgb_color, rgbColor=rgbColor)

    async def set_temperature(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        temperature: int | None = None,
    ) -> None:
        """Set the temperature for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param temperature: The desired temperature in degrees Kelvin.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied temperature isn't in range
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        temp_val = args[1] if len(args) > 1 else temperature
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use set_temperature(target=..., temperature=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if temp_val is None:
            raise ValueError("temperature is required")

        payload = UnitState.payload_from_temperature(temp_val)
        await self._send(target_val, payload, OpCode.SetTemperature)

    async def setTemperature(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        temperature: int | None = None,
    ) -> None:
        """Deprecated alias for set_temperature."""
        warnings.warn(
            "setTemperature is deprecated; use set_temperature instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_temperature(*args, target=target, temperature=temperature)

    async def set_color_xy(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        xy_color: tuple[float, float] | None = None,
        xyColor: tuple[float, float] | None = None,
    ) -> None:
        """Set the xy color for one or multiple units.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :param xy_color: The desired color as a pair of floats in the range [0.0, 1.0].
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises ValueError: The supplied xy_color isn't in range or not supported by the supplied unit.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        color_val = args[1] if len(args) > 1 else (xy_color if xy_color is not None else xyColor)
        if args or xyColor is not None:
            warnings.warn(
                "Positional arguments or xyColor are deprecated; use set_color_xy(target=..., xy_color=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if color_val is None:
            raise ValueError("xy_color is required")
        if color_val[0] < 0.0 or color_val[0] > 1.0 or color_val[1] < 0.0 or color_val[1] > 1.0:
            raise ValueError("Color out of range.")

        length = 22
        if target_val is not None and isinstance(target_val, Unit):
            control = target_val.unitType.get_control(UnitControlType.XY)
            if control is None:
                raise ValueError("The control isn't supported by this unit.")
            length = control.length

        payload = UnitState.payload_from_xy(color_val, length)
        await self._send(target_val, payload, OpCode.SetColorXY)

    async def setColorXY(
        self,
        *args: Any,
        target: Unit | Group | None = None,
        xyColor: tuple[float, float] | None = None,
        xy_color: tuple[float, float] | None = None,
    ) -> None:
        """Deprecated alias for set_color_xy."""
        warnings.warn(
            "setColorXY is deprecated; use set_color_xy instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_color_xy(*args, target=target, xy_color=xy_color, xyColor=xyColor)

    async def turn_on(
        self,
        *args: Any,
        target: Unit | Group | None = None,
    ) -> None:
        """Turn one or multiple units on to their last level.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use turn_on(target=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        self._check_network()
        await self._send(target_val, b"\xff\x01\x00\x00\x01", OpCode.SetLevel)

    async def turnOn(
        self,
        *args: Any,
        target: Unit | Group | None = None,
    ) -> None:
        """Deprecated alias for turn_on."""
        warnings.warn(
            "turnOn is deprecated; use turn_on instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.turn_on(*args, target=target)

    async def turn_off(
        self,
        *args: Any,
        target: Unit | Group | None = None,
    ) -> None:
        """Turn one or multiple units off.

        If ``target`` is of type ``Unit`` only this unit is affected.
        If ``target`` is of type ``Group`` the whole group is affected.
        if ``target`` is of type ``None`` all units in the network are affected.

        :param target: One or multiple targeted units.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use turn_off(target=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        self._check_network()
        await self.set_level(target=target_val, level=0)

    async def turnOff(
        self,
        *args: Any,
        target: Unit | Group | None = None,
    ) -> None:
        """Deprecated alias for turn_off."""
        warnings.warn(
            "turnOff is deprecated; use turn_off instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.turn_off(*args, target=target)

    async def switch_to_scene(
        self,
        *args: Any,
        target: Scene | None = None,
        level: int = 0xFF,
    ) -> None:
        """Switch the network to a predefined scene.

        :param target: The scene to switch to.
        :param level: An optional relative brightness for all units in the scene.
        :return: Nothing is returned by this function. To get the new state register a change handler.
        :raises BluetoothError: An error occurred in the bluetooth stack.
        """
        target_val = args[0] if len(args) > 0 else target
        level_val = args[1] if len(args) > 1 else level
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use switch_to_scene(target=..., level=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if target_val is None:
            raise ValueError("target scene is required")
        await self.set_level(target=target_val, level=level_val)  # type: ignore[arg-type]

    async def switchToScene(
        self,
        *args: Any,
        target: Scene | None = None,
        level: int = 0xFF,
    ) -> None:
        """Deprecated alias for switch_to_scene."""
        warnings.warn(
            "switchToScene is deprecated; use switch_to_scene instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.switch_to_scene(*args, target=target, level=level)

    async def _send(
        self, target: Unit | Group | Scene | None, state: bytes, opcode: OpCode
    ) -> None:
        if self._casaClient is None:
            raise ConnectionStateError(
                ConnectionState.AUTHENTICATED,
                ConnectionState.NONE,
            )

        self._logger.debug(f"Sending operation {opcode.name} with payload {state.hex()}.")

        opPkt = self._opContext.prepare_operation(op=opcode, target=target, payload=state)

        try:
            await self._casaClient.send(opPkt)
        except ConnectionStateError as err:
            if err.got == ConnectionState.NONE:
                self._logger.info("Trying to reconnect broken connection once.")
                await self.reconnect(address=self._casaClient._address_or_device)
                await self._casaClient.send(opPkt)
            else:
                raise err

    def _data_callback(
        self, packetType: IncomingPacketType, data: dict[str, Any] | SwitchEvent
    ) -> None:
        self._logger.debug(f"Incoming data callback of type {packetType!s}")
        if packetType == IncomingPacketType.UnitState:
            unitData = cast(dict[str, Any], data)
            self._logger.debug(
                f"Handling changed state {unitData['state'].hex()} for unit {unitData['id']}"
            )

            found = False
            for u in self._casaNetwork.units:  # type: ignore[union-attr]
                if u.device_id == unitData["id"]:
                    found = True
                    u.set_state_from_bytes(value=unitData["state"])
                    u._on = unitData["on"]
                    u._online = unitData["online"]

                    # Notify listeners
                    for h in self._unitChangedCallbacks:
                        try:
                            h(u)
                        except Exception:
                            self._logger.error(
                                f"Exception occurred in unitChangedCallback {h}.",
                                exc_info=True,
                            )

            if not found:
                self._logger.error(f"Changed state notification for unkown unit {unitData['id']}")
        elif packetType == IncomingPacketType.SwitchEvent:
            switchData = cast(SwitchEvent, data)
            self._logger.debug(
                f"Handling switch event: unit_id={switchData.unit_id}, "
                f"button={switchData.button}, event={switchData.event}"
            )

            # Notify listeners
            for switch_handler in self._switchEventCallbacks:
                try:
                    switch_handler(switchData)
                except Exception:
                    self._logger.error(
                        f"Exception occurred in switchEventCallback {switch_handler}.",
                        exc_info=True,
                    )
        else:
            self._logger.warning(f"Handler for type {packetType} not implemented!")

    def _dataCallback(
        self, packetType: IncomingPacketType, data: dict[str, Any] | SwitchEvent
    ) -> None:
        warnings.warn(
            "_dataCallback is deprecated; use _data_callback instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._data_callback(packetType, data)

    def register_unit_changed_handler(
        self, *args: Any, handler: Callable[[Unit], None] | None = None
    ) -> None:
        """Register a new handler for unit state changed.

        This handler is called whenever a new state for a unit is received.
        The handler is supplied by the unit for which the state changed
        and the state property of the unit is set to the new state.

        :param handler: The method to call when a new unit state is received.
        """
        target_handler = args[0] if len(args) > 0 else handler
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use register_unit_changed_handler(handler=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if target_handler is None:
            raise ValueError("handler is required")
        self._unitChangedCallbacks.append(target_handler)
        self._logger.debug(f"Registered unit changed handler {target_handler}")

    def registerUnitChangedHandler(
        self, *args: Any, handler: Callable[[Unit], None] | None = None
    ) -> None:
        """Deprecated alias for register_unit_changed_handler."""
        warnings.warn(
            "registerUnitChangedHandler is deprecated; use register_unit_changed_handler instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.register_unit_changed_handler(*args, handler=handler)

    def unregister_unit_changed_handler(
        self, *args: Any, handler: Callable[[Unit], None] | None = None
    ) -> None:
        """Unregister an existing unit state change handler.

        :param handler: The handler to unregister.
        :raises ValueError: If the handler isn't registered.
        """
        target_handler = args[0] if len(args) > 0 else handler
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use unregister_unit_changed_handler(handler=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if target_handler is None:
            raise ValueError("handler is required")
        self._unitChangedCallbacks.remove(target_handler)
        self._logger.debug(f"Removed unit changed handler {target_handler}")

    def unregisterUnitChangedHandler(
        self, *args: Any, handler: Callable[[Unit], None] | None = None
    ) -> None:
        """Deprecated alias for unregister_unit_changed_handler."""
        warnings.warn(
            "unregisterUnitChangedHandler is deprecated; use unregister_unit_changed_handler instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.unregister_unit_changed_handler(*args, handler=handler)

    def register_switch_event_handler(
        self, *args: Any, handler: Callable[[SwitchEvent], None] | None = None
    ) -> None:
        """Register a new handler for switch events.

        This handler is called whenever a switch event is received.
        """
        target_handler = args[0] if len(args) > 0 else handler
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use register_switch_event_handler(handler=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if target_handler is None:
            raise ValueError("handler is required")
        self._switchEventCallbacks.append(target_handler)
        self._logger.debug(f"Registered switch event handler {target_handler}")

    def registerSwitchEventHandler(
        self, *args: Any, handler: Callable[[SwitchEvent], None] | None = None
    ) -> None:
        """Deprecated alias for register_switch_event_handler."""
        warnings.warn(
            "registerSwitchEventHandler is deprecated; use register_switch_event_handler instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.register_switch_event_handler(*args, handler=handler)

    def unregister_switch_event_handler(
        self, *args: Any, handler: Callable[[SwitchEvent], None] | None = None
    ) -> None:
        """Unregister an existing switch event handler.

        :param handler: The handler to unregister.
        :raises ValueError: If the handler isn't registered.
        """
        target_handler = args[0] if len(args) > 0 else handler
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use unregister_switch_event_handler(handler=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if target_handler is None:
            raise ValueError("handler is required")
        self._switchEventCallbacks.remove(target_handler)
        self._logger.debug(f"Removed switch event handler {target_handler}")

    def unregisterSwitchEventHandler(
        self, *args: Any, handler: Callable[[SwitchEvent], None] | None = None
    ) -> None:
        """Deprecated alias for unregister_switch_event_handler."""
        warnings.warn(
            "unregisterSwitchEventHandler is deprecated; use unregister_switch_event_handler instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.unregister_switch_event_handler(*args, handler=handler)

    def register_disconnect_callback(
        self, *args: Any, callback: Callable[[], None] | None = None
    ) -> None:
        """Register a disconnect callback.

        The callback is called whenever the Bluetooth stack reports that
        the Bluetooth connection to the network was disconnected.

        :params callback: The callback to register.
        """
        target_cb = args[0] if len(args) > 0 else callback
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use register_disconnect_callback(callback=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if target_cb is None:
            raise ValueError("callback is required")
        self._disconnectCallbacks.append(target_cb)
        self._logger.debug(f"Registered disconnect callback {target_cb}")

    def registerDisconnectCallback(
        self, *args: Any, callback: Callable[[], None] | None = None
    ) -> None:
        """Deprecated alias for register_disconnect_callback."""
        warnings.warn(
            "registerDisconnectCallback is deprecated; use register_disconnect_callback instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.register_disconnect_callback(*args, callback=callback)

    def unregister_disconnect_callback(
        self, *args: Any, callback: Callable[[], None] | None = None
    ) -> None:
        """Unregister an existing disconnect callback.

        :param callback: The callback to unregister.
        :raises ValueError: If the callback isn't registered.
        """
        target_cb = args[0] if len(args) > 0 else callback
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use unregister_disconnect_callback(callback=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if target_cb is None:
            raise ValueError("callback is required")
        self._disconnectCallbacks.remove(target_cb)
        self._logger.debug(f"Removed disconnect callback {target_cb}")

    def unregisterDisconnectCallback(
        self, *args: Any, callback: Callable[[], None] | None = None
    ) -> None:
        """Deprecated alias for unregister_disconnect_callback."""
        warnings.warn(
            "unregisterDisconnectCallback is deprecated; use unregister_disconnect_callback instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.unregister_disconnect_callback(*args, callback=callback)

    async def invalidate_cache(self, *args: Any, uuid: str | None = None) -> None:
        """Invalidates the cache for a network.

        :param uuid: The address of the network.
        """
        target_uuid = args[0] if len(args) > 0 else uuid
        if args:
            warnings.warn(
                "Positional arguments are deprecated; use invalidate_cache(uuid=...) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if target_uuid is None:
            raise ValueError("uuid is required")

        # We can't use our own cache here since the invalidation happens
        # before the first connection attempt.
        tempCache = Cache(cache_path=self._cache._cache_path)
        await tempCache.set_uuid(uuid=target_uuid)
        await tempCache.invalidate_cache()

    async def invalidateCache(self, *args: Any, uuid: str | None = None) -> None:
        """Deprecated alias for invalidate_cache."""
        warnings.warn(
            "invalidateCache is deprecated; use invalidate_cache instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.invalidate_cache(*args, uuid=uuid)

    def _disconnect_callback(self) -> None:
        # Mark all units as offline on disconnect.
        for u in self.units:
            u._online = False
            for h in self._unitChangedCallbacks:
                try:
                    h(u)
                except Exception:
                    self._logger.error(
                        f"Exception occurred in unitChangedHandler {h}.",
                        exc_info=True,
                    )

        for d in self._disconnectCallbacks:
            try:
                d()
            except Exception:
                self._logger.error(
                    f"Exception occurred in disconnectCallback {d}.",
                    exc_info=True,
                )

    def _disconnectCallback(self) -> None:
        warnings.warn(
            "_disconnectCallback is deprecated; use _disconnect_callback instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._disconnect_callback()

    async def disconnect(self) -> None:
        """Disconnect from the network."""
        if self._casaClient:
            try:
                await asyncio.shield(self._casaClient.disconnect())
            except Exception:
                self._logger.error("Failed to disconnect from client.", exc_info=True)
        if self._casaNetwork:
            try:
                await asyncio.shield(self._casaNetwork.disconnect())
            except Exception:
                self._logger.error("Failed to disconnect from network.", exc_info=True)
            self._casaNetwork = None
        if self._ownHttpClient and self._httpClient is not None:
            try:
                await asyncio.shield(self._httpClient.aclose())
            except Exception:
                self._logger.error("Failed to close http client.", exc_info=True)
