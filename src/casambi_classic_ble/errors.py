"""Deprecated error module; all exceptions have been moved to casambi_classic_ble.exceptions."""

import warnings

from .exceptions import (
    AuthenticationError,
    BluetoothDeviceNotFoundError,
    BluetoothError,
    CasambiBtError,
    CasambiClassicBleError,
    ConnectionStateError,
    NetworkNotFoundError,
    NetworkOnlineUpdateNeededError,
    NetworkUpdateError,
    ProtocolError,
    UnsupportedProtocolVersion,
)

warnings.warn(
    "casambi_classic_ble.errors is deprecated; import exceptions from casambi_classic_ble.exceptions or casambi_classic_ble directly.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "AuthenticationError",
    "BluetoothDeviceNotFoundError",
    "BluetoothError",
    "CasambiBtError",
    "CasambiClassicBleError",
    "ConnectionStateError",
    "NetworkNotFoundError",
    "NetworkOnlineUpdateNeededError",
    "NetworkUpdateError",
    "ProtocolError",
    "UnsupportedProtocolVersion",
]
