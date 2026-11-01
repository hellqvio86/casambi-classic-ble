"""Comprehensive cryptographic compatibility and invariant tests for ClassicEncryptor."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.cmac import CMAC

from casambi_classic_ble._encryption import ClassicEncryptor


@pytest.fixture
def crypto_golden_vectors() -> dict[str, Any]:
    """Load crypto session golden vectors from fixture file."""
    fixture_path = Path(__file__).parent / "fixtures" / "golden_vectors.json"
    with open(fixture_path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data["crypto_session_vectors"]


class TestClassicEncryptorInvariants:
    """Test constructor invariants and boundary validation for ClassicEncryptor."""

    def test_key_length_validation(self) -> None:
        """Key must be strictly 16 bytes (AES-128)."""
        # Valid 16-byte key
        ClassicEncryptor(key=b"\x00" * 16, sig_len=4)
        ClassicEncryptor(key=bytearray(b"\x00" * 16), sig_len=16)

        # Invalid key lengths
        with pytest.raises(ValueError, match="AES key must be exactly 16 bytes"):
            ClassicEncryptor(key=b"\x00" * 15, sig_len=4)

        with pytest.raises(ValueError, match="AES key must be exactly 16 bytes"):
            ClassicEncryptor(key=b"\x00" * 32, sig_len=4)

        with pytest.raises(ValueError, match="AES key must be exactly 16 bytes"):
            ClassicEncryptor(key=b"", sig_len=4)

    def test_key_type_validation(self) -> None:
        """Key must be bytes or bytearray."""
        with pytest.raises(TypeError, match="AES key must be bytes or bytearray"):
            ClassicEncryptor(key="0102030405060708090a0b0c0d0e0f10", sig_len=4)  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="AES key must be bytes or bytearray"):
            ClassicEncryptor(key=12345, sig_len=4)  # type: ignore[arg-type]

    def test_signature_length_validation(self) -> None:
        """Signature length must be either 4 (visitor) or 16 (manager)."""
        ClassicEncryptor(key=b"\x00" * 16, sig_len=4)
        ClassicEncryptor(key=b"\x00" * 16, sig_len=16)

        for invalid_len in (0, 1, 2, 8, 12, 20, 32):
            with pytest.raises(ValueError, match="Signature length must be 4 or 16 bytes"):
                ClassicEncryptor(key=b"\x00" * 16, sig_len=invalid_len)


class TestClassicEncryptorMalformedLogging:
    """Verify that every malformed packet or invalid condition logs at ERROR level."""

    def test_digest_invalid_connhash_logs_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """connhash length != 8 must log ERROR and raise ValueError."""
        encryptor = ClassicEncryptor(key=b"\x01" * 16, sig_len=4)

        with (
            caplog.at_level(logging.ERROR),
            pytest.raises(ValueError, match="Connhash must be 8 bytes"),
        ):
            encryptor.digest(packet=b"test", connhash=b"short")

        assert any("Malformed packet" in rec.getMessage() for rec in caplog.records)
        assert any(rec.levelno == logging.ERROR for rec in caplog.records)

    def test_verify_invalid_connhash_logs_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """connhash length != 8 in verify must log ERROR and raise ValueError."""
        encryptor = ClassicEncryptor(key=b"\x01" * 16, sig_len=4)

        with (
            caplog.at_level(logging.ERROR),
            pytest.raises(ValueError, match="Connhash must be 8 bytes"),
        ):
            encryptor.verify(packet=b"\x00" * 10, connhash=b"too_long_connhash")

        assert any("Malformed packet" in rec.getMessage() for rec in caplog.records)
        assert any(rec.levelno == logging.ERROR for rec in caplog.records)

    def test_verify_packet_shorter_than_signature_logs_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Packet shorter than sig_len is malformed and must log ERROR and raise ValueError."""
        encryptor = ClassicEncryptor(key=b"\x01" * 16, sig_len=4)
        connhash = b"\x02" * 8

        # Packet with only 3 bytes (< 4 byte signature)
        with (
            caplog.at_level(logging.ERROR),
            pytest.raises(ValueError, match="shorter than signature length"),
        ):
            encryptor.verify(packet=b"\x01\x02\x03", connhash=connhash)

        assert any("Malformed packet" in rec.getMessage() for rec in caplog.records)
        assert any(rec.levelno == logging.ERROR for rec in caplog.records)

        # Empty packet
        caplog.clear()
        with (
            caplog.at_level(logging.ERROR),
            pytest.raises(ValueError, match="shorter than signature length"),
        ):
            encryptor.verify(packet=b"", connhash=connhash)

        assert any("Malformed packet" in rec.getMessage() for rec in caplog.records)

    def test_verify_signature_failure_logs_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """Signature mismatch must log ERROR and raise InvalidSignature."""
        encryptor = ClassicEncryptor(key=b"\x01" * 16, sig_len=4)
        connhash = b"\x02" * 8
        payload = b"payload_bytes"

        # Valid digest
        digested = encryptor.digest(packet=payload, connhash=connhash)

        # Tampered signature
        tampered = bytearray(digested)
        tampered[0] ^= 0x01

        with caplog.at_level(logging.ERROR), pytest.raises(InvalidSignature):
            encryptor.verify(packet=bytes(tampered), connhash=connhash)

        assert any(
            "Malformed packet received: signature verification failed" in rec.getMessage()
            for rec in caplog.records
        )
        assert any(rec.levelno == logging.ERROR for rec in caplog.records)


