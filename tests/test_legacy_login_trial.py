"""Simulated legacy servers only, no actual login, no real accounts."""
import socket
import struct
import unittest

from lala_core.login import LoginError
from lala_core.legacy_login_trial import LegacyLoginTrial
from lala_core.login_wire import OLD_TX_XOR
from lala_core.wire import ObservedPacket


def frame(main, sub, payload=b""):
    raw = b"\xc4\xc6" + struct.pack("<H", len(payload) + 2) + bytes((main, sub)) + payload
    return bytes(value ^ OLD_TX_XOR for value in raw)


def role(index):
    name = "test".encode("utf-16le")
    return (bytes((index, len(name))) + name
            + b"\0" * (1+1+4*4+8+4+1+1+4+4+1+1)
            + struct.pack("<H", 10) + b"\0"*8 + b"\0"
            + b"\0" * (4*4+2+4*2+4*2))


class FakeConnection:
    def __init__(self, incoming):
        self.incoming = list(incoming)
        self.sent = []
        self.closed = False

    def settimeout(self, timeout):
        pass

    def sendall(self, data):
        if self.closed:
            raise OSError("closed")
        self.sent.append(data)

    def recv(self, n):
        if self.incoming:
            return self.incoming.pop(0)
        raise socket.timeout()

    def shutdown(self, how):
        pass

    def close(self):
        self.closed = True


class LegacyLoginTrialTests(unittest.TestCase):
    def setup_adapter(self, verify, formal):
        sockets = [
            FakeConnection(verify),
            FakeConnection(formal),
        ]
        opened = []
        def connect(endpoint, *, timeout):
            opened.append(endpoint)
            return sockets[len(opened)-1]
        return LegacyLoginTrial(connector=connect, timeout=1), sockets, opened

    def test_two_connections_heartbeat_and_role_selection(self):
        a, sockets, opened = self.setup_adapter(
            [frame(1, 23) + frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02"),
             frame(63, 1, role(2) + role(1)), frame(1, 11)],
        )
        result = a.authenticate(line_id=101, account="fakeaccount",
                                password="fakepassword", consent=True)
        self.assertEqual(result.role_slots, (1, 2))
        self.assertFalse(result.official_identity_verified)
        self.assertFalse(result.current_protocol_certified)
        self.assertEqual(opened, [("34.81.10.22",16988)]*2)
        self.assertTrue(sockets[0].closed)
        self.assertFalse(sockets[1].closed)
        self.assertEqual(len(sockets[0].sent), 2)
        self.assertEqual(len(sockets[1].sent), 1)
        req = bytes(x ^ OLD_TX_XOR for x in sockets[0].sent[0])
        self.assertEqual(req[4:6], b"\x3f\x07")
        self.assertEqual(req[6], 0)
        heartbeat = bytes(x ^ OLD_TX_XOR for x in sockets[0].sent[1])
        self.assertEqual(heartbeat[4:6], b"\x3f\x05")
        selected = a.select_role(1)
        self.assertEqual(selected.role_slot, 1)
        self.assertTrue(selected.world_packet_observed)
        self.assertFalse(selected.official_identity_verified)
        self.assertTrue(sockets[1].closed)
        select = bytes(x ^ OLD_TX_XOR for x in sockets[1].sent[-1])
        self.assertEqual(select[4:], b"\x3f\x02\x01")

    def test_opt_in_required_before_any_dial(self):
        a, sock, endpoints = self.setup_adapter([], [])
        for consent in (False, None, 1):
            with self.subTest(consent=consent), self.assertRaises(LoginError):
                a.authenticate(line_id=101, account="a", password="p",
                               consent=consent)
        self.assertEqual(endpoints, [])

    def test_invalid_endpoints_never_connect(self):
        a, sock, endpoints = self.setup_adapter([], [])
        for line in (0, 999, "101"):
            with self.assertRaises(LoginError):
                a.authenticate(line_id=line, account="a", password="p", consent=True)
        self.assertEqual(endpoints, [])

    def test_server_refusal_and_no_roles_are_not_success(self):
        for verification, formal in (
            ([frame(63, 7, b"\x04\0")], []),
            ([frame(63, 7, b"\0\0")], [frame(63, 7, b"\x07\x02")]),
            ([frame(63, 7, b"\0\0")], [frame(63, 7, b"\0\x02")]),
        ):
            a, sockets, opened = self.setup_adapter(verification, formal)
            with self.subTest(verification=verification,
                              formal=formal), self.assertRaises(LoginError):
                a.authenticate(line_id=101, account="u", password="p", consent=True)
            self.assertTrue(sockets[0].closed)
            self.assertFalse(a._verified_slots)

    def test_wrong_format_never_marks_accepted(self):
        a, sockets, opened = self.setup_adapter([b"junk"], [])
        with self.assertRaises(LoginError):
            a.authenticate(line_id=101, account="u", password="p", consent=True)
        self.assertTrue(sockets[0].closed)

    def test_cancel_while_first_socket_is_connecting_sends_nothing(self):
        created = []
        trial = None
        def dial(endpoint, *, timeout):
            connection = FakeConnection([frame(63, 7, b"\0\0")])
            created.append(connection)
            trial.close()  # cancellation arrives during blocking TCP dial
            return connection
        trial = LegacyLoginTrial(connector=dial, timeout=1)
        with self.assertRaises(LoginError):
            trial.authenticate(line_id=101, account="fake", password="fake",
                               consent=True)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].sent, [])
        self.assertTrue(created[0].closed)

    def test_cancel_during_formal_dial_never_sends_kind_two(self):
        created = []
        trial = None
        def dial(endpoint, *, timeout):
            connection = FakeConnection([frame(63, 7, b"\0\0")])
            created.append(connection)
            if len(created) == 2:
                trial.close()  # interrupted before C63-7 kind 2
            return connection
        trial = LegacyLoginTrial(connector=dial, timeout=1)
        with self.assertRaises(LoginError):
            trial.authenticate(line_id=101, account="fake", password="fake",
                               consent=True)
        self.assertEqual(len(created), 2)
        self.assertEqual(len(created[0].sent), 1)
        self.assertEqual(created[1].sent, [])
        self.assertTrue(created[1].closed)

    def test_trial_is_single_use_even_when_accepted(self):
        trial, sockets, endpoints = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1))],
        )
        trial.authenticate(line_id=101, account="fake", password="fake",
                           consent=True)
        with self.assertRaises(LoginError):
            trial.authenticate(line_id=101, account="fake", password="fake",
                               consent=True)
        self.assertEqual(len(endpoints), 2)
        trial.close()

    def test_cancel_closes_formal_socket_and_disables_role_selection(self):
        a, sockets, opened = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1))],
        )
        result = a.authenticate(line_id=101, account="u", password="p", consent=True)
        self.assertEqual(result.role_slots, (1,))
        a.close()
        self.assertTrue(sockets[1].closed)
        with self.assertRaises(LoginError):
            a.select_role(1)
