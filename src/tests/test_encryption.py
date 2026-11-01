import pytest
from cryptography.exceptions import InvalidSignature

from casambi_classic_ble._encryption import ClassicEncryptor


def test_classic_encryptor_roundtrip():
    key = b"\x01" * 16
    connhash = b"\x02" * 8
    classic = ClassicEncryptor(key=key, sig_len=4)

    payload = b"PacketPayload"
    digested = classic.digest(packet=payload, connhash=connhash)

    assert len(digested) == len(payload) + 4
    assert digested[4:] == payload

    verified = classic.verify(packet=digested, connhash=connhash)
    assert verified == payload


def test_classic_encryptor_invalid_connhash():
    key = b"\x01" * 16
    classic = ClassicEncryptor(key=key, sig_len=4)

    with pytest.raises(ValueError, match="Connhash must be 8 bytes"):
        classic.digest(packet=b"test", connhash=b"short")

    with pytest.raises(ValueError, match="Connhash must be 8 bytes"):
        classic.verify(packet=b"test", connhash=b"short")


def test_classic_encryptor_invalid_signature():
    key = b"\x01" * 16
    connhash = b"\x02" * 8
    classic = ClassicEncryptor(key=key, sig_len=4)

    payload = b"PacketPayload"
    digested = classic.digest(packet=payload, connhash=connhash)

    corrupted = bytearray(digested)
    corrupted[0] ^= 0xFF

    with pytest.raises(InvalidSignature):
        classic.verify(packet=bytes(corrupted), connhash=connhash)
