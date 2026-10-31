"""Casambi BLE constants and UUIDs"""

from enum import IntEnum


class CasambiCommands(IntEnum):
    """Casambi command opcodes for classic firmware"""

    TURN_LIGHT_ON = 0x01
    TURN_LIGHT_OFF = 0x02
    SET_LEVEL = 0x03
    SET_COLOR_TEMP = 0x04
    SET_RGB = 0x05
    GET_DEVICE_INFO = 0x10
    GET_NETWORK_INFO = 0x11
    GET_STATE = 0x14
    GET_UNIT_STATE = 0x0F
    AUTHENTICATE = 0x07


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
