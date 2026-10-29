"""Isolated synthetic Bundle installation; never contacts the actual game CDN."""
import hashlib
import io
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zlib

from lala_core.bundle_install import InstallError, BundleSpec
from lala_core.official_versions import ObservedVersions, OfficialVersionError
from lala_core.resource_bootstrap import install_resources, verify_installed, main

REV1 = "1286_2026_10_29_13_42_37_94"
REV2 = "1284_2026_10_28_19_50_04_11"
CONTENT = b"LaLa fake downloaded bytes, NOT game content"


def t(s):
    b = s.encode()
    return struct.pack("<H", len(b)) + b


def crc(data):
    return (zlib.crc32(data) & 0xffffffff).to_bytes(4, "little").hex()


def manifest(package, revision):
    """Synthetic 4 LaLa assets -> 1 Bundle + 1 recursive dependency.

    Extra Data/Main game content MUST NOT be installed.
    """
    d = struct.pack("<I", 0x00594F4F) + t("2.2.5") + struct.pack("<BBBii", 1, 0, 1, 1, 2)
    d += t("ScriptableBuildPipeline") + t(package) + t(revision) + t("")
    prefix = "Assets/ResourcesBuild/Data/"
    if package == "DataPackage":
        assets = [(prefix + name + ".bytes", 0) for name in (
            "Eve", "ItemData_C", "SmithData_C", "ScenesData_C")]
        assets += [(prefix + "NotUsedByLaLa.bytes", 2)]
        bundles = [
            ("needed.bundle", (1,)),
            ("dependency.bundle", ()),
            ("unrelated.bundle", ()),
        ]
    else:
        assets = [("Assets/ResourcesBuild/Sprite/Unused.prefab", 0)]
        bundles = [("allgame-main.bundle", ())]
    d += struct.pack("<i", len(assets))
    for path, bundle in assets:
        d += t("asset") + t(path) + t("guid")
        d += struct.pack("<Hi", 0, bundle)
    d += struct.pack("<i", len(bundles))
    for name, dependencies in bundles:
        d += t(name) + struct.pack("<I", 0)
        d += t(hashlib.md5(CONTENT, usedforsecurity=False).hexdigest()) + t(crc(CONTENT))
        d += struct.pack("<qB", len(CONTENT), 0) + struct.pack("<H", 0)
        d += struct.pack("<H", len(dependencies))
        for dep in dependencies:
            d += struct.pack("<i", dep)
    return d


def observed():
    return ObservedVersions("1.3.0", "1.3.22.1",
                            (("DataPackage", REV1), ("MainPackage", REV2)), "test")


def get(url, *, limit):
    p = "MainPackage" if "MainPackage." in url else "DataPackage"
    body = manifest(p, dict(observed().package_versions)[p])
    return crc(body).encode() if url.endswith(".hash") else body


