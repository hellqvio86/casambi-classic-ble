"""Casambi Classic BLE Library.

Bluetooth Low Energy library for Casambi classic firmware lighting control.
"""

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
from .exceptions import CasambiConnectionError, CasambiError
from .scanner import CasambiScanner

__version__ = "0.3.2"
__author__ = "Olof Hellqvist"

__all__ = [
    "CasambiDevice",
    "CasambiScanner",
    "CasambiCloud",
    "CasambiCommands",
    "CasambiUUIDs",
    "CasambiError",
    "CasambiConnectionError",
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
