import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zlib

from lala_core.official_versions import ObservedVersions, OfficialVersionError
from lala_core.resource_bootstrap import bootstrap, install_index
from tests.test_yooasset_index import pack_manifest, REVISION


def observed():
    return ObservedVersions(
        "1.3.0", "1.3.22.1",
        (("DataPackage", REVISION),
         ("MainPackage", "1284_2026_10_28_19_50_04_11")),
        "2026-10-29T09:00:00+00:00",
    )


def fake_get(url, *, limit=16384):
    if "ResourcePath_PC.dat" in url:
        return b'[{"ExeVer":"1.3.0","DataVer":"1.3.22.1"}]'
    main = "MainPackage." in url
    name = "MainPackage" if main else "DataPackage"
    version = dict(observed().package_versions)[name]
    if url.endswith(".version"):
        return version.encode()
    blob = pack_manifest(package=name, revision=version)
    if url.endswith(".hash"):
        return (zlib.crc32(blob) & 0xffffffff).to_bytes(4, "little").hex().encode()
    return blob


class StartupInstallTests(unittest.TestCase):
    def test_first_install_receipt_and_repeat_cache_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = bootstrap(root=tmp, fetcher=fake_get)
            self.assertTrue(first["index_installed"])
            self.assertFalse(first["all_required_bundles_installed"])
            self.assertFalse(first["can_login"])
            self.assertTrue(first["can_open_ui"])
            version_dir = Path(tmp) / first["catalog_key"]
            self.assertTrue((version_dir / "DataPackage.bytes").is_file())
            self.assertTrue((version_dir / "MainPackage.bytes").is_file())
            self.assertTrue((version_dir / "installed.json").is_file())
            self.assertEqual(json.loads((Path(tmp) / "current.json").read_text())["catalog_key"],
                             first["catalog_key"])
            second = bootstrap(root=tmp, fetcher=fake_get)
            self.assertTrue(second["reused_verified_cache"])

    def test_bad_manifest_must_not_publish_or_enter(self):
        with tempfile.TemporaryDirectory() as tmp:
            def bad_get(url, *, limit=16384):
                if "MainPackage." in url and url.endswith(".bytes"):
                    return b"invalid"
                return fake_get(url, limit=limit)
            with self.assertRaises(OfficialVersionError):
                bootstrap(root=tmp, fetcher=bad_get)
            self.assertFalse((Path(tmp) / "current.json").exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_mismatched_revision_never_installs(self):
        with tempfile.TemporaryDirectory() as tmp:
            revised = ObservedVersions("1.3.0", "1.3.22.1",
                                       (("DataPackage", REVISION),
                                        ("MainPackage", REVISION)), "T")
            with self.assertRaises(OfficialVersionError):
                install_index(observation=observed(), fetcher=fake_get, root=tmp,
                              verify_latest=lambda: revised)
            self.assertFalse((Path(tmp) / "current.json").exists())

    def test_corrupted_old_cache_blocks_startup_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = bootstrap(root=tmp, fetcher=fake_get)
            path = Path(tmp) / first["catalog_key"] / "DataPackage.bytes"
            path.write_bytes(b"tampered")
            with self.assertRaises(OfficialVersionError):
                bootstrap(root=tmp, fetcher=fake_get)
            self.assertEqual(path.read_bytes(), b"tampered")

    def test_atomic_publish_only_after_both_manifests_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            def fetching(url, *, limit=16384):
                calls.append(url)
                return fake_get(url, limit=limit)
            result = bootstrap(root=tmp, fetcher=fetching)
            # 3 lookup + 4 manifest + 3 recheck, all bounded; no game server.
            self.assertEqual(len(calls), 10)
            self.assertEqual(sum(x.endswith(".bytes") for x in calls), 2)
            self.assertEqual(sum(x.endswith(".hash") for x in calls), 2)
            self.assertTrue(result["index_installed"])
