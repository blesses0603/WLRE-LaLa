"""登入入口與假 Adapter 測試：絕對不傳真實帳密／遊戲封包。"""
import unittest
from unittest.mock import Mock

from lala_core.login import (
    LoginCoordinator, LoginError, VerifiedLoginOutcome, VerifiedRoleSelection,
    validate_credentials,
)
from lala_core.session import SessionStore
from lala_core.world_sync import VerifiedPosition, WorldPhase


class FakeApprovedAdapter:
    protocol_verified = True
    endpoint_verified = True
    def __init__(self):
        self.calls = []
    def authenticate(self, *, endpoint, account, password):
        self.calls.append((endpoint, account, password))
        return VerifiedLoginOutcome(True, (1, 2), True, True)


class LoginServiceTests(unittest.TestCase):
    def test_default_never_calls_network_or_authenticates(self):
        login = LoginCoordinator()
        for bad in (False, True):
            with self.subTest(resources=bad), self.assertRaises(LoginError):
                login.begin(line_id=101, account="test", password="demo",
                            resources_verified=bad)
            self.assertFalse(login.view().authenticated)
            self.assertFalse(login.session.view().connected)
        self.assertNotIn("demo", repr(login.view()))
        self.assertNotIn("test", repr(login.view()))

    def test_verified_adapter_is_needed_to_perform_auth(self):
        session = SessionStore()
        adapter = FakeApprovedAdapter()
        login = LoginCoordinator(session=session, adapter=adapter)
        generation = login.begin(line_id=101, account="demo", password="secret",
                                 resources_verified=True)
        self.assertEqual(login.view().phase, "authenticating")
        self.assertEqual(adapter.calls, [])
        result = login.authenticate(generation=generation, account="demo",
                                    password="secret")
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(adapter.calls[0][0], ("34.81.10.22", 16988))
        self.assertTrue(login.complete(generation, result))
        self.assertEqual(login.view().phase, "role_selection")
        self.assertEqual(login.view().role_slots, (1, 2))
        self.assertTrue(login.session.view().connected)
        self.assertTrue(login.session.view().resource_verified)
        self.assertFalse(login.choose_role(role_id=1))
        self.assertNotIn("secret", str(login.view()))

    def test_result_cannot_cross_disconnect_or_new_attempt(self):
        adapter = FakeApprovedAdapter()
        login = LoginCoordinator(adapter=adapter)
        gen = login.begin(line_id=101, account="demo", password="secret",
                          resources_verified=True)
        login.cancel()
        self.assertFalse(login.complete(gen, VerifiedLoginOutcome(True, (1,),
                                                                   True, True)))
        self.assertFalse(login.session.view().connected)
        with self.assertRaises(LoginError):
            login.authenticate(generation=gen, account="demo", password="secret")

    def test_fake_or_unverified_server_reply_never_marks_login_success(self):
        for result in (
            None, "success",
            VerifiedLoginOutcome(True, (1,), False, True),
            VerifiedLoginOutcome(True, (1,), True, False),
            VerifiedLoginOutcome(False, (1,), True, True),
            VerifiedLoginOutcome(True, (1, 1), True, True),
            VerifiedLoginOutcome(True, (1, 2, 3), True, True),
        ):
            with self.subTest(result=result):
                login = LoginCoordinator(adapter=FakeApprovedAdapter())
                gen = login.begin(line_id=101, account="u", password="p",
                                  resources_verified=True)
                self.assertFalse(login.complete(gen, result))
                self.assertFalse(login.session.view().connected)
                self.assertEqual(login.view().phase, "rejected")

    def test_invalid_credentials_and_endpoint_are_blocked(self):
        for account, pwd in (("", "p"), ("a", ""), ("あ", "p"),
                             ("a", "has space"), ("x"*256, "p"),
                             ("a", "\n")):
            with self.subTest(account=account, password_length=len(pwd)):
                with self.assertRaises(LoginError):
                    validate_credentials(account, pwd)
        with self.assertRaises(LoginError):
            LoginCoordinator(adapter=FakeApprovedAdapter()).begin(
                line_id=9999, account="u", password="p", resources_verified=True)

    def test_login_error_does_not_echo_secret(self):
        class UnsafeAdapter:
            protocol_verified = False
            endpoint_verified = True
            def authenticate(self, **kwargs):
                raise AssertionError("must not be called")
        c = LoginCoordinator(adapter=UnsafeAdapter())
        with self.assertRaises(LoginError) as err:
            c.begin(line_id=101, account="myuser", password="mysecret",
                    resources_verified=True)
        self.assertNotIn("myuser", str(err.exception))
        self.assertNotIn("mysecret", str(err.exception))
        self.assertFalse(c.session.view().connected)

    def test_verified_world_sync_connected_to_login_lifecycle(self):
        adapter = FakeApprovedAdapter()
        login = LoginCoordinator(adapter=adapter)
        generation = login.begin(line_id=101, account="demo", password="secret",
                                 resources_verified=True)
        result = login.authenticate(generation=generation, account="demo",
                                    password="secret")
        self.assertTrue(login.complete(generation, result))
        denied = VerifiedRoleSelection(1, 123, True, True, False)
        self.assertFalse(login.accept_verified_role(
            generation=generation, selected=denied))
        self.assertEqual(login.view().phase, "role_selection")
        accepted = VerifiedRoleSelection(1, 123, True, True, True)
        self.assertTrue(login.accept_verified_role(
            generation=generation, selected=accepted))
        self.assertEqual(login.view().phase, "world_initializing")
        self.assertFalse(login.world_sync.view().authoritative)
        epoch = login.session.view().generation
        initial = VerifiedPosition(epoch, 0, 123, 10, 20, 30, True)
        self.assertTrue(login.accept_world_snapshot(
            generation=generation, update=initial))
        self.assertEqual(login.view().phase, "world_ready")
        self.assertTrue(login.world_sync.view().authoritative)
        update = VerifiedPosition(epoch, 1, 123, 10, 21, 30, True)
        self.assertTrue(login.accept_world_position(
            generation=generation, update=update))
        self.assertEqual(login.session.view().server_state["x"], 21)
        self.assertNotIn("secret", str(login.world_sync.view()))
        login.cancel()
        self.assertFalse(login.world_sync.view().authoritative)
        self.assertFalse(login.session.view().connected)

    def test_gap_and_old_generation_events_cannot_resurrect_world(self):
        login = LoginCoordinator(adapter=FakeApprovedAdapter())
        gen = login.begin(line_id=101, account="fake", password="fake",
                          resources_verified=True)
        self.assertTrue(login.complete(gen, VerifiedLoginOutcome(
            True, (1,), True, True)))
        self.assertTrue(login.accept_verified_role(
            generation=gen,
            selected=VerifiedRoleSelection(1, 123, True, True, True)))
        epoch = login.session.view().generation
        self.assertTrue(login.accept_world_snapshot(
            generation=gen,
            update=VerifiedPosition(epoch, 0, 123, 1, 2, 3, True)))
        self.assertFalse(login.accept_world_position(
            generation=gen,
            update=VerifiedPosition(epoch, 2, 123, 1, 2, 4, True)))
        self.assertEqual(login.view().phase, "resync_required")
        self.assertFalse(login.session.view().connected)
        self.assertFalse(login.accept_world_position(
            generation=gen,
            update=VerifiedPosition(epoch, 1, 123, 1, 2, 3, True)))

    def test_legacy_trial_cannot_escalate_to_verified_world(self):
        login = LoginCoordinator()
        self.assertFalse(login.accept_verified_role(
            generation=login.view().generation,
            selected=VerifiedRoleSelection(1, 123, False, False, False)))
        self.assertEqual(login.world_sync.view().phase,
                         WorldPhase.DISCONNECTED)
        self.assertFalse(login.session.view().connected)

    def test_disconnect_revokes_queued_world_result(self):
        login = LoginCoordinator(adapter=FakeApprovedAdapter())
        gen = login.begin(line_id=101, account="fake", password="fake",
                          resources_verified=True)
        self.assertTrue(login.complete(gen, VerifiedLoginOutcome(
            True, (1,), True, True)))
        self.assertTrue(login.accept_verified_role(
            generation=gen,
            selected=VerifiedRoleSelection(1, 123, True, True, True)))
        old_epoch = login.session.view().generation
        login.cancel()
        self.assertFalse(login.accept_world_snapshot(
            generation=gen,
            update=VerifiedPosition(old_epoch, 0, 123, 1, 2, 3, True)))
        self.assertFalse(login.session.view().server_state)

