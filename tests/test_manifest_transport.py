import unittest
from hashlib import sha256
import zlib
from lala_core.manifest_transport import (
    MAX_MANIFEST_BYTES, combine_manifest_receipts,
    fetch_manifest_receipts, verify_manifest_transport,
)
from lala_core.official_versions import (
    ObservedVersions, OfficialVersionError, package_url,
)


def observation():
    return ObservedVersions(
        "1.4.0", "1.4.22",
        (("DataPackage", "1280_2026_10_29_12_30_20_40"),
         ("MainPackage", "1280_2026_10_29_12_30_20_41")),
        "2026-10-29T10:00:00Z",
    )


def crc(data):
    return (zlib.crc32(data) & 0xffffffff).to_bytes(4, "little").hex().encode("ascii")


class ManifestTests(unittest.TestCase):
    def test_two_independent_manifests_and_nonready_catalog(self):
        obs = observation()
        requests = []
        contents = {"DataPackage": b"manifest-D", "MainPackage": b"manifest-M"}
        def fetch(url, *, limit):
            requests.append((url, limit))
            name = "DataPackage" if "DataPackage." in url else "MainPackage"
            return crc(contents[name]) if url.endswith(".hash") else contents[name]
        pair = fetch_manifest_receipts(obs, fetcher=fetch)
        self.assertEqual(len(requests), 4)
        self.assertEqual({r.package for r in pair.manifests},
                         {"MainPackage", "DataPackage"})
        self.assertEqual(pair.manifests[0].sha256_hex,
                         sha256(b"manifest-D").hexdigest())
        self.assertEqual(len(pair.catalog_key), 64)
        self.assertFalse(pair.can_login)
        self.assertTrue(all(not r.parsed_and_compatible for r in pair.manifests))
        self.assertTrue(all(limit == (8 if url.endswith(".hash") else MAX_MANIFEST_BYTES)
                            for url, limit in requests))

    def test_corrupted_manifest_and_wrong_endianness_rejected(self):
        obs = observation()
        data = b"manifest-D"
        with self.assertRaises(OfficialVersionError):
            verify_manifest_transport(obs, "DataPackage", crc(data), data+b"x")
        with self.assertRaises(OfficialVersionError):
            verify_manifest_transport(obs, "DataPackage", b"FFFFFFFFF", data)
        with self.assertRaises(OfficialVersionError):
            verify_manifest_transport(obs, "DataPackage", b"html", data)
        with self.assertRaises(OfficialVersionError):
            verify_manifest_transport(obs, "Unknown", crc(data), data)

    def test_duplicate_and_mismatched_receipts(self):
        obs = observation()
        one = verify_manifest_transport(obs, "DataPackage", crc(b"d"), b"d")
        two = verify_manifest_transport(obs, "MainPackage", crc(b"m"), b"m")
        with self.assertRaises(OfficialVersionError):
            combine_manifest_receipts(obs, (one, one))
        with self.assertRaises(OfficialVersionError):
            combine_manifest_receipts(obs, (one,))
        wrong = ObservedVersions(
            obs.exe_version, "1.4.23", obs.package_versions, obs.checked_at_utc)
        with self.assertRaises(OfficialVersionError):
            combine_manifest_receipts(wrong, (one, two))

    def test_same_package_version_different_content_changes_catalog_identity(self):
        obs = observation()
        one = verify_manifest_transport(obs, "DataPackage", crc(b"d"), b"d")
        two = verify_manifest_transport(obs, "MainPackage", crc(b"m"), b"m")
        other = verify_manifest_transport(obs, "MainPackage", crc(b"M"), b"M")
        a = combine_manifest_receipts(obs, (one, two))
        b = combine_manifest_receipts(obs, (one, other))
        self.assertNotEqual(a.catalog_key, b.catalog_key)

    def test_missing_package_stops_without_fake_receipt(self):
        obs = observation()
        def fetch(url, *, limit):
            if "MainPackage." in url:
                raise OSError("network unavailable")
            return crc(b"d") if url.endswith(".hash") else b"d"
        with self.assertRaises(OfficialVersionError):
            fetch_manifest_receipts(obs, fetcher=fetch)

    def test_version_url_uses_observed_path_not_fixed_1275(self):
        self.assertIn("/1.4.22/", package_url("1.4.22", "MainPackage", "bytes"))
