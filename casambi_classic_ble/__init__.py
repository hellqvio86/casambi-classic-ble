"""
Casambi Classic BLE Library
Bluetooth Low Energy library for Casambi classic firmware lighting control
"""

from .cloud import CasambiCloud
from .constants import CasambiCommands, CasambiUUIDs
from .device import CasambiDevice
from .exceptions import CasambiConnectionError, CasambiError
from .scanner import CasambiScanner

__version__ = "0.1.0"
__author__ = "Your Name"
__all__ = [
    "CasambiDevice",
    "CasambiScanner",
    "CasambiCloud",
    "CasambiCommands",
    "CasambiUUIDs",
    "CasambiError",
    "CasambiConnectionError",
]
