"""Casambi BLE constants and UUIDs"""

from enum import IntEnum

from ._constants import (
    KEY_CACHE_FILE,
    LEGACY_KEY_CACHE_FILE,
    LEGACY_NETWORK_ID_CACHE_FILE,
    LEGACY_SESSION_CACHE_FILE,
    LEGACY_TYPES_CACHE_FILE,
    NETWORK_ID_CACHE_FILE,
    SESSION_CACHE_FILE,
    TYPES_CACHE_FILE,
)


class CasambiCommands(IntEnum):
    """Casambi command opcodes for classic firmware.

    Notes on observed vs exposed opcodes:
        - `TURN_LIGHT_ON` (0x01) & `TURN_LIGHT_OFF` (0x02): Observed 1-byte unit ID opcodes
          in older firmware. High-level methods `turn_on()` and `turn_off()` deliberately
          use `SET_LEVEL` (0x03) with 2-byte unit IDs (`<HB`) for compatibility with
          modern Classic firmware (e.g. 26.x).
        - `GET_DEVICE_INFO` (0x10) & `GET_NETWORK_INFO` (0x11): Observed GATT control
          query opcodes. Device information is normally retrieved via standard BLE
          Device Information Service (DIS 0x180A) characteristics.
        - `TURN_LIGHT_ON_LONG` (0x81) & `TURN_LIGHT_OFF_LONG` (0x82): Direct control by
          6-byte hardware device address.
    """

    TURN_LIGHT_ON = 0x01
    TURN_LIGHT_OFF = 0x02
    SET_LEVEL = 0x03
    SET_COLOR_TEMP = 0x04
    SET_RGB = 0x05
    AUTHENTICATE = 0x07
    GET_UNIT_STATE = 0x0F
    GET_DEVICE_INFO = 0x10
    GET_NETWORK_INFO = 0x11
    GET_STATE = 0x14
    TURN_LIGHT_ON_LONG = 0x81
    TURN_LIGHT_OFF_LONG = 0x82


class CasambiUUIDs:
    """Casambi BLE service and characteristic UUIDs"""

    # Service variant 1 (FE3D)
    SERVICE_V1 = "0000fe3d-0000-1000-8000-00805f9b34fb"
    CONTROL_V1 = "0000fe3e-0000-1000-8000-00805f9b34fb"
    STATUS_V1 = "0000fe3f-0000-1000-8000-00805f9b34fb"

    # Service variant 2 (FE4D)
    SERVICE_V2 = "0000fe4d-0000-1000-8000-00805f9b34fb"
    CONTROL_V2 = "c9ffde48-ca5a-0001-ab83-8f519b482f77"
    STATUS_V2 = "c9ffde48-ca5a-0002-ab83-8f519b482f77"

    # Device Information Service
    DEVICE_INFO_SERVICE = "0000180a-0000-1000-8000-00805f9b34fb"
    MANUFACTURER_NAME = "00002a29-0000-1000-8000-00805f9b34fb"
    MODEL_NUMBER = "00002a24-0000-1000-8000-00805f9b34fb"
    FIRMWARE_REVISION = "00002a26-0000-1000-8000-00805f9b34fb"


__all__ = [
    "CasambiCommands",
    "CasambiUUIDs",
    "KEY_CACHE_FILE",
    "LEGACY_KEY_CACHE_FILE",
    "SESSION_CACHE_FILE",
    "LEGACY_SESSION_CACHE_FILE",
    "TYPES_CACHE_FILE",
    "LEGACY_TYPES_CACHE_FILE",
    "NETWORK_ID_CACHE_FILE",
    "LEGACY_NETWORK_ID_CACHE_FILE",
]
