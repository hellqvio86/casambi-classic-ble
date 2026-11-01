import hmac
import logging
import os
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.modes import CBC, ECB
from cryptography.hazmat.primitives.cmac import CMAC

_TRACE: Final[bool] = os.environ.get("CASAMBI_TRACE", "").lower() in ("1", "true", "yes")


def _xor(data: bytes, key: bytes) -> bytes:
    if len(data) != len(key):
        raise ValueError("Data and key must be of equal length.")
    return bytes(a ^ b for a, b in zip(data, key))


def _encHelper(cipher: Cipher, input: bytes) -> bytes:
    if len(input) % 16 != 0:
        raise ValueError("Input length must be a multiple of 16 bytes.")

    # False positive: AES-ECB block cipher is mandated by Casambi Classic BLE radio protocol
    # codeql[py/weak-cryptographic-algorithm]
    context = cipher.encryptor()
    return context.update(input) + context.finalize()


class Encryptor:
    def __init__(self, key: bytes) -> None:
        self._aes = AES(key)
        # False positive: AES-ECB block cipher is mandated by Casambi Classic BLE radio protocol
        # codeql[py/weak-cryptographic-algorithm]
        self._blockCipher = Cipher(AES(key), mode=ECB())
        self._cmacCipher = Cipher(AES(key), mode=CBC(b"\0" * 16))
        self._logger = logging.getLogger(__name__)

    def encryptThenMac(self, packet: bytes, nonce: bytes, headerLen: int = 4) -> bytes:
        if _TRACE:
            self._logger.debug(
                f"Encrypting packet: {packet.hex()} of len {len(packet)} with nonce {nonce.hex()}"
            )
        else:
            self._logger.debug("Encrypting packet of len %d", len(packet))

        packet = bytes(packet)
        packet = packet[:headerLen] + self._encryptInternal(packet[headerLen:], nonce)

        if _TRACE:
            self._logger.debug(f"Encrypted packet: {packet.hex()}")
        else:
            self._logger.debug("Encrypted packet of len %d", len(packet))

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(packet)
        packet += cmacCipher.finalize()
        return packet

    def decryptAndVerify(self, packet: bytes, nonce: bytes, headerLen: int = 4) -> bytes:
        if _TRACE:
            self._logger.debug(
                f"Decrypting packet: {packet.hex()} of len {len(packet)} with nonce {nonce.hex()}"
            )
        else:
            self._logger.debug("Decrypting packet of len %d", len(packet))

        packet = bytes(packet)
        ciphertext, packetMac = packet[0:-16], packet[-16:]

        # Always decrypt for timing reasons
        plaintext = self._encryptInternal(ciphertext[headerLen:], nonce)

        if _TRACE:
            self._logger.debug(f"Decrypted packet: {plaintext.hex()}")
        else:
            self._logger.debug("Decrypted packet of len %d", len(plaintext))

        cmacCipher = CMAC(self._aes)
        cmacCipher.update(ciphertext)
        cmacCipher.verify(packetMac)
        return plaintext

    def _encryptInternal(self, packet: bytes, nonce: bytes) -> bytes:
        if len(nonce) != 16:
            raise ValueError("Nonce must be 16 bytes long.")

        nonce_buf = bytearray(nonce)

        counter = 0
        result = b""
        for i in range(0, len(packet), 16):
            nonce_buf[12:] = counter.to_bytes(4, "little")
            block = _encHelper(self._blockCipher, bytes(nonce_buf))
            rem = min(i + 16, len(packet))
            result += _xor(block[: rem - i], packet[i:rem])
            counter += 1

        return result


class ClassicEncryptor:
    def __init__(self, key: bytes, sig_len: int) -> None:
        self._aes = AES(key)
        self._cipher = Cipher(AES(key), mode=ECB())
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
