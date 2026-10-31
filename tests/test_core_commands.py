import unittest
from lala_core.commands import CommandGate, Command, PermissionDenied
from lala_core.operations import OperationState
from lala_core.session import SessionStore


class FakeAdapter:
    def __init__(self):
        self.sent = []
        self.fail = False
    def supports(self, capability):
        return capability == "reviewed"
    def send(self, command):
        self.sent.append(command)
        if self.fail:
            raise OSError("timeout with unknown send outcome")


class GateTests(unittest.TestCase):
    def test_closed_by_default(self):
        store = SessionStore()
        gate = CommandGate(store)
        with self.assertRaises(PermissionDenied):
            gate.submit(Command("battle", "reviewed"), user_confirmed=True)
        store.start(authenticated=True, resources_verified=True)
        with self.assertRaises(PermissionDenied):
            gate.submit(Command("battle", "reviewed"), user_confirmed=True)

    def test_requires_confirmation_and_adapter(self):
        store = SessionStore()
        generation = store.start(authenticated=True, resources_verified=True)
        adapter = FakeAdapter()
        gate = CommandGate(store, adapter)
        with self.assertRaises(PermissionDenied):
            gate.submit(Command("battle", "reviewed"), user_confirmed=True)
        # Only a mock audited adapter may publish this synthetic baseline.
        self.assertTrue(store.apply(generation=generation, revision=0,
                                    data={"role_id": 123}, authoritative=True))
        with self.assertRaises(PermissionDenied):
            gate.submit(Command("battle", "reviewed"))
        with self.assertRaises(PermissionDenied):
            gate.submit(Command("trade", "unknown"), user_confirmed=True)
        self.assertTrue(gate.submit(Command("battle", "reviewed"), user_confirmed=True))
        with self.assertRaises(PermissionDenied):
            gate.submit(Command("battle", "reviewed"), user_confirmed=True)
        self.assertEqual(len(adapter.sent), 1)
        self.assertFalse(gate.acknowledge("battle", authoritative=False, success=True))
        self.assertEqual(gate.status("battle"), OperationState.UNCERTAIN)
        self.assertFalse(gate.reset_after_sync("battle", authoritative=False))
        self.assertTrue(gate.reset_after_sync("battle", authoritative=True))
        self.assertEqual(gate.status("battle"), OperationState.IDLE)

    def test_timeout_never_retries(self):
        store = SessionStore()
        generation = store.start(authenticated=True, resources_verified=True)
        self.assertTrue(store.apply(generation=generation, revision=0,
                                    data={"role_id": 123}, authoritative=True))
        adapter = FakeAdapter()
        adapter.fail = True
        gate = CommandGate(store, adapter)
        with self.assertRaises(OSError):
            gate.submit(Command("craft", "reviewed"), user_confirmed=True)
        with self.assertRaises(PermissionDenied):
            gate.submit(Command("craft", "reviewed"), user_confirmed=True)
        self.assertEqual(len(adapter.sent), 1)
