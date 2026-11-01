from enum import IntEnum, unique
from typing import Final

DEVICE_NAME: Final = "Casambi BT Python"

CASA_UUID: Final = "0000fe4d-0000-1000-8000-00805f9b34fb"
CASA_AUTH_CHAR_UUID: Final = "c9ffde48-ca5a-0001-ab83-8f519b482f77"

KEY_CACHE_FILE: Final = "casambi_lookup.json"
LEGACY_KEY_CACHE_FILE: Final = "keys.pck"
SESSION_CACHE_FILE: Final = "casambi_session.json"
LEGACY_SESSION_CACHE_FILE: Final = "session.pck"
TYPES_CACHE_FILE: Final = "casambi_types.json"
LEGACY_TYPES_CACHE_FILE: Final = "types.pck"
NETWORK_ID_CACHE_FILE: Final = "casambi_network_id.txt"
LEGACY_NETWORK_ID_CACHE_FILE: Final = "networkid"


@unique
class ConnectionState(IntEnum):
    NONE = 0
    CONNECTED = 1
    KEY_EXCHANGED = 2
    AUTHENTICATED = 3
    ERROR = 99


@unique
class IncomingPacketType(IntEnum):
    UnitState = 6
    SwitchEvent = 7
    NetworkConfig = 9


FIRST_UNSUPPORTED_PROTOCOL_VERSION: Final[int] = 10
MIN_SUPPORTED_CLASSIC_VERSION: Final[int] = 5


def isClassicNetwork(version: int) -> bool:
    return version < FIRST_UNSUPPORTED_PROTOCOL_VERSION


CLASSIC_AUTH_LEVEL_MANAGER: Final = 3
CLASSIC_AUTH_LEVEL_VISITOR: Final = 2
