import unittest
from unittest.mock import Mock
from lala_core.official_versions import (
    OfficialVersionError, VERSION_MAP_URL, fetch_public_bytes,
    observe_official_versions, package_url, parse_package_revision,
    parse_version_map, require_public_url,
)


class Response:
    def __init__(self, url, data, *, status=200, declared=None):
        self.url, self.data, self.status = url, data, status
        self.headers = {} if declared is None else {"Content-Length": declared}
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def geturl(self):
        return self.url
    def read(self, n):
        return self.data[:n]


class VersionsTests(unittest.TestCase):
    def test_parses_current_highest_exe_without_hardcoding_1275(self):
        body = b'[{"ExeVer":"1.3.0","DataVer":"1.3.21"},' \
               b'{"ExeVer":"1.4.0","DataVer":"1.4.22"},]'
        self.assertEqual(parse_version_map(body), ("1.4.0", "1.4.22"))

    def test_reject_duplicate_invalid_and_html(self):
        for body in (
            b'<html>error</html>',
            b'[]',
            b'[{"ExeVer":"1.2.3","DataVer":"../../foo"}]',
            b'[{"ExeVer":"1.2.3","DataVer":"1.2.3"},'
            b'{"ExeVer":"1.2.3","DataVer":"1.2.4"}]',
        ):
            with self.subTest(body=body), self.assertRaises(OfficialVersionError):
                parse_version_map(body)

    def test_legacy_observed_utf16_gzip_and_final_trailing_comma(self):
        import gzip
        fixture = (
            b'[\r\n'
            b'{"ExeVer":"1.1.3","DataVer":"1.3.21"},\r\n'
            b'{"ExeVer":"1.1.4","DataVer":"1.3.21"},\r\n'
            b'{"ExeVer":"1.2.0","DataVer":"1.3.21"},\r\n'
            b'{"ExeVer":"1.3.0","DataVer":"1.3.21"},\r\n'
            b']'
        )
        self.assertEqual(len(fixture), 164)
        for data in (fixture, fixture.decode("utf-8").encode("utf-16"),
                     gzip.compress(fixture)):
            with self.subTest(size=len(data)):
                self.assertEqual(parse_version_map(data), ("1.3.0", "1.3.21"))

    def test_bad_rows_report_field_and_index_without_echoing_server_value(self):
        cases = [
            (b'[{"ExeVer":"1.3.0"}]', "DataVer 缺少"),
            (b'[{"ExeVer":"1.3.0","DataVer":12}]', "DataVer 不是文字"),
            (b'[{"ExeVer":"1.3.0","DataVer":"PRIVATE_TOKEN"}]',
             "DataVer 格式不符"),
            (b'[false]', "不是 JSON 物件"),
        ]
        for data, message in cases:
            with self.subTest(data=data), self.assertRaises(OfficialVersionError) as ctx:
                parse_version_map(data)
            self.assertIn("第 1 筆", str(ctx.exception))
            self.assertIn(message, str(ctx.exception))
            self.assertNotIn("PRIVATE_TOKEN", str(ctx.exception))

    def test_html_and_oversized_gzip_fail_closed(self):
        import gzip
        with self.assertRaisesRegex(OfficialVersionError, "HTML"):
            parse_version_map(b"<html><body>bad CDN response</body></html>")
        with self.assertRaises(OfficialVersionError):
            parse_version_map(gzip.compress(b"x" * (16384 + 1)))

    def test_full_package_revision_not_integer(self):
        revision = "1275_2026_10_21_18_29_38_49"
        self.assertEqual(parse_package_revision(revision.encode()), revision)
        for value in (b"1275", b"../secret", b"12345_bad", b""):
            with self.assertRaises(OfficialVersionError):
                parse_package_revision(value)

    def test_official_https_source_allowlist(self):
        allowed = package_url("1.3.21", "DataPackage", "version")
        self.assertEqual(require_public_url(allowed), allowed)
        for url in (
            "https://example.com/WLN/TW/ResourcePath_PC.dat",
            "http://wlreftp.chinesegamer.net/WLN/TW/ResourcePath_PC.dat",
            "https://wlreftp.chinesegamer.net.evil.test/WLN/TW/ResourcePath_PC.dat",
            "https://wlreftp.chinesegamer.net/WLN/TW/../secret",
            VERSION_MAP_URL + "?redirect=1",
            VERSION_MAP_URL + "?token=123",
            VERSION_MAP_URL + "?123&foo=1",
            "https://wlreftp.chinesegamer.net:8443/WLN/TW/ResourcePath_PC.dat",
        ):
            with self.subTest(url=url), self.assertRaises(OfficialVersionError):
                require_public_url(url)

    def test_numeric_cache_buster_only_on_resource_map(self):
        self.assertEqual(require_public_url(VERSION_MAP_URL + "?46317.9367265972"),
                         VERSION_MAP_URL + "?46317.9367265972")
        self.assertEqual(require_public_url(VERSION_MAP_URL + "?1234567890"),
                         VERSION_MAP_URL + "?1234567890")
        with self.assertRaises(OfficialVersionError):
            require_public_url(package_url("1.3.21", "MainPackage", "version") + "?123")

    def test_malformed_canonical_map_retries_once_without_guessing(self):
        from unittest.mock import patch
        from lala_core import official_versions
        urls = []
        def fetched(url):
            urls.append(url)
            if url == VERSION_MAP_URL:
                return b'[{"ExeVer":"1.3.0","DataVer":null}]'
            if url.startswith(VERSION_MAP_URL + "?"):
                return b'[{"ExeVer":"1.3.0","DataVer":"1.3.21"}]'
            return b'1275_2026_10_21_18_27_33_84'
        with patch.object(official_versions.time, "time_ns", return_value=1234567890):
            observed = observe_official_versions(fetcher=fetched)
        self.assertEqual(observed.data_version, "1.3.21")
        self.assertEqual(urls[:2], [VERSION_MAP_URL, VERSION_MAP_URL + "?1234567890"])
        self.assertEqual(len(urls), 4)
        self.assertFalse(observed.protocol_compatible)

    def test_twice_invalid_preserves_failsafe_diagnostic(self):
        from unittest.mock import patch
        from lala_core import official_versions
        urls = []
        def fetched(url):
            urls.append(url)
            return b'[{"ExeVer":"1.3.0","DataVer":"REDACTED_SECRET"}]'
        with patch.object(official_versions.time, "time_ns", return_value=2222):
            with self.assertRaises(OfficialVersionError) as context:
                observe_official_versions(fetcher=fetched)
        self.assertEqual(urls, [VERSION_MAP_URL, VERSION_MAP_URL + "?2222"])
        self.assertIn("第 1 筆 DataVer 格式不符", str(context.exception))
        self.assertNotIn("REDACTED_SECRET", str(context.exception))

    def test_bounded_https_response(self):
        opener = Mock(side_effect=lambda req, timeout: Response(
            req.full_url, b'[]', declared="2"))
        self.assertEqual(fetch_public_bytes(VERSION_MAP_URL, opener=opener), b'[]')
        bad = Mock(side_effect=lambda req, timeout: Response(
            "https://evil.test/x", b'[]'))
        with self.assertRaises(OfficialVersionError):
            fetch_public_bytes(VERSION_MAP_URL, opener=bad)
        long = Mock(side_effect=lambda req, timeout: Response(req.full_url, b'abc', declared="200"))
        with self.assertRaises(OfficialVersionError):
            fetch_public_bytes(VERSION_MAP_URL, limit=5, opener=long)

    def test_exactly_three_requests_and_protocol_always_closed(self):
        urls = []
        def fetch(url):
            urls.append(url)
            if url == VERSION_MAP_URL:
                return b'[{"ExeVer":"1.4.0","DataVer":"1.4.22"}]'
            return b'1280_2026_10_29_12_30_20_40'
        observation = observe_official_versions(fetcher=fetch,
                                                checked_at_utc="2026-10-29T00:00:00+00:00")
        self.assertEqual(len(urls), 3)
        self.assertEqual(observation.exe_version, "1.4.0")
        self.assertEqual(observation.data_version, "1.4.22")
        self.assertEqual(observation.package_version("MainPackage"),
                         "1280_2026_10_29_12_30_20_40")
        self.assertFalse(observation.protocol_compatible)

    def test_incomplete_sources_do_not_fallback(self):
        def fetch(url):
            if url == VERSION_MAP_URL:
                return b'[{"ExeVer":"1.3.0","DataVer":"1.3.21"}]'
            return b'not a revision'
        with self.assertRaises(OfficialVersionError):
            observe_official_versions(fetcher=fetch)
