"""
Casambi Classic BLE Library
Bluetooth Low Energy library for Casambi classic firmware lighting control
"""

from .device import CasambiDevice
from .scanner import CasambiScanner
from .cloud import CasambiCloud
from .constants import CasambiCommands, CasambiUUIDs
from .exceptions import CasambiError, CasambiConnectionError

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
