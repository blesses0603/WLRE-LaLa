"""1262 legacy replay contract: synthetic fixtures only, never access official server."""
import struct
import unittest
from lala_core.wire import ReadOnlyFrameDecoder, ObservedPacket, WireDecodeError
from lala_core.observed_events import decode_observed
from lala_core.observed_ledger import ObservedLedger


def encoded_packet(main, sub, payload=b"", *, xor=0xad):
    plain = b"\xc4\xc6" + struct.pack("<H", len(payload) + 2) + bytes((main, sub)) + payload
    return bytes(x ^ xor for x in plain)


def inventory_item(slot=3, item_id=101, count=5):
    # From the verified 1262 S23-5 item layout, only slot/id/count enter UI.
    return (
        struct.pack("<BHB", slot, item_id, count)
        + b"\0" * (1+1+4 + 4+4 + 2)
        + struct.pack("<dd", 0.0, 0.0)
        + b"\0" * (1+1+2 + 2 + 1+2+4 + 4*3 + 1+1+1+1)
    )


class FrameTests(unittest.TestCase):
    def test_fragmented_and_coalesced_frames(self):
        expected = (ObservedPacket(26, 4, b"\x88\x13\0\0"),
                    ObservedPacket(52, 1, b"\x02\0"))
        payload = b"".join(encoded_packet(p.main, p.sub, p.payload) for p in expected)
        reader = ReadOnlyFrameDecoder(xor_key=0xad, profile="legacy-1262")
        seen = ()
        for fragment in (payload[:1], payload[1:3], payload[3:11], payload[11:]):
            seen += reader.feed(fragment)
        reader.finish()
        self.assertEqual(seen, expected)

    def test_reject_unsupported_profile_and_corrupt_frames(self):
        with self.assertRaises(WireDecodeError):
            ReadOnlyFrameDecoder(xor_key=0xad, profile="official-1286")
        with self.assertRaises(WireDecodeError):
            ReadOnlyFrameDecoder(xor_key=-1, profile="legacy-1262")
        d = ReadOnlyFrameDecoder(xor_key=0, profile="legacy-1262")
        with self.assertRaises(WireDecodeError):
            d.feed(b"\x00\x00\x02\x00\x01\x0b")
        with self.assertRaises(WireDecodeError):
            ReadOnlyFrameDecoder(xor_key=0, profile="legacy-1262").feed(b"\xc4\xc6\x01\0")

    def test_incomplete_frames_and_reset(self):
        d = ReadOnlyFrameDecoder(xor_key=0, profile="legacy-1262")
        self.assertEqual(d.feed(b"\xc4\xc6\x06\0\x01"), ())
        with self.assertRaises(WireDecodeError):
            d.finish()
        self.assertEqual(d.feed(encoded_packet(1, 11, xor=0)),
                         (ObservedPacket(1, 11, b""),))


class ObservedReadOnlyTests(unittest.TestCase):
    def test_gold_and_bag_from_synthetic_legacy_packets(self):
        ledger = ObservedLedger(profile="legacy-1262")
        events = [
            ObservedPacket(26, 1, b"\x01\0\0\0\0"),
            ObservedPacket(26, 4, struct.pack("<I", 5000)),
            ObservedPacket(26, 2, struct.pack("<IB", 750, 0)),
            ObservedPacket(23, 5, b"\x14" + inventory_item()),
        ]
        for packet in events:
            self.assertTrue(ledger.apply(decode_observed(packet, profile="legacy-1262")))
        state = ledger.snapshot()
        self.assertEqual(state.gold, 4250)
        self.assertEqual(state.slots, ((3, 101, 5),))
        self.assertTrue(state.bag_reliable)
        self.assertFalse(state.server_verified)

    def test_unknown_packet_cannot_expose_secrets(self):
        event = decode_observed(
            ObservedPacket(63, 7, b"test-account-password"),
            profile="legacy-1262")
        self.assertEqual(event.kind, "unimplemented")
        self.assertNotIn("password", str(event))
        self.assertNotIn("account", str(event))

    def test_legacy_parser_must_not_be_used_as_current_official_codec(self):
        with self.assertRaises(WireDecodeError):
            decode_observed(ObservedPacket(26, 4, b"\0" * 4),
                            profile="official-1286")
        with self.assertRaises(ValueError):
            ObservedLedger(profile="official-1286")

    def test_bag_rejects_truncated_and_duplicate_slots(self):
        for payload in (b"\x14" + inventory_item()[:-1],
                        b"\x14" + inventory_item() + inventory_item(),
                        b"\x00"):
            with self.subTest(length=len(payload)), self.assertRaises(WireDecodeError):
                decode_observed(ObservedPacket(23, 5, payload),
                                profile="legacy-1262")

    def test_gold_delta_requires_snapshot_and_disallows_underflow(self):
        ledger = ObservedLedger(profile="legacy-1262")
        ledger.apply(decode_observed(
            ObservedPacket(26, 2, struct.pack("<IB", 5, 0)),
            profile="legacy-1262"))
        self.assertFalse(ledger.snapshot().gold_reliable)
        ledger.apply(decode_observed(ObservedPacket(26, 4, struct.pack("<I", 2)),
                                     profile="legacy-1262"))
        ledger.apply(decode_observed(ObservedPacket(26, 2, struct.pack("<IB", 5, 0)),
                                     profile="legacy-1262"))
        self.assertIsNone(ledger.snapshot().gold)

    def test_role_change_clears_stale_money_and_bag(self):
        ledger = ObservedLedger(profile="legacy-1262")
        for packet in (ObservedPacket(7, 1, struct.pack("<IHHH", 10, 1, 20, 30)),
                       ObservedPacket(26, 4, struct.pack("<I", 100)),
                       ObservedPacket(23, 5, b"\x14" + inventory_item()),
                       ObservedPacket(12, 1, struct.pack("<IHHH", 11, 1, 1, 2))):
            ledger.apply(decode_observed(packet, profile="legacy-1262"))
        snapshot = ledger.snapshot()
        self.assertIsNone(snapshot.gold)
        self.assertFalse(snapshot.bag_reliable)
        self.assertEqual(snapshot.role_id, 11)

    def test_reject_bad_notify_and_extra_bytes(self):
        for packet in (ObservedPacket(26, 1, struct.pack("<IB", 3, 2)),
                       ObservedPacket(52, 1, b"\x02\0\xff"),
                       ObservedPacket(26, 4, b"\x00")):
            with self.subTest(packet=packet), self.assertRaises(WireDecodeError):
                decode_observed(packet, profile="legacy-1262")
