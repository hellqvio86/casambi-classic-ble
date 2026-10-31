import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.modes import ECB

from casambi_classic_ble._encryption import (
    ClassicEncryptor,
    Encryptor,
    _encHelper,
    _xor,
)


def test_xor():
    a = b"\x01\x02\x03"
    b = b"\x04\x05\x06"
    assert _xor(a, b) == b"\x05\x07\x05"


def test_enc_helper():
    key = b"\x00" * 16
    cipher = Cipher(AES(key), mode=ECB())
    block = b"\x11" * 16
    res = _encHelper(cipher, block)
    assert len(res) == 16


def test_encryptor_roundtrip():
    key = b"\x01" * 16
    nonce = b"\x02" * 16
    encryptor = Encryptor(key=key)

    plaintext = b"head" + b"Hello Casambi World Payload"
    encrypted = encryptor.encryptThenMac(packet=plaintext, nonce=nonce, headerLen=4)

    assert len(encrypted) == len(plaintext) + 16  # 16 bytes CMAC

    decrypted = encryptor.decryptAndVerify(packet=encrypted, nonce=nonce, headerLen=4)
    assert decrypted == b"Hello Casambi World Payload"


def test_encryptor_invalid_nonce():
    key = b"\x01" * 16
    encryptor = Encryptor(key=key)
    with pytest.raises(ValueError, match="Nonce must be 16 bytes"):
        encryptor.encryptThenMac(packet=b"test", nonce=b"short", headerLen=2)


def test_encryptor_invalid_mac():
    key = b"\x01" * 16
    nonce = b"\x02" * 16
    encryptor = Encryptor(key=key)

    plaintext = b"head" + b"Payload"
    encrypted = encryptor.encryptThenMac(packet=plaintext, nonce=nonce, headerLen=4)

    # Corrupt MAC
    corrupted = bytearray(encrypted)
    corrupted[-1] ^= 0xFF
    with pytest.raises(InvalidSignature):
        encryptor.decryptAndVerify(packet=bytes(corrupted), nonce=nonce, headerLen=4)


def test_classic_encryptor_roundtrip():
    key = b"\x03" * 16
    connhash = b"\x04" * 8
    classic = ClassicEncryptor(key=key, sig_len=4)

    packet = b"\x01\x02\x03\x04\x05"
    digested = classic.digest(packet=packet, connhash=connhash)
    assert len(digested) == len(packet) + 4
    assert digested[4:] == packet

    verified = classic.verify(packet=digested, connhash=connhash)
    assert verified == packet


def test_classic_encryptor_invalid_connhash():
    key = b"\x03" * 16
    classic = ClassicEncryptor(key=key, sig_len=4)
    with pytest.raises(ValueError, match="Connhash must be 8 bytes"):
        classic.digest(packet=b"abc", connhash=b"123")
    with pytest.raises(ValueError, match="Connhash must be 8 bytes"):
        classic.verify(packet=b"abc", connhash=b"123")


def test_classic_encryptor_invalid_signature():
    key = b"\x03" * 16
    connhash = b"\x04" * 8
    classic = ClassicEncryptor(key=key, sig_len=4)

    packet = b"\x01\x02\x03\x04\x05"
    digested = bytearray(classic.digest(packet=packet, connhash=connhash))
    digested[0] ^= 0xFF  # Corrupt signature

    with pytest.raises(InvalidSignature, match="Signature verification failed"):
        classic.verify(packet=bytes(digested), connhash=connhash)
