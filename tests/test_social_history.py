import unittest
from lala_core.social import SocialHistory


class SocialTests(unittest.TestCase):
    def test_reject_untrusted_and_out_of_order(self):
        h = SocialHistory(capacity=2)
        self.assertFalse(h.ingest(channel="party", text="未核對", revision=1,
                                  authoritative=False))
        self.assertTrue(h.ingest(channel="system", text="a", revision=1,
                                 authoritative=True))
        self.assertFalse(h.ingest(channel="system", text="duplicate", revision=1,
                                  authoritative=True))
        self.assertTrue(h.ingest(channel="party", text="b", revision=2,
                                 authoritative=True))
        self.assertTrue(h.ingest(channel="guild", text="c", revision=3,
                                 authoritative=True))
        self.assertEqual([x.text for x in h.view()], ["b", "c"])
        h.reset()
        self.assertFalse(h.view())

    def test_invalid_channels_and_large_payload(self):
        h = SocialHistory()
        self.assertFalse(h.ingest(channel="unknown", text="x", revision=1,
                                  authoritative=True))
        self.assertFalse(h.ingest(channel="system", text="x"*3000, revision=1,
                                  authoritative=True))
