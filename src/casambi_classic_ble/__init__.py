"""Casambi Classic BLE Library.

Bluetooth Low Energy library for Casambi classic firmware lighting control.
"""

from importlib.metadata import PackageNotFoundError, version

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
    CasambiCloudApiException,
    CasambiCommandError,
    CasambiConnectionError,
    CasambiDeviceError,
    CasambiDeviceNotFoundError,
    CasambiError,
    CasambiException,
)
from .scanner import CasambiScanner

try:
    __version__: str = version("casambi-classic-ble")
except PackageNotFoundError:
    __version__ = "0+unknown"

__author__ = "Lukas Kempf, Olof Hellqvist"

__all__ = [
    "CasambiDevice",
    "CasambiScanner",
    "CasambiCloud",
    "CasambiCommands",
    "CasambiUUIDs",
    "CasambiError",
    "CasambiException",
    "CasambiDeviceError",
    "CasambiConnectionError",
    "CasambiCommandError",
    "CasambiDeviceNotFoundError",
    "CasambiCloudApiException",
    "Casambi",
    "Group",
    "Scene",
    "Unit",
    "UnitControl",
    "UnitControlType",
    "ColorSource",
    "UnitState",
    "UnitType",
    "discover",
]
