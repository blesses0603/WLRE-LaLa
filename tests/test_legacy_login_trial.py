"""Simulated legacy servers only, no actual login, no real accounts."""
import socket
import struct
import unittest

from lala_core.login import LoginError
from lala_core.legacy_login_trial import LegacyLoginTrial, MAX_ROLE_PACKETS
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


def world_player(role_id=654321, name="測試角色", *, scene=120, x=30, y=40):
    name_bytes = name.encode("utf-16le")
    return (
        struct.pack("<IBHHH", role_id, 1, scene, x, y)
        + b"\0" * (3 + 8 + 2)
        + b"\x00"  # no equipment
        + bytes((len(name_bytes),)) + name_bytes
        + b"\0" * 8  # private namecard fields
        + b"\x00"  # empty private signature
        + struct.pack("<H", 0)  # title
    )


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
             frame(63, 1, role(2) + role(1)),
             frame(1, 11) + frame(3, 1, world_player())],
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
        self.assertTrue(selected.initial_data_complete)
        self.assertEqual(selected.role_id, 654321)
        self.assertEqual(selected.character_name, "測試角色")
        self.assertEqual((selected.scene, selected.x, selected.y), (120, 30, 40))
        self.assertFalse(selected.ongoing_connection)
        self.assertFalse(selected.official_identity_verified)
        self.assertTrue(sockets[1].closed)
        self.assertTrue(selected.init_acks_sent)
        self.assertEqual(len(sockets[1].sent), 4)
        outbound = [bytes(x ^ OLD_TX_XOR for x in raw)[4:]
                    for raw in sockets[1].sent[1:]]
        self.assertEqual(outbound, [
            b"\x3f\x02\x01", b"\x0c\x01", b"\x03\x02"])

    def test_s1_11_alone_is_not_character_sync(self):
        a, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(1, 11)],
        )
        a.authenticate(line_id=101, account="fake", password="fake", consent=True)
        with self.assertRaises(LoginError):
            a.select_role(1)
        self.assertTrue(sockets[1].closed)

    def test_s3_1_without_initial_data_complete_is_not_success(self):
        a, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(3, 1, world_player())],
        )
        a.authenticate(line_id=101, account="fake", password="fake", consent=True)
        with self.assertRaises(LoginError):
            a.select_role(1)
        self.assertTrue(sockets[1].closed)

    def test_invalid_s3_1_is_rejected_even_if_s1_11_is_present(self):
        a, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(3, 1, world_player()[:-3]) + frame(1, 11)],
        )
        a.authenticate(line_id=101, account="fake", password="fake", consent=True)
        with self.assertRaisesRegex(LoginError, "S3-1"):
            a.select_role(1)
        self.assertTrue(sockets[1].closed)

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


    def test_role_packet_cap_reports_known_markers_without_silent_success(self):
        # The server-like fake floods unrelated events after a valid S3-1.
        # Missing S1-11 still means no authoritative character sync.
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(3, 1, world_player()) + frame(9, 9) * (MAX_ROLE_PACKETS + 1)],
        )
        trial.authenticate(line_id=101, account="synthetic_user",
                           password="synthetic_pass", consent=True)
        with self.assertRaises(LoginError) as error:
            trial.select_role(1)
        message = str(error.exception)
        self.assertIn(f"選角試驗超過 {MAX_ROLE_PACKETS} 個封包", message)
        self.assertIn("S3-1：已收到", message)
        self.assertIn("S1-11：未收到", message)
        self.assertNotIn("synthetic_user", message)
        self.assertNotIn("synthetic_pass", message)
        self.assertTrue(sockets[1].closed)
        self.assertEqual(trial._verified_slots, ())

    def test_role_cap_without_world_or_ready_still_closes(self):
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(8, 8) * (MAX_ROLE_PACKETS + 1)],
        )
        trial.authenticate(line_id=101, account="fake",
                           password="fake", consent=True)
        with self.assertRaises(LoginError) as error:
            trial.select_role(1)
        self.assertIn("S3-1：未收到", str(error.exception))
        self.assertIn("S1-11：未收到", str(error.exception))
        self.assertTrue(sockets[1].closed)

    def test_verification_packet_limit_identifies_stage(self):
        trial, sockets, opened = self.setup_adapter(
            [frame(8, 8) * 513], [])
        with self.assertRaises(LoginError) as error:
            trial.authenticate(line_id=101, account="fake",
                               password="fake", consent=True)
        self.assertIn("帳號驗證試驗超過 512 個封包", str(error.exception))
        self.assertEqual(len(opened), 1)
        self.assertTrue(sockets[0].closed)

    def test_role_init_after_more_than_512_old_style_events(self):
        # Original capture contains 1,848 S2C packets across its session.
        # A packet burst above 512 must not be a false init failure.
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(9, 9) * 513 + frame(3, 1, world_player())
             + frame(1, 11)],
        )
        trial.authenticate(line_id=101, account="fake",
                           password="fake", consent=True)
        result = trial.select_role(1)
        self.assertTrue(result.initial_data_complete)
        self.assertTrue(result.init_acks_sent)
        self.assertTrue(sockets[1].closed)

    def test_partial_formal_stream_frame_continues_after_select_role(self):
        world = frame(3, 1, world_player())
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1))
             + world[:2],
             world[2:] + frame(1, 11)],
        )
        trial.authenticate(line_id=101, account="fake",
                           password="fake", consent=True)
        result = trial.select_role(1)
        self.assertTrue(result.initial_data_complete)
        self.assertEqual(result.role_id, 654321)
        self.assertTrue(result.init_acks_sent)

    def test_preselection_coalesced_role_info_is_not_trusted(self):
        # Formally observed BEFORE C63-2: cannot prove role selected.
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1))
             + frame(3, 1, world_player()) + frame(1, 11)],
        )
        trial.authenticate(line_id=101, account="fake",
                           password="fake", consent=True)
        with self.assertRaises(LoginError):
            trial.select_role(1)
        self.assertEqual(len(sockets[1].sent), 2)
        self.assertTrue(sockets[1].closed)

    def test_nonempty_heartbeat_is_rejected_without_reply(self):
        trial, sockets, opened = self.setup_adapter(
            [frame(1, 23, b"\x01") + frame(63, 7, b"\0\0")], [])
        with self.assertRaisesRegex(LoginError, "S1-23"):
            trial.authenticate(line_id=101, account="fake",
                               password="fake", consent=True)
        self.assertEqual(len(sockets[0].sent), 1)
        self.assertEqual(len(opened), 1)
        self.assertTrue(sockets[0].closed)

    def test_nonempty_s1_11_rejected_without_init_ack(self):
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(3, 1, world_player()) + frame(1, 11, b"\x01")],
        )
        trial.authenticate(line_id=101, account="fake",
                           password="fake", consent=True)
        with self.assertRaisesRegex(LoginError, "S1-11"):
            trial.select_role(1)
        self.assertEqual(len(sockets[1].sent), 2)  # login, select only
        self.assertTrue(sockets[1].closed)

    def test_opt_in_readonly_observer_keeps_socket_until_bounded_expiry(self):
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(3, 1, world_player()) + frame(1, 11)],
        )
        trial.authenticate(line_id=101, account="fake", password="fake",
                           consent=True)
        selected = trial.select_role(1, keep_open=True)
        self.assertTrue(selected.ongoing_connection)
        self.assertFalse(selected.official_identity_verified)
        self.assertFalse(trial._stopped.is_set())
        self.assertFalse(sockets[1].closed)
        # Only the legacy heartbeat is legal during observation.
        sockets[1].incoming.extend([frame(9, 9) + frame(1, 23)])
        now = [0.]
        def clock():
            now[0] += .4
            return now[0]
        trial._clock = clock
        summary = trial.observe_readonly(duration=1)
        self.assertEqual(summary.packets_seen, 1)
        self.assertEqual(summary.heartbeat_replies, 1)
        self.assertFalse(summary.official_identity_verified)
        self.assertTrue(sockets[1].closed)
        outbound = [bytes(x ^ OLD_TX_XOR for x in raw)[4:]
                    for raw in sockets[1].sent]
        self.assertEqual(outbound[-1], b"\x3f\x05")
        self.assertNotIn(b"\x06\x01", outbound)  # never walk
        with self.assertRaises(LoginError):
            trial.observe_readonly(duration=1)

    def test_readonly_requires_explicit_selection_and_valid_duration(self):
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(3, 1, world_player()) + frame(1, 11)],
        )
        for duration in (0, 121, 1.0, True, -1):
            with self.assertRaises(LoginError):
                trial.observe_readonly(duration=duration)
        trial.authenticate(line_id=101, account="fake", password="fake",
                           consent=True)
        with self.assertRaises(LoginError):
            trial.observe_readonly(duration=1)
        trial.select_role(1)  # default keeps the historical one-shot close
        self.assertTrue(sockets[1].closed)
        with self.assertRaises(LoginError):
            trial.observe_readonly(duration=1)

    def test_readonly_disconnection_prevents_future_heartbeats(self):
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(3, 1, world_player()) + frame(1, 11)],
        )
        trial.authenticate(line_id=101, account="fake", password="fake",
                           consent=True)
        trial.select_role(1, keep_open=True)
        before = len(sockets[1].sent)
        trial.close()
        sockets[1].incoming.append(frame(1, 23))
        with self.assertRaises(LoginError):
            trial.observe_readonly(duration=1)
        self.assertEqual(len(sockets[1].sent), before)
        self.assertTrue(sockets[1].closed)

    def test_coalesced_packet_after_init_is_retained_for_observation(self):
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(3, 1, world_player()) + frame(1, 11)
             + frame(9, 9) + frame(1, 23)],
        )
        trial.authenticate(line_id=101, account="fake", password="fake",
                           consent=True)
        trial.select_role(1, keep_open=True)
        ticks = [0.]
        def clock():
            ticks[0] += .4
            return ticks[0]
        trial._clock = clock
        result = trial.observe_readonly(duration=1)
        self.assertEqual(result.packets_seen, 1)
        self.assertEqual(result.heartbeat_replies, 1)
        self.assertTrue(sockets[1].closed)

    def test_readonly_packet_distribution_excludes_heartbeat_and_payload(self):
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(3, 1, world_player()) + frame(1, 11)],
        )
        trial.authenticate(line_id=101, account="fake",
                           password="fake", consent=True)
        trial.select_role(1, keep_open=True)
        sockets[1].incoming.extend([
            frame(9, 9, b"payload-should-never-leak")
            + frame(9, 9) + frame(7, 1) + frame(9, 1)
            + frame(1, 23) + frame(7, 1),
        ])
        ticks = [0.]
        def clock():
            ticks[0] += .2
            return ticks[0]
        trial._clock = clock
        result = trial.observe_readonly(duration=1)
        self.assertEqual(result.packets_seen, 5)
        self.assertEqual(result.heartbeat_replies, 1)
        self.assertEqual(result.distinct_packet_types, 3)
        self.assertEqual(result.top_packet_types, (
            (7, 1, 2), (9, 9, 2), (9, 1, 1),
        ))
        self.assertNotIn("payload-should-never-leak", repr(result))
        self.assertTrue(sockets[1].closed)

    def test_readonly_packet_distribution_is_limited_to_eight_types(self):
        trial, sockets, _ = self.setup_adapter(
            [frame(63, 7, b"\0\0")],
            [frame(63, 7, b"\0\x02") + frame(63, 1, role(1)),
             frame(3, 1, world_player()) + frame(1, 11)],
        )
        trial.authenticate(line_id=101, account="fake",
                           password="fake", consent=True)
        trial.select_role(1, keep_open=True)
        sockets[1].incoming.append(
            b"".join(frame(main, 1) for main in range(10, 22))
        )
        ticks = [0.]
        def clock():
            ticks[0] += .2
            return ticks[0]
        trial._clock = clock
        result = trial.observe_readonly(duration=1)
        self.assertEqual(result.packets_seen, 12)
        self.assertEqual(result.heartbeat_replies, 0)
        self.assertEqual(result.distinct_packet_types, 12)
        self.assertEqual(
            result.top_packet_types,
            tuple((main, 1, 1) for main in range(10, 18))
        )
