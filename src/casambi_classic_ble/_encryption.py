import hmac
import logging
import os
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.cmac import CMAC

_TRACE: Final[bool] = os.environ.get("CASAMBI_TRACE", "").lower() in ("1", "true", "yes")


class ClassicEncryptor:
    def __init__(self, key: bytes, sig_len: int) -> None:
        self._aes = AES(key)
        self._sig_len = sig_len
        self._logger = logging.getLogger(__name__)

    def digest(self, packet: bytes, connhash: bytes) -> bytes:
        # We leave handling the auth level to the caller and expect the packet to start with the signature.

        if len(connhash) != 8:
            raise ValueError("Connhash must be 8 bytes long.")

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(connhash + packet)
        cmac = cmacCipher.finalize()

        return cmac[: self._sig_len] + packet

    def verify(self, packet: bytes, connhash: bytes) -> bytes:
        # We leave handling the auth level to the caller and expect the packet to start with the signature.

        if len(connhash) != 8:
            raise ValueError("Connhash must be 8 bytes long.")

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(connhash + packet[self._sig_len :])
        computedMac = cmacCipher.finalize()[: self._sig_len]
        pckMac = packet[: self._sig_len]

        if not hmac.compare_digest(computedMac, pckMac):
            self._logger.warning("Signature verification failed.")
            raise InvalidSignature("Signature verification failed.")

        return packet[self._sig_len :]