class Response(io.BytesIO):
    status = 200
    def __init__(self, url, data):
        super().__init__(data)
        self.url = url
        self.headers = {"Content-Length": str(len(data))}
    def geturl(self):
        return self.url


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.urls = []

    def opener(self, req, timeout):
        self.urls.append(req.full_url)
        return Response(req.full_url, CONTENT)

    def install(self, **kw):
        return install_resources(root=self.root, observer=observed, fetcher=get,
                                 opener=self.opener, check_disk=False, **kw)

    def test_first_install_reuse_and_offline_entry_gate(self):
        a = self.install()
        self.assertEqual((a.files_total, a.files_downloaded), (2, 2))
        self.assertFalse(a.can_login)
        self.assertEqual(len(self.urls), 2)
        self.assertTrue(all("needed.bundle" in url or "dependency.bundle" in url
                            for url in self.urls), self.urls)
        self.assertTrue(verify_installed(root=self.root, expected_catalog_key=a.catalog_key)["resources_installed"])
        b = self.install()
        self.assertEqual((b.files_downloaded, b.files_reused), (0, 2))
        self.assertEqual(a.selected_asset_count, 4)
        self.assertEqual(len(self.urls), 2)
        self.assertEqual(len(list(self.root.rglob("*.bundle"))), 2)
        self.assertEqual(verify_installed(root=self.root)["schema"], 2)

    def test_ignored_game_bundles_are_never_installed(self):
        result = self.install()
        self.assertEqual(result.files_total, 2)
        self.assertEqual({url.split("/")[-1] for url in self.urls},
                         {"needed.bundle", "dependency.bundle"})
        self.assertFalse(any("unrelated" in url or "allgame-main" in url
                             for url in self.urls))

    def test_receipt_requires_current_lala_feature_selection_policy(self):
        import json
        self.install()
        receipt = self.root / "installed.json"
        marker = json.loads(receipt.read_text())
        marker["resource_policy_key"] = "a" * 64
        receipt.write_text(json.dumps(marker))
        with self.assertRaises(InstallError):
            verify_installed(root=self.root)

    def test_removed_exact_asset_blocks_before_any_game_download(self):
        from lala_core.yooasset_index import parse_manifest
        from lala_core.manifest_transport import (
            ManifestReceipt, ManifestPair)
        from lala_core.yooasset_index import ParsedCatalog
        from lala_core.bundle_install import build_bundle_specs
        obs = observed()
        # Even a perfectly valid official Manifest with other game content
        # is insufficient when reviewed LaLa source asset is missing.
        broken_data = manifest("DataPackage", REV1).replace(
            b"Assets/ResourcesBuild/Data/SmithData_C.bytes",
            b"Assets/ResourcesBuild/Data/NotLaLaData.bytes")
        from lala_core.manifest_transport import verify_manifest_transport
        import hashlib
        def receipt(pkg, rev, body):
            return ManifestReceipt(pkg, obs.data_version, rev, len(body),
                                   hashlib.sha256(body).hexdigest(), crc(body))
        main = manifest("MainPackage", REV2)
        pair = ManifestPair(obs.exe_version, obs.data_version,
                            (receipt("DataPackage", REV1, broken_data),
                             receipt("MainPackage", REV2, main)))
        catalog = ParsedCatalog(pair, (
            parse_manifest(broken_data, package="DataPackage", revision=REV1),
            parse_manifest(main, package="MainPackage", revision=REV2)))
        with self.assertRaisesRegex(InstallError, "缺少經審核"):
            build_bundle_specs(catalog)

    def test_corrupt_bundle_blocks_and_redownloads_only_bad_file(self):
        self.install()
        bundles = list(self.root.rglob("*.bundle"))
        self.assertEqual(len(bundles), 2)
        bundles[0].write_bytes(b"broken")
        with self.assertRaises(InstallError):
            verify_installed(root=self.root)
        repaired = self.install()
        self.assertEqual(repaired.files_downloaded, 1)
        verify_installed(root=self.root)

    def test_interrupted_update_blocks_old_receipt_until_recovery(self):
        first = self.install()
        self.assertTrue(verify_installed(root=self.root)["resources_installed"])
        # Simulate the official next version being observed and a Bundle
        # transfer failing after the old installed receipt was created.
        def broken(req, timeout):
            return Response(req.full_url, CONTENT + b"corrupted")
        bundle = next(self.root.rglob("*.bundle"))
        bundle.write_bytes(b"corrupted")
        with patch.object(self, "opener", broken), self.assertRaises(InstallError):
            self.install()
        self.assertTrue((self.root / "installed.json").exists())
        self.assertTrue((self.root / "install.pending").exists())
        with self.assertRaises(InstallError):
            verify_installed(root=self.root)
        repaired = self.install()
        self.assertEqual(repaired.catalog_key, first.catalog_key)
        self.assertFalse((self.root / "install.pending").exists())
        self.assertTrue(verify_installed(root=self.root)["resources_installed"])

    def test_download_integrity_failure_never_marks_success(self):
        def wrong(req, timeout):
            return Response(req.full_url, CONTENT + b"bad")
        with patch.object(self, "opener", wrong), self.assertRaises(InstallError):
            self.install()
        self.assertFalse((self.root / "installed.json").exists())
        self.assertEqual(list(self.root.rglob("*.partial")), [])

    def test_bad_crc_blocks_before_any_download(self):
        def broken(url, *, limit):
            return b"00000000" if url.endswith(".hash") else get(url, limit=limit)
        with self.assertRaises(OfficialVersionError):
            install_resources(root=self.root, observer=observed, fetcher=broken,
                              opener=self.opener, check_disk=False)
        self.assertEqual(self.urls, [])
        self.assertFalse((self.root / "installed.json").exists())

    def test_version_change_during_transfer_does_not_mark_success(self):
        calls = [0]
        def drifting():
            calls[0] += 1
            value = observed()
            if calls[0] == 1:
                return value
            return ObservedVersions(
                value.exe_version, "1.4.99", value.package_versions, "changed")
        with self.assertRaises(InstallError):
            install_resources(root=self.root, observer=drifting, fetcher=get,
                              opener=self.opener, check_disk=False)
        self.assertFalse((self.root / "installed.json").exists())

    def test_quota_rejects_before_transfer(self):
        with self.assertRaises(InstallError):
            self.install(max_total_bytes=1)
        self.assertEqual(self.urls, [])

    def test_tampered_receipt_cannot_open(self):
        self.install()
        (self.root / "installed.json").write_text('{"resources_installed":true}')
        with self.assertRaises(InstallError):
            verify_installed(root=self.root)

    def test_reject_path_traversal(self):
        for value in ("../outside.bundle", "folder/fake.bundle", "image.exe"):
            with self.subTest(value=value), self.assertRaises(InstallError):
                BundleSpec("1.3.22.1", "DataPackage", REV1, value, 10, "0"*32, "0"*8)

    def test_cli_flags_required(self):
        with patch("lala_core.resource_bootstrap.install_resources") as installer:
            with self.assertRaises(SystemExit):
                main([])
            installer.assert_not_called()
