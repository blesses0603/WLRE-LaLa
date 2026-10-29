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
