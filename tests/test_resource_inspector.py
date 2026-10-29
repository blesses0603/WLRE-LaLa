import json
import unittest
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from lala_core.official_versions import ObservedVersions
from lala_core.resource_inspector import inspect, main
from lala_core.startup_readiness import review_startup
from lala_core.manifest_transport import (
    combine_manifest_receipts, verify_manifest_transport
)
from lala_core.official_versions import OfficialVersionError
import zlib


def observation():
    return ObservedVersions(
        "1.4.0", "1.4.22",
        (("DataPackage", "1280_2026_10_29_12_30_20_40"),
         ("MainPackage", "1280_2026_10_29_12_30_20_41")),
        "2026-10-29T00:00:00Z",
    )


class InspectorTests(unittest.TestCase):
    def test_inspector_observation_without_manifest_never_ready(self):
        report = inspect(observer=observation)
        self.assertEqual(report["status"], "observed_only")
        self.assertFalse(report["can_login"])
        self.assertFalse(report["protocol_compatible"])
        self.assertNotIn("manifests", report)

    def test_manifest_transport_cannot_unlock_login(self):
        def fetch(url, *, limit):
            payload = b"dummy-data" if "DataPackage." in url else b"dummy-main"
            crc = (zlib.crc32(payload) & 0xffffffff).to_bytes(4, "little").hex()
            return crc.encode() if url.endswith(".hash") else payload
        report = inspect(observer=observation, with_manifests=True,
                         manifest_fetcher=fetch)
        self.assertTrue(report["manifest_transport_checked"])
        self.assertFalse(report["catalog_parsed"])
        self.assertFalse(report["can_login"])
        self.assertEqual(len(report["catalog_identity"]), 64)
        self.assertNotIn("dummy-data", json.dumps(report))

    def test_startup_readiness_rejects_stale_manifests(self):
        obs = observation()
        def receipt(name, payload):
            crc = (zlib.crc32(payload) & 0xffffffff).to_bytes(4, "little").hex()
            return verify_manifest_transport(obs, name, crc.encode(), payload)
        pair = combine_manifest_receipts(
            obs, (receipt("DataPackage", b"data"), receipt("MainPackage", b"main")))
        self.assertTrue(review_startup(obs, pair).manifests_transport_checked)
        self.assertFalse(review_startup(obs, pair).can_login)
        older = ObservedVersions(obs.exe_version, "1.4.21",
                                 obs.package_versions, obs.checked_at_utc)
        with self.assertRaises(OfficialVersionError):
            review_startup(older, pair)

    def test_cli_requires_explicit_online_flag(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main([])
        self.assertEqual(caught.exception.code, 2)

    def test_cli_prints_only_approved_observation(self):
        output = StringIO()
        with patch("lala_core.resource_inspector.observe_official_versions",
                   return_value=observation()), redirect_stdout(output):
            self.assertEqual(main(["--online", "--json"]), 0)
        result = json.loads(output.getvalue())
        self.assertFalse(result["can_login"])
        self.assertEqual(result["exe_version"], "1.4.0")


class StartupCliTests(unittest.TestCase):
    def test_startup_runs_one_combined_check_with_bounded_timeout(self):
        obs = observation()
        import zlib
        from lala_core import resource_inspector
        from lala_core.manifest_transport import MAX_MANIFEST_BYTES
        from lala_core.official_versions import VERSION_MAP_URL
        calls = []

        def fake_fetch(url, *, limit=16384, timeout=10):
            calls.append((url, limit, timeout))
            if url == VERSION_MAP_URL:
                return b'[{"ExeVer":"1.4.0","DataVer":"1.4.22"}]'
            if url.endswith(".version"):
                return (b"1280_2026_10_29_12_30_20_40" if "DataPackage." in url
                        else b"1280_2026_10_29_12_30_20_41")
            data = b"fake-Data" if "DataPackage." in url else b"fake-Main"
            if url.endswith(".hash"):
                return (zlib.crc32(data) & 0xffffffff).to_bytes(4, "little").hex().encode()
            return data

        result = StringIO()
        with patch.object(resource_inspector, "fetch_public_bytes", side_effect=fake_fetch):
            with redirect_stdout(result):
                self.assertEqual(main(["--online", "--manifests", "--json",
                                       "--timeout", "3"]), 0)
        output = json.loads(result.getvalue())
        self.assertEqual(len(calls), 7)
        self.assertTrue(all(timeout == 3.0 for _url, _limit, timeout in calls))
        self.assertEqual(sum(limit == MAX_MANIFEST_BYTES for _url, limit, _t in calls), 2)
        self.assertTrue(output["manifest_transport_checked"])
        self.assertFalse(output["can_login"])

    def test_timeout_rejects_zero_and_negative(self):
        for value in ("0", "-5", "61"):
            with self.subTest(value=value):
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as failed:
                    main(["--online", "--timeout", value])
                self.assertEqual(failed.exception.code, 2)