class TestClassicEncryptorGoldenVectors:
    """Validate cryptographic outputs against immutable golden vectors."""

    def test_visitor_golden_vectors(self, crypto_golden_vectors: dict[str, Any]) -> None:
        """Verify Visitor role vectors (4-byte signature truncation, header 0x02)."""
        for vec in crypto_golden_vectors["visitor"]:
            key = bytes.fromhex(vec["key_hex"])
            connhash = bytes.fromhex(vec["connhash_hex"])
            packet = bytes.fromhex(vec["packet_hex"])
            expected_sig = bytes.fromhex(vec["expected_sig_hex"])
            expected_digested = bytes.fromhex(vec["expected_digested_hex"])
            expected_wire = bytes.fromhex(vec["expected_wire_hex"])

            encryptor = ClassicEncryptor(key=key, sig_len=vec["sig_len"])

            # 1. Digest produces exact expected bytes
            digested = encryptor.digest(packet=packet, connhash=connhash)
            assert digested == expected_digested
            assert digested[:4] == expected_sig
            assert digested[4:] == packet

            # 2. Wire frame has correct auth level prefix (0x02 for visitor)
            wire_packet = b"\x02" + digested
            assert wire_packet == expected_wire

            # 3. Verify unpacks original packet
            verified = encryptor.verify(packet=digested, connhash=connhash)
            assert verified == packet

    def test_manager_golden_vectors(self, crypto_golden_vectors: dict[str, Any]) -> None:
        """Verify Manager role vectors (full 16-byte CMAC signature, header 0x03)."""
        for vec in crypto_golden_vectors["manager"]:
            key = bytes.fromhex(vec["key_hex"])
            connhash = bytes.fromhex(vec["connhash_hex"])
            packet = bytes.fromhex(vec["packet_hex"])
            expected_sig = bytes.fromhex(vec["expected_sig_hex"])
            expected_digested = bytes.fromhex(vec["expected_digested_hex"])
            expected_wire = bytes.fromhex(vec["expected_wire_hex"])

            encryptor = ClassicEncryptor(key=key, sig_len=vec["sig_len"])

            # 1. Digest produces exact 16-byte signature
            digested = encryptor.digest(packet=packet, connhash=connhash)
            assert digested == expected_digested
            assert digested[:16] == expected_sig
            assert digested[16:] == packet

            # 2. Wire frame has correct auth level prefix (0x03 for manager)
            wire_packet = b"\x03" + digested
            assert wire_packet == expected_wire

            # 3. Verify unpacks original packet
            verified = encryptor.verify(packet=digested, connhash=connhash)
            assert verified == packet

    def test_independent_rf4493_cmac_reference(self) -> None:
        """Verify against an independently calculated RFC 4493 CMAC reference."""
        key = bytes.fromhex("fedcba98765432100123456789abcdef")
        connhash = bytes.fromhex("1122334455667788")
        packet = b"\x00\x05\x03\x01\x80"  # seq 5, opcode 3 (SET_LEVEL), unit 1, 50%

        # Independently calculate reference CMAC
        reference_cmac = CMAC(AES(key))
        reference_cmac.update(connhash + packet)
        expected_full_mac = reference_cmac.finalize()

        # Visitor 4-byte truncation
        visitor_encryptor = ClassicEncryptor(key=key, sig_len=4)
        visitor_digested = visitor_encryptor.digest(packet=packet, connhash=connhash)
        assert visitor_digested[:4] == expected_full_mac[:4]
        assert visitor_encryptor.verify(packet=visitor_digested, connhash=connhash) == packet

        # Manager 16-byte full MAC
        manager_encryptor = ClassicEncryptor(key=key, sig_len=16)
        manager_digested = manager_encryptor.digest(packet=packet, connhash=connhash)
        assert manager_digested[:16] == expected_full_mac
        assert manager_encryptor.verify(packet=manager_digested, connhash=connhash) == packet


