"""27 功能對應的舊版封包尺寸證據：全部離線合成，無網路、無帳密。"""
import unittest

from lala_core.feature_wire_bridge import FeatureWireBridge
from lala_core.features import BY_KEY
from lala_core.wire import ObservedPacket


class FeatureWireBridgeTests(unittest.TestCase):
    def test_all_27_features_covered_and_disconnected(self):
        bridge = FeatureWireBridge(profile="legacy-1262")
        report = bridge.report()
        self.assertFalse(report.server_verified)
        self.assertEqual({name for name, _ in report.accepted}, set(BY_KEY))
        self.assertEqual(len(report.accepted), 27)
        self.assertFalse(any(value for _, value in report.accepted))

    def test_fixed_legacy_packets_are_routed_by_feature_only(self):
        bridge = FeatureWireBridge(profile="legacy-1262")
        sources = (
            (8, 1, 10, "characters"),
            (8, 2, 13, "companions"),
            (6, 1, 8, "world"),
            (1, 1, 4, "chat"),
            (13, 4, 4, "party"),
            (186, 6, 2, "coop"),
            (26, 4, 4, "inventory"),
            (52, 1, 2, "battle"),
            (85, 15, 0, "dungeons"),
            (31, 12, 2, "expeditions"),
        )
        for main, sub, length, _ in sources:
            bridge.observe(ObservedPacket(main, sub, b"x" * length))
        data = bridge.report()
        matched = dict(data.accepted)
        self.assertEqual({feature for *_, feature in sources},
                         {name for name, count in matched.items() if count})
        self.assertTrue(all(matched[feature] == 1 for *_, feature in sources))
        self.assertFalse(any(v for _, v in data.rejected_lengths))
        self.assertFalse(data.server_verified)

    def test_invalid_sizes_do_not_create_evidence_and_s39_is_candidate_only(self):
        bridge = FeatureWireBridge(profile="legacy-1262")
        payload = b"secret-not-to-be-logged"
        bridge.observe(ObservedPacket(8, 1, payload))
        bridge.observe(ObservedPacket(39, 60, b"private-name" * 15))
        bridge.observe(ObservedPacket(39, 61, payload))
        report = bridge.report()
        self.assertEqual(dict(report.accepted)["characters"], 0)
        self.assertEqual(dict(report.rejected_lengths)["characters"], 1)
        self.assertEqual(dict(report.candidate_only)["guild"], 1)
        self.assertEqual(dict(report.accepted)["guild"], 0)
        self.assertNotIn("secret-not-to-be-logged", repr(report))
        self.assertNotIn("private-name", repr(report))

    def test_invalid_profile_and_packet_are_rejected(self):
        with self.assertRaises(ValueError):
            FeatureWireBridge(profile="current-official")
        with self.assertRaises(TypeError):
            FeatureWireBridge(profile="legacy-1262").observe(object())

    def test_repeat_event_is_anonymous_count_not_a_session(self):
        bridge = FeatureWireBridge(profile="legacy-1262")
        for _ in range(16):
            bridge.observe(ObservedPacket(8, 1, b"x" * 10))
        snapshot = bridge.report()
        self.assertEqual(dict(snapshot.accepted)["characters"], 16)
        self.assertFalse(snapshot.server_verified)
        self.assertNotIn("payload", str(snapshot))
