import unittest
from hashlib import sha256
from tempfile import TemporaryDirectory
from pathlib import Path
from lala_core.resources import ResourceSpec, audit_local_resources


class ResourceTests(unittest.TestCase):
    def test_good_missing_corrupt_and_unsafe_paths(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "safe.bin").write_bytes(b"real")
            good = sha256(b"real").hexdigest()
            results = audit_local_resources(root, (
                ResourceSpec("safe.bin", 4, good),
                ResourceSpec("none.bin", 4, good),
                ResourceSpec("../outside.bin", 4, good),
                ResourceSpec("safe.bin", 4, good),
                ResourceSpec("safe2.bin", 4, "notasha"),
            ))
            self.assertEqual([r.verified for r in results],
                             [True, False, False, False, False])
            self.assertIn("重複", results[3].reason)

    def test_mismatch_fails_closed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a").write_bytes(b"abc")
            results = audit_local_resources(root, (
                ResourceSpec("a", 3, sha256(b"abcd").hexdigest()),
                ResourceSpec("a/../a", 3, sha256(b"abc").hexdigest()),
            ))
            self.assertFalse(any(r.verified for r in results))
