"""舊版 S7-1/S12-1 本人位置的唯讀抽樣：全程合成，不連伺服器。"""
import struct
import unittest

from lala_core.legacy_position_probe import LegacyPositionProbe
from lala_core.wire import ObservedPacket


def position(main, role, scene, x, y, *, extension=b""):
    return ObservedPacket(
        main, 1, struct.pack("<IHHH", role, scene, x, y) + extension)


class LegacyPositionProbeTests(unittest.TestCase):
    def setUp(self):
        self.probe = LegacyPositionProbe(role_id=123, scene=10, x=20, y=30)

    def test_own_updates_and_repeated_position(self):
        self.probe.observe(position(7, 123, 11, 21, 31))
        self.probe.observe(position(12, 123, 11, 21, 31, extension=b"\x01"))
        report = self.probe.report()
        self.assertEqual((report.own_messages, report.changed_messages,
                          report.repeated_messages), (2, 1, 1))
        self.assertEqual((report.scene, report.x, report.y), (11, 21, 31))
        self.assertFalse(report.authoritative)
        self.assertFalse(report.sequence_verified)

    def test_other_player_never_overwrites_selected_character(self):
        self.probe.observe(position(7, 999, 44, 50, 60))
        result = self.probe.report()
        self.assertEqual(result.other_role_messages, 1)
        self.assertEqual(result.own_messages, 0)
        self.assertEqual((result.scene, result.x, result.y), (10, 20, 30))
        self.assertNotIn("999", str(result))

    def test_incomplete_and_invalid_role_are_rejected_without_reset(self):
        self.probe.observe(ObservedPacket(7, 1, b"12345"))
        self.probe.observe(position(12, 0, 40, 30, 20))
        self.probe.observe(position(7, 123, 12, 22, 32))
        result = self.probe.report()
        self.assertEqual(result.invalid_messages, 2)
        self.assertEqual(result.changed_messages, 1)
        self.assertEqual((result.scene, result.x, result.y), (12, 22, 32))

    def test_no_traffic_infers_no_server_sequence(self):
        result = self.probe.report()
        self.assertFalse(result.authoritative)
        self.assertFalse(result.sequence_verified)
        self.assertEqual(result.own_messages, 0)
        self.assertEqual((result.scene, result.x, result.y), (10, 20, 30))

    def test_unknown_messages_do_not_decode_or_leak_payload(self):
        self.probe.observe(ObservedPacket(39, 60, b"private-guild-member"))
        self.probe.observe(ObservedPacket(1, 4, b"password-not-allowed"))
        result = self.probe.report()
        self.assertEqual(result.own_messages, 0)
        self.assertEqual(result.invalid_messages, 0)
        self.assertNotIn("password", repr(result))
        self.assertNotIn("guild", repr(result))

    def test_role_id_and_coordinates_cannot_be_fake_boolean(self):
        for kwargs in (
            {"role_id": True, "scene": 1, "x": 2, "y": 3},
            {"role_id": 0, "scene": 1, "x": 2, "y": 3},
            {"role_id": 2, "scene": True, "x": 2, "y": 3},
            {"role_id": 2, "scene": 1, "x": -1, "y": 3},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                LegacyPositionProbe(**kwargs)

    def test_wrong_input_type_is_rejected(self):
        with self.assertRaises(TypeError):
            self.probe.observe(object())


if __name__ == "__main__":
    unittest.main()
