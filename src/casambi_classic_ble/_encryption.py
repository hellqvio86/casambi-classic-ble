import hmac
import logging
import os
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.cmac import CMAC

_TRACE: Final[bool] = os.environ.get("CASAMBI_TRACE", "").lower() in ("1", "true", "yes")


class ClassicEncryptor:
    def __init__(self, key: bytes | bytearray, sig_len: int) -> None:
        if not isinstance(key, (bytes, bytearray)):
            raise TypeError(f"AES key must be bytes or bytearray, got {type(key).__name__}")
        if len(key) != 16:
            raise ValueError(f"AES key must be exactly 16 bytes, got {len(key)}")
        if sig_len not in (4, 16):
            raise ValueError(f"Signature length must be 4 or 16 bytes, got {sig_len}")

        self._aes = AES(bytes(key))
        self._sig_len = sig_len
        self._logger = logging.getLogger(__name__)

    def digest(self, packet: bytes, connhash: bytes) -> bytes:
        # We leave handling the auth level to the caller and expect the packet to start with the signature.
        if len(connhash) != 8:
            self._logger.error(
                "Malformed packet: connhash must be exactly 8 bytes (got %d, packet=%s).",
                len(connhash),
                packet.hex(),
            )
            raise ValueError(
                f"Connhash must be 8 bytes long (got {len(connhash)}, packet={packet.hex()})."
            )

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(connhash + packet)
        cmac = cmacCipher.finalize()

        return cmac[: self._sig_len] + packet

    def verify(self, packet: bytes, connhash: bytes) -> bytes:
        # We leave handling the auth level to the caller and expect the packet to start with the signature.
        if len(connhash) != 8:
            self._logger.error(
                "Malformed packet: connhash must be exactly 8 bytes (got %d, packet=%s).",
                len(connhash),
                packet.hex(),
            )
            raise ValueError(
                f"Connhash must be 8 bytes long (got {len(connhash)}, packet={packet.hex()})."
            )

        if len(packet) < self._sig_len:
            self._logger.error(
                "Malformed packet received (length %d is shorter than signature length %d, packet=%s).",
                len(packet),
                self._sig_len,
                packet.hex(),
            )
            raise ValueError(
                f"Packet length ({len(packet)}) is shorter than signature length ({self._sig_len}): {packet.hex()}"
            )

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(connhash + packet[self._sig_len :])
        computedMac = cmacCipher.finalize()[: self._sig_len]
        pckMac = packet[: self._sig_len]

        if not hmac.compare_digest(computedMac, pckMac):
            self._logger.error(
                "Malformed packet received: signature verification failed for packet %s (sig=%s, expected=%s).",
                packet.hex(),
                pckMac.hex(),
                computedMac.hex(),
            )
            raise InvalidSignature(
                f"Signature verification failed for packet {packet.hex()} (sig={pckMac.hex()}, expected={computedMac.hex()})."
            )

        return packet[self._sig_len :]
