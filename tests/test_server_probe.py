"""所有測試以假 socket 驗證，絕不可在 CI 連遊戲正式伺服器。"""
from contextlib import contextmanager
from io import StringIO
from unittest.mock import patch
from contextlib import redirect_stderr
import socket
import unittest

from lala_core.server_probe import LINE_SNAPSHOT, main, probe_line


class MockConnection:
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def send(self, *_):
        raise AssertionError("TCP 探測禁止送出任何位元組")
    def recv(self, *_):
        raise AssertionError("TCP 探測禁止讀取封包")


class ServerProbeTests(unittest.TestCase):
    def test_one_time_socket_connect_close_without_credentials(self):
        calls = []
        def mock_connector(endpoint, *, timeout):
            calls.append((endpoint, timeout))
            return MockConnection()
        result = probe_line(101, timeout=2, connector=mock_connector,
                            clock=iter((10.0, 10.045)).__next__)
        self.assertEqual(calls, [(("34.81.10.22", 16988), 2)])
        self.assertEqual(result.status, "tcp_connected")
        self.assertTrue(result.tcp_reachable)
        self.assertEqual(result.elapsed_ms, 45)
        self.assertEqual(result.transmitted_bytes, 0)
        self.assertFalse(result.authenticated)
        self.assertFalse(result.protocol_compatible)

    def test_refused_timeout_and_other_error_fail_closed(self):
        for exception, status in (
            (ConnectionRefusedError(), "connection_refused"),
            (TimeoutError(), "timeout"),
            (OSError(), "network_error"),
        ):
            def refuse(endpoint, *, timeout):
                raise exception
            with self.subTest(status=status):
                result = probe_line(101, connector=refuse)
                self.assertEqual(result.status, status)
                self.assertFalse(result.tcp_reachable)

    def test_only_known_old_server_lines_allowed(self):
        self.assertEqual(len(LINE_SNAPSHOT), 7)
        for line in (0, 999, "101", True):
            with self.subTest(line=line), self.assertRaises(ValueError):
                probe_line(line, connector=lambda *_args, **_kwargs:
                           self.fail("Should not call connector"))
        with self.assertRaises(ValueError):
            probe_line(101, timeout=6)

    def test_cli_requires_explicit_user_permission(self):
        with patch("lala_core.server_probe.socket.create_connection") as dialer:
            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["--json"])
            self.assertEqual(error.exception.code, 2)
            dialer.assert_not_called()

    def test_connectivity_never_claims_login_even_when_tcp_connected(self):
        with patch("lala_core.server_probe.socket.create_connection",
                   return_value=MockConnection()):
            result = probe_line(102)
        self.assertEqual(result.line_id, 102)
        self.assertFalse(result.to_dict()["authenticated"])
        self.assertFalse(result.to_dict()["protocol_compatible"])
