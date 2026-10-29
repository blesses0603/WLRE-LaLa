import unittest
from lala_core.operations import OperationGuard, OperationState


class GuardTests(unittest.TestCase):
    def test_reject_without_ready_or_resource(self):
        g = OperationGuard()
        self.assertFalse(g.begin('craft', session_ready=False, resources_verified=True))
        self.assertFalse(g.begin('craft', session_ready=True, resources_verified=False))
        self.assertFalse(g.begin('', session_ready=True, resources_verified=True))
        self.assertEqual(g.status('craft'), OperationState.IDLE)

    def test_duplicate_blocked_until_confirmed(self):
        g = OperationGuard()
        self.assertTrue(g.begin('craft', session_ready=True, resources_verified=True))
        self.assertFalse(g.begin('craft', session_ready=True, resources_verified=True))
        self.assertEqual(g.status('craft'), OperationState.PENDING)
        self.assertTrue(g.confirmed('craft'))
        self.assertEqual(g.status('craft'), OperationState.IDLE)

    def test_uncertain_not_automatically_retried(self):
        g = OperationGuard()
        self.assertTrue(g.begin('trade', session_ready=True, resources_verified=True))
        self.assertTrue(g.mark_uncertain('trade'))
        self.assertFalse(g.begin('trade', session_ready=True, resources_verified=True))
        self.assertFalse(g.confirmed('trade'))
        self.assertEqual(g.status('trade'), OperationState.UNCERTAIN)

    def test_uncertain_requires_authoritative_resync(self):
        g = OperationGuard()
        g.begin('trade', session_ready=True, resources_verified=True)
        g.mark_uncertain('trade')
        g.reset_from_authoritative_sync('trade')
        self.assertEqual(g.status('trade'), OperationState.IDLE)

    def test_unexpected_confirm_does_not_unlock(self):
        g = OperationGuard()
        self.assertFalse(g.confirmed('missing'))
        self.assertFalse(g.mark_uncertain('missing'))
