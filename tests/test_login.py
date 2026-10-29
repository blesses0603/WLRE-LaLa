"""登入入口與假 Adapter 測試：絕對不傳真實帳密／遊戲封包。"""
import unittest
from unittest.mock import Mock

from lala_core.login import (
    LoginCoordinator, LoginError, VerifiedLoginOutcome, validate_credentials,
)
from lala_core.session import SessionStore


class FakeApprovedAdapter:
    protocol_verified = True
    endpoint_verified = True
    def __init__(self):
        self.calls = []
    def authenticate(self, *, endpoint, account, password):
        self.calls.append((endpoint, account, password))
        return VerifiedLoginOutcome(True, (777, 888), True, True)


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
        self.assertEqual(login.view().role_ids, (777, 888))
        self.assertTrue(login.session.view().connected)
        self.assertTrue(login.session.view().resource_verified)
        self.assertFalse(login.choose_role(role_id=777))
        self.assertNotIn("secret", str(login.view()))

    def test_result_cannot_cross_disconnect_or_new_attempt(self):
        adapter = FakeApprovedAdapter()
        login = LoginCoordinator(adapter=adapter)
        gen = login.begin(line_id=101, account="demo", password="secret",
                          resources_verified=True)
        login.cancel()
        self.assertFalse(login.complete(gen, VerifiedLoginOutcome(True, (777,),
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
