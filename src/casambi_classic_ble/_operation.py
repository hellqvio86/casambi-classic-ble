import logging
from abc import ABC, abstractmethod
from enum import IntEnum, unique
from typing import Final

from ._unit import Group, Scene, Unit


@unique
class OpCode(IntEnum):
    Response = 0
    SetLevel = 1
    SetTemperature = 3
    SetVertical = 4
    SetWhite = 5
    SetColor = 7
    SetSlider = 12
    SetState = 48
    SetColorXY = 54


_classicOpcodeMap: Final[dict[OpCode, dict[type, int]]] = {
    OpCode.SetLevel: {type(None): 4, Unit: 7, Group: 26, Scene: 1},
    OpCode.SetTemperature: {type(None): 5, Unit: 8, Group: 27},
    OpCode.SetColor: {type(None): 6, Unit: 9, Group: 28},
    OpCode.SetVertical: {type(None): 22, Unit: 24, Group: 29},
    OpCode.SetWhite: {type(None): 23, Unit: 25, Group: 30},
}


class OperationsContext(ABC):
    def __init__(self) -> None:
        self._origin: int = 1
        self.lifetime: int = 5
        self._logger = logging.getLogger(__name__)

    @abstractmethod
    def prepareOperation(
        self, op: OpCode, target: Unit | Group | Scene | None, payload: bytes
    ) -> bytes:
        pass


class OperationsContextClassic(OperationsContext):
    def __init__(self) -> None:
        super().__init__()
        self.lifetime = 200

    def prepareOperation(
        self, op: OpCode, target: Unit | Group | Scene | None, payload: bytes
    ) -> bytes:
        if len(payload) > 16:
            raise ValueError("Payload too long")

        if op not in _classicOpcodeMap:
            raise ValueError(f"OpCode {op} is not supported on Classic networks.")

        if self._origin > 255:
            self._origin = 1

        # We always send origin, so set 0x40
        flags = _classicOpcodeMap[op][type(target)] | 0x40
        packet = bytearray(3)

        targetId = None
        if isinstance(target, Unit):
            targetId = target.deviceId
        elif isinstance(target, Group):
            targetId = target.groudId
        elif isinstance(target, Scene):
            targetId = target.sceneId

        if targetId is not None:
            packet += targetId.to_bytes(1)
            flags |= 0x80

        packet[1] = flags
        packet[2] = self._origin
        packet.append(self.lifetime)

        packet += payload

        packet[0] = (len(packet) + 239) & 0xFF

        self._origin += 1
        return bytes(packet)
