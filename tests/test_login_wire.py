"""All examples use synthetic account strings and synthetic old-protocol packets."""
import struct
import unittest

from lala_core.login import LoginError
from lala_core.login_wire import (
    OLD_TX_XOR, build_legacy_request, decode_legacy_reply,
    decoder_for_legacy_fixture,
)
from lala_core.wire import ObservedPacket, WireDecodeError


class LegacyLoginWireTests(unittest.TestCase):
    def test_request_kind_zero_matches_reference_layout(self):
        raw = build_legacy_request("demo", "fake_pass", kind=0)
        plain = bytes(byte ^ OLD_TX_XOR for byte in raw)
        self.assertEqual(plain[:2], b"\xc4\xc6")
        self.assertEqual(int.from_bytes(plain[2:4], "little"), len(plain)-4)
        self.assertEqual(plain[4:6], b"\x3f\x07")
        self.assertEqual(plain[6:11], bytes((0, 0, 3, 0, 4)))
        self.assertEqual(plain[11:15], b"demo")
        self.assertEqual(plain[15], 9)
        self.assertEqual(plain[16:], b"fake_pass")

    def test_formal_login_kind_two_and_bad_credentials(self):
        raw = build_legacy_request("abc", "def", kind=2)
        plain = bytes(byte ^ OLD_TX_XOR for byte in raw)
        self.assertEqual(plain[6], 2)
        for account, password, kind in (
            ("", "pass", 0), ("a"*256, "pass", 0),
            ("secret space", "p", 2), ("abc", "pass", 1),
        ):
            with self.subTest(kind=kind), self.assertRaises(LoginError):
                build_legacy_request(account, password, kind=kind)

    def test_result_strictly_rejects_unknown_server_format(self):
        outcome = decode_legacy_reply(ObservedPacket(63, 7, b"\0\x02"),
                                      expected_kind=2)
        self.assertTrue(outcome.accepted)
        self.assertFalse(outcome.verified_current_server)
        self.assertFalse(decode_legacy_reply(ObservedPacket(63, 7, b"\x03\x02"),
                                            expected_kind=2).accepted)
        for packet in (ObservedPacket(1, 23, b""),
                       ObservedPacket(63, 7, b"\0"),
                       ObservedPacket(63, 7, b"\0\x02\x03"),
                       ObservedPacket(63, 7, b"\0\0")):
            with self.subTest(packet=packet), self.assertRaises(WireDecodeError):
                decode_legacy_reply(packet, expected_kind=2)

    def test_fragmented_xor_reply_is_only_offline_fixture(self):
        plain = b"\xc4\xc6" + struct.pack("<H", 4) + b"\x3f\x07\0\x02"
        raw = bytes(b ^ OLD_TX_XOR for b in plain)
        decoder = decoder_for_legacy_fixture()
        self.assertEqual(decoder.feed(raw[:3]), ())
        packets = decoder.feed(raw[3:])
        self.assertEqual(len(packets), 1)
        self.assertTrue(decode_legacy_reply(packets[0], expected_kind=2).accepted)
        self.assertFalse(decode_legacy_reply(packets[0], expected_kind=2).verified_current_server)
        decoder.finish()
