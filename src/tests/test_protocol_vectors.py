"""Golden-vector tests asserting exact opcode and packet bytes for Classic Casambi protocol."""

import ast
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from casambi_classic_ble.constants import CasambiCommands
from casambi_classic_ble.device import CasambiDevice


@pytest.fixture
def golden_vectors() -> dict[str, Any]:
    """Load golden vectors fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "golden_vectors.json"
    with open(fixture_path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data


class TestProtocolGoldenVectors:
    """Test suite for validating exact opcode bytes and packet encodings against golden vectors."""

    def test_all_constants_opcodes_covered(self, golden_vectors: dict[str, Any]) -> None:
        """Every opcode in CasambiCommands and every opcode used in device.py must be in golden_vectors."""
        configured_opcodes = {vector["opcode"] for vector in golden_vectors["opcodes"].values()}
        for cmd in CasambiCommands:
            assert cmd.value in configured_opcodes, (
                f"Opcode {cmd.name} ({cmd.value:#02x}) is missing from golden_vectors"
            )

        # Introspect device.py to find all command values passed to _send_command
        device_py = Path(__file__).parents[1] / "casambi_classic_ble" / "device.py"
        tree = ast.parse(device_py.read_text(encoding="utf-8"))
        used_opcodes: set[int] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                is_send_command = isinstance(func, ast.Attribute) and func.attr == "_send_command"
                if is_send_command:
                    for kw in node.keywords:
                        if kw.arg == "command":
                            if isinstance(kw.value, ast.Constant) and isinstance(
                                kw.value.value, int
                            ):
                                used_opcodes.add(kw.value.value)
                            elif isinstance(kw.value, ast.Attribute):
                                attr_name = kw.value.attr
                                if hasattr(CasambiCommands, attr_name):
                                    used_opcodes.add(getattr(CasambiCommands, attr_name).value)

        assert len(used_opcodes) > 0, "AST scan did not find any _send_command calls in device.py"
        for opcode_val in used_opcodes:
            assert opcode_val in configured_opcodes, (
                f"Opcode {opcode_val:#02x} used by device.py is missing from golden_vectors"
            )

    def test_all_golden_vectors_have_provenance(self, golden_vectors: dict[str, Any]) -> None:
        """Every vector entry must declare valid provenance ('captured' or 'derived')."""
        valid_provenances = {"captured", "derived"}

        for beacon in golden_vectors["advertisements"]:
            assert "provenance" in beacon, f"Missing provenance in advertisement: {beacon}"
            assert beacon["provenance"] in valid_provenances

        for packet in golden_vectors["status_packets"]:
            assert "provenance" in packet, f"Missing provenance in status packet: {packet}"
            assert packet["provenance"] in valid_provenances

        for name, vector in golden_vectors["opcodes"].items():
            assert "provenance" in vector, f"Missing provenance in opcode vector '{name}': {vector}"
            assert vector["provenance"] in valid_provenances

        assert "provenance" in golden_vectors["protected_mesh_xor"]
        assert golden_vectors["protected_mesh_xor"]["provenance"] in valid_provenances

    @pytest.mark.asyncio
    async def test_set_level_encodings_match_golden_vectors(
        self,
        mock_bleak_client: AsyncMock,
        golden_vectors: dict[str, Any],
    ) -> None:
        """Verify SET_LEVEL command produces exact golden byte sequences."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        written_packets: list[bytes] = []

        async def capture_write(char_uuid: str, data: bytes, *, response: bool = True) -> None:
            written_packets.append(data)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=capture_write)

        # 1. Dim level (50%)
        dim_vector = golden_vectors["opcodes"]["SET_LEVEL_DIM"]
        await device.set_level(unit_id=dim_vector["unit_id"], level=dim_vector["level_float"])
        assert written_packets[-1].hex() == dim_vector["frame_hex"]

        # 2. Turn ON (2-byte unit format)
        on_vector = golden_vectors["opcodes"]["SET_LEVEL_2BYTE_ON"]
        await device.turn_on(unit_id=on_vector["unit_id"])
        assert written_packets[-1].hex() == on_vector["frame_hex"]

        # 3. Turn OFF (2-byte unit format)
        off_vector = golden_vectors["opcodes"]["SET_LEVEL_2BYTE_OFF"]
        await device.turn_off(unit_id=off_vector["unit_id"])
        assert written_packets[-1].hex() == off_vector["frame_hex"]

        # 4. Broadcast ON
        bcast_on = golden_vectors["opcodes"]["SET_LEVEL_BROADCAST_ON"]
        await device.turn_on_broadcast()
        assert written_packets[-1].hex() == bcast_on["frame_hex"]

        # 5. Broadcast OFF
        bcast_off = golden_vectors["opcodes"]["SET_LEVEL_BROADCAST_OFF"]
        await device.turn_off_broadcast()
        assert written_packets[-1].hex() == bcast_off["frame_hex"]

    @pytest.mark.asyncio
    async def test_color_temperature_encoding_matches_golden_vector(
        self,
        mock_bleak_client: AsyncMock,
        golden_vectors: dict[str, Any],
    ) -> None:
        """Verify SET_COLOR_TEMP command matches exact golden byte vector."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        cct_vector = golden_vectors["opcodes"]["SET_COLOR_TEMP"]
        written_packets: list[bytes] = []

        async def capture_write(char_uuid: str, data: bytes, *, response: bool = True) -> None:
            written_packets.append(data)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=capture_write)

        await device.set_color_temperature(
            unit_id=cct_vector["unit_id"], temp_kelvin=cct_vector["temp_kelvin"]
        )
        assert written_packets[-1].hex() == cct_vector["frame_hex"]

    @pytest.mark.asyncio
    async def test_rgb_encoding_matches_golden_vector(
        self,
        mock_bleak_client: AsyncMock,
        golden_vectors: dict[str, Any],
    ) -> None:
        """Verify SET_RGB command matches exact golden byte vector."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        rgb_vector = golden_vectors["opcodes"]["SET_RGB"]
        written_packets: list[bytes] = []

        async def capture_write(char_uuid: str, data: bytes, *, response: bool = True) -> None:
            written_packets.append(data)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=capture_write)

        await device.set_rgb(
            unit_id=rgb_vector["unit_id"],
            r=rgb_vector["r"],
            g=rgb_vector["g"],
            b=rgb_vector["b"],
        )
        assert written_packets[-1].hex() == rgb_vector["frame_hex"]

    @pytest.mark.asyncio
    async def test_authentication_matches_golden_vector(
        self,
        mock_bleak_client: AsyncMock,
        golden_vectors: dict[str, Any],
    ) -> None:
        """Verify AUTHENTICATE opcode and MD5 hash payload match golden vector."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        auth_vector = golden_vectors["opcodes"]["AUTHENTICATE"]
        written_packets: list[bytes] = []

        async def capture_write(char_uuid: str, data: bytes, *, response: bool = True) -> None:
            written_packets.append(data)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=capture_write)

        # "password" has MD5: 5f4dcc3b5aa765d61d8327deb882cf99
        await device.authenticate(password="password")
        assert written_packets[-1].hex() == auth_vector["frame_hex"]

    @pytest.mark.asyncio
    async def test_get_state_and_unit_state_match_golden_vectors(
        self,
        mock_bleak_client: AsyncMock,
        golden_vectors: dict[str, Any],
    ) -> None:
        """Verify GET_STATE (0x14) and GET_UNIT_STATE (0x0F) match golden vectors."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        written_packets: list[bytes] = []

        async def capture_write(char_uuid: str, data: bytes, *, response: bool = True) -> None:
            written_packets.append(data)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=capture_write)

        # request_state calls 0x14 then 0x0F
        await device.request_state(unit_id=1, settle=0.0)
        assert len(written_packets) == 2
        assert written_packets[0].hex() == golden_vectors["opcodes"]["GET_STATE"]["frame_hex"]
        assert written_packets[1].hex() == golden_vectors["opcodes"]["GET_UNIT_STATE"]["frame_hex"]

    @pytest.mark.asyncio
    async def test_direct_on_off_and_info_opcodes_match_golden_vectors(
        self,
        mock_bleak_client: AsyncMock,
        golden_vectors: dict[str, Any],
    ) -> None:
        """Verify TURN_LIGHT_ON (0x01), TURN_LIGHT_OFF (0x02), GET_DEVICE_INFO (0x10), GET_NETWORK_INFO (0x11)."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        written_packets: list[bytes] = []

        async def capture_write(char_uuid: str, data: bytes, *, response: bool = True) -> None:
            written_packets.append(data)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=capture_write)

        # Direct TURN_LIGHT_ON (0x01)
        await device._send_command(
            command=CasambiCommands.TURN_LIGHT_ON,
            payload=bytes.fromhex(golden_vectors["opcodes"]["TURN_LIGHT_ON"]["payload_hex"]),
        )
        assert written_packets[-1].hex() == golden_vectors["opcodes"]["TURN_LIGHT_ON"]["frame_hex"]

        # Direct TURN_LIGHT_OFF (0x02)
        await device._send_command(
            command=CasambiCommands.TURN_LIGHT_OFF,
            payload=bytes.fromhex(golden_vectors["opcodes"]["TURN_LIGHT_OFF"]["payload_hex"]),
        )
        assert written_packets[-1].hex() == golden_vectors["opcodes"]["TURN_LIGHT_OFF"]["frame_hex"]

        # GET_DEVICE_INFO (0x10)
        await device._send_command(
            command=CasambiCommands.GET_DEVICE_INFO,
            payload=bytes.fromhex(golden_vectors["opcodes"]["GET_DEVICE_INFO"]["payload_hex"]),
        )
        assert (
            written_packets[-1].hex() == golden_vectors["opcodes"]["GET_DEVICE_INFO"]["frame_hex"]
        )

        # GET_NETWORK_INFO (0x11)
        await device._send_command(
            command=CasambiCommands.GET_NETWORK_INFO,
            payload=bytes.fromhex(golden_vectors["opcodes"]["GET_NETWORK_INFO"]["payload_hex"]),
        )
        assert (
            written_packets[-1].hex() == golden_vectors["opcodes"]["GET_NETWORK_INFO"]["frame_hex"]
        )

    @pytest.mark.asyncio
    async def test_turn_on_off_by_address_match_golden_vectors(
        self,
        mock_bleak_client: AsyncMock,
        golden_vectors: dict[str, Any],
    ) -> None:
        """Verify turn_on_by_address (0x81) and turn_off_by_address (0x82) match golden vectors."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF", client=mock_bleak_client)
        device.is_connected = True

        written_packets: list[bytes] = []

        async def capture_write(char_uuid: str, data: bytes, *, response: bool = True) -> None:
            written_packets.append(data)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=capture_write)

        on_long_vector = golden_vectors["opcodes"]["TURN_LIGHT_ON_LONG"]
        await device.turn_on_by_address(address=on_long_vector["address"])
        assert written_packets[-1].hex() == on_long_vector["frame_hex"]

        off_long_vector = golden_vectors["opcodes"]["TURN_LIGHT_OFF_LONG"]
        await device.turn_off_by_address(address=off_long_vector["address"])
        assert written_packets[-1].hex() == off_long_vector["frame_hex"]

    def test_advertisement_beacons_match_golden_vectors(
        self,
        golden_vectors: dict[str, Any],
    ) -> None:
        """Verify advertisement payload parsing against golden vectors."""
        device = CasambiDevice(address="66:55:44:33:22:11")

        for beacon in golden_vectors["advertisements"]:
            raw_payload = bytes.fromhex(beacon["raw_hex"])
            status = device.update_from_advertisement(mfr_data=raw_payload)
            assert status is not None
            assert status["on"] == beacon["expected_status"]["on"]
            assert status["dimLevel"] == beacon["expected_status"]["dimLevel"]
            assert status["level_percent"] == beacon["expected_status"]["level_percent"]
            assert status["source"] == beacon["expected_status"]["source"]

    def test_status_packet_decoding_matches_golden_vectors(
        self,
        golden_vectors: dict[str, Any],
    ) -> None:
        """Verify incoming status packet unpack matches expected fields."""
        device = CasambiDevice(address="AA:BB:CC:DD:EE:FF")

        for packet in golden_vectors["status_packets"]:
            raw_bytes = bytes.fromhex(packet["raw_hex"])
            status = device.parse_status(data=raw_bytes)
            assert status["opcode"] == packet["expected_opcode"]
            assert status["id"] == packet["expected_id"]
            assert status["on"] == packet["expected_on"]
            assert status["dimLevel"] == packet["expected_dim_level"]
            assert status["level_percent"] == packet["expected_level_percent"]
