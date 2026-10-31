"""S3-1 decoder contract. Completely synthetic, never records user data."""
import struct
import unittest
from lala_core.legacy_world import parse_legacy_world_player
from lala_core.wire import ObservedPacket, WireDecodeError


def fixture(*, role_id=321, name="測試角色", equips=0, scene=100, trailing=b""):
    name_bytes = name.encode("utf-16le")
    return (
        struct.pack("<IBHHH", role_id, 0, scene, 30, 42)
        + b"\0" * (3 + 8 + 2)
        + bytes((equips,))
        + b"\0" * (equips * 6)
        + bytes((len(name_bytes),)) + name_bytes
        + b"\0" * 8 + b"\x00"
        + struct.pack("<H", 0) + trailing
    )


class LegacyWorldParserTests(unittest.TestCase):
    def test_old_full_character_layout(self):
        result = parse_legacy_world_player(
            ObservedPacket(3, 1, fixture(equips=2)))
        self.assertEqual(result.role_id, 321)
        self.assertEqual(result.character_name, "測試角色")
        self.assertEqual((result.scene, result.x, result.y), (100, 30, 42))
        self.assertEqual(result.schema, "legacy-1262")
        self.assertFalse(result.official_identity_verified)

    def test_truncation_and_unexpected_tail_rejected(self):
        blob = fixture()
        for payload in (blob[:3], blob[:15], blob[:-1], blob+b"x"):
            with self.subTest(length=len(payload)), self.assertRaises(WireDecodeError):
                parse_legacy_world_player(ObservedPacket(3, 1, payload))

    def test_reject_unknown_packet_or_zero_role_id(self):
        with self.assertRaises(WireDecodeError):
            parse_legacy_world_player(ObservedPacket(3, 7, fixture()))
        with self.assertRaises(WireDecodeError):
            parse_legacy_world_player(ObservedPacket(3, 1, fixture(role_id=0)))

    def test_bounded_equipment_array(self):
        with self.assertRaises(WireDecodeError):
            parse_legacy_world_player(
                ObservedPacket(3, 1, fixture(equips=33)))
