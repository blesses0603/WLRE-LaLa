"""Pure synthetic binary manifests; no copied game data or live requests."""
import struct
import unittest
from hashlib import sha256
import zlib

from lala_core.official_versions import OfficialVersionError, ObservedVersions
from lala_core.yooasset_index import parse_manifest, fetch_parsed_catalog


REVISION = "1286_2026_10_29_13_42_37_94"


def text(s):
    data = s.encode("utf-8")
    return struct.pack("<H", len(data)) + data


def pack_manifest(package="DataPackage", revision=REVISION, *,
                  bundle_names=("A", "B"), dependency=True):
    data = struct.pack("<I", 0x00594F4F) + text("2.2.5")
    data += struct.pack("<BBBii", 1, 0, 1, 1, 2)
    data += text("ScriptableBuildPipeline") + text(package) + text(revision) + text("")
    data += struct.pack("<i", 2)
    for name, bid in (("a", 0), ("b", 1)):
        data += text(name) + text("Assets/"+name) + text("guid-"+name)
        data += struct.pack("<H", 0) + struct.pack("<i", bid)
    data += struct.pack("<i", len(bundle_names))
    for i, name in enumerate(bundle_names):
        data += text(name) + struct.pack("<I", 99)
        data += text("hash") + text("crc") + struct.pack("<qB", 40, 0)
        data += struct.pack("<H", 0)  # bundle tags
        data += (struct.pack("<Hi", 1, 0) if i == 1 and dependency
                 else struct.pack("<H", 0))
    return data


class YooIndexTests(unittest.TestCase):
    def test_full_index_and_exact_path_resolution(self):
        index = parse_manifest(pack_manifest(), package="DataPackage", revision=REVISION)
        self.assertEqual(len(index.assets), 2)
        self.assertEqual(len(index.bundles), 2)
        self.assertEqual(index.find_bundle_for_path("Assets/b").name, "B")
        self.assertIsNone(index.find_bundle_for_path("Assets/missing"))
        self.assertEqual(index.bundles[1].dependencies, (0,))
        self.assertFalse(index.summary()["gameplay_compatible"])
        self.assertFalse(index.summary()["asset_schema_validated"])

    def test_bad_package_revision_truncation_and_magic(self):
        data = pack_manifest()
        for bad in (data[:-1], b"BAD!" + data[4:]):
            with self.subTest(size=len(bad)), self.assertRaises(OfficialVersionError):
                parse_manifest(bad, package="DataPackage", revision=REVISION)
        with self.assertRaises(OfficialVersionError):
            parse_manifest(data, package="MainPackage", revision=REVISION)
        with self.assertRaises(OfficialVersionError):
            parse_manifest(data, package="DataPackage", revision="wrong")

    def test_duplicate_bundle_rejected(self):
        with self.assertRaises(OfficialVersionError):
            parse_manifest(pack_manifest(bundle_names=("A", "A")),
                           package="DataPackage", revision=REVISION)

    def test_both_manifest_transport_and_index_without_content_in_summary(self):
        other_rev = "1284_2026_10_28_19_50_04_11"
        observation = ObservedVersions(
            "1.3.0", "1.3.22.1",
            (("DataPackage", REVISION), ("MainPackage", other_rev)),
            "2026-10-29T00:00:00Z",
        )
        calls = []
        def fetched(url, *, limit):
            calls.append(url)
            is_main = "MainPackage." in url
            content = pack_manifest(
                package="MainPackage" if is_main else "DataPackage",
                revision=other_rev if is_main else REVISION)
            return ((zlib.crc32(content)&0xffffffff).to_bytes(4, "little").hex().encode()
                    if url.endswith(".hash") else content)
        catalog = fetch_parsed_catalog(observation, fetcher=fetched)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(catalog.indexes), 2)
        self.assertEqual(catalog.indexes[0].summary()["asset_count"], 2)
        self.assertFalse(catalog.can_login)
        self.assertFalse(catalog.protocol_compatible)
        self.assertEqual(len(catalog.transport.catalog_key), 64)
        self.assertNotIn("Assets/a", str(catalog.indexes[0].summary()))

    def test_bad_crc_prevents_parsing(self):
        observation = ObservedVersions(
            "1.3.0", "1.3.22.1",
            (("DataPackage", REVISION), ("MainPackage", REVISION)), "T")
        def corrupt(url, *, limit):
            return b"badcrc00" if url.endswith(".hash") else pack_manifest()
        with self.assertRaises(OfficialVersionError):
            fetch_parsed_catalog(observation, fetcher=corrupt)