class TestClassicEncryptorNegativeVectors:
    """Test rejection of tampered packets, wrong keys, and mismatched connection hashes."""

    def test_reject_altered_payload(self) -> None:
        """Altering a single bit in the payload must fail verification."""
        key = b"\x42" * 16
        connhash = b"\x99" * 8
        encryptor = ClassicEncryptor(key=key, sig_len=4)

        digested = bytearray(encryptor.digest(packet=b"\x00\x01\x03\x01\xff", connhash=connhash))

        # Alter payload byte
        digested[-1] ^= 0x01

        with pytest.raises(InvalidSignature):
            encryptor.verify(packet=bytes(digested), connhash=connhash)

    def test_reject_wrong_key(self) -> None:
        """Valid packet verified with a different key must fail."""
        key_sender = b"\x11" * 16
        key_receiver = b"\x22" * 16
        connhash = b"\x99" * 8

        sender = ClassicEncryptor(key=key_sender, sig_len=4)
        receiver = ClassicEncryptor(key=key_receiver, sig_len=4)

        digested = sender.digest(packet=b"\x00\x01\x03\x01\xff", connhash=connhash)

        with pytest.raises(InvalidSignature):
            receiver.verify(packet=digested, connhash=connhash)

    def test_reject_wrong_connhash(self) -> None:
        """Valid packet verified with a different connection hash must fail."""
        key = b"\x11" * 16
        connhash_valid = b"\x01" * 8
        connhash_wrong = b"\x02" * 8

        encryptor = ClassicEncryptor(key=key, sig_len=4)
        digested = encryptor.digest(packet=b"\x00\x01\x03\x01\xff", connhash=connhash_valid)

        with pytest.raises(InvalidSignature):
            encryptor.verify(packet=digested, connhash=connhash_wrong)

    def test_packet_counter_alters_signature_preventing_replay(self) -> None:
        """Different packet sequence counters must produce distinct signatures."""
        key = b"\x55" * 16
        connhash = b"\x77" * 8
        encryptor = ClassicEncryptor(key=key, sig_len=4)

        # Same command (turn on), different sequence counters
        packet_seq1 = b"\x00\x01\x03\x01\xff"
        packet_seq2 = b"\x00\x02\x03\x01\xff"

        digested1 = encryptor.digest(packet=packet_seq1, connhash=connhash)
        digested2 = encryptor.digest(packet=packet_seq2, connhash=connhash)

        sig1 = digested1[:4]
        sig2 = digested2[:4]

        assert sig1 != sig2, "Different sequence counters must produce distinct signatures"
