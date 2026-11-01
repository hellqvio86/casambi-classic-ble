"""Casambi Classic BLE Library.

Bluetooth Low Energy library for Casambi classic firmware lighting control.
"""

from importlib.metadata import PackageNotFoundError, version

from . import utils
from ._casambi import Casambi
from ._discover import discover
from ._unit import (
    ColorSource,
    Group,
    Scene,
    Unit,
    UnitControl,
    UnitControlType,
    UnitState,
    UnitType,
)
from .cloud import CasambiCloud
from .constants import CasambiCommands, CasambiUUIDs
from .device import CasambiDevice
from .exceptions import (
    AuthenticationError,
    BluetoothDeviceNotFoundError,
    BluetoothError,
    CasambiBtError,
    CasambiCacheError,
    CasambiClassicBleError,
    CasambiCloudApiException,
    CasambiCommandError,
    CasambiConnectionError,
    CasambiDeviceError,
    CasambiDeviceNotFoundError,
    CasambiError,
    CasambiException,
    CasambiSecurityError,
    ConnectionStateError,
    NetworkNotFoundError,
    NetworkOnlineUpdateNeededError,
    NetworkUpdateError,
    ProtocolError,
    UnsupportedProtocolVersion,
)
from .scanner import CasambiScanner

try:
    __version__: str = version("casambi-classic-ble")
except PackageNotFoundError:
    __version__ = "0+unknown"

__author__ = "Lukas Kempf, Olof Hellqvist"

__all__ = [
    "AuthenticationError",
    "BluetoothDeviceNotFoundError",
    "BluetoothError",
    "Casambi",
    "CasambiBtError",
    "CasambiCacheError",
    "CasambiClassicBleError",
    "CasambiCloud",
    "CasambiCloudApiException",
    "CasambiCommandError",
    "CasambiCommands",
    "CasambiConnectionError",
    "CasambiDevice",
    "CasambiDeviceError",
    "CasambiDeviceNotFoundError",
    "CasambiError",
    "CasambiException",
    "CasambiScanner",
    "CasambiSecurityError",
    "CasambiUUIDs",
    "ColorSource",
    "ConnectionStateError",
    "Group",
    "NetworkNotFoundError",
    "NetworkOnlineUpdateNeededError",
    "NetworkUpdateError",
    "ProtocolError",
    "Scene",
    "Unit",
    "UnitControl",
    "UnitControlType",
    "UnitState",
    "UnitType",
    "UnsupportedProtocolVersion",
    "discover",
    "utils",
]
