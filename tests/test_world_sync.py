"""可信會話生命週期的純合成事件測試，不連遊戲伺服器。"""
import unittest

from lala_core.login import VerifiedLoginOutcome
from lala_core.session import SessionStore
from lala_core.world_sync import (
    VerifiedPosition, WorldPhase, WorldSync,
)


OK = VerifiedLoginOutcome(True, (1,), True, True)
UNVERIFIED = VerifiedLoginOutcome(True, (1,), False, True)


class WorldSyncTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore()
        self.now = [100.0]
        self.engine = WorldSync(self.store, clock=lambda: self.now[0],
                                idle_timeout=30)
        self.generation = self.store.start(
            authenticated=True, resources_verified=True)

    def attach(self):
        return self.engine.attach(generation=self.generation, role_id=123,
                                  outcome=OK, world_schema_verified=True)

    def position(self, revision, *, role=123, scene=10, x=20, y=30,
                 generation=None, schema=True):
        return VerifiedPosition(
            self.generation if generation is None else generation,
            revision, role, scene, x, y, schema)

    def test_no_data_before_complete_snapshot(self):
        self.assertTrue(self.attach())
        self.assertEqual(self.engine.view().phase, WorldPhase.WAITING_SNAPSHOT)
        self.assertFalse(self.engine.view().authoritative)
        self.assertFalse(self.engine.position(self.position(1)))
        self.assertEqual(self.store.view().revision, -1)
        self.assertFalse(self.store.view().server_state)

    def test_verified_initial_snapshot_then_consecutive_positions(self):
        self.assertTrue(self.attach())
        self.assertTrue(self.engine.full_snapshot(self.position(0)))
        self.assertTrue(self.engine.view().authoritative)
        self.assertEqual(self.store.view().server_state["scene"], 10)
        self.assertTrue(self.engine.position(self.position(1, x=21)))
        self.assertEqual(self.store.view().server_state["x"], 21)
        self.assertEqual(self.store.view().revision, 1)
        self.assertFalse(self.engine.position(self.position(1, x=700)))
        self.assertEqual(self.store.view().server_state["x"], 21)
        self.assertTrue(self.engine.view().authoritative)

    def test_missing_revision_invalidates_without_automatic_reconnect(self):
        self.attach()
        self.engine.full_snapshot(self.position(0))
        self.assertFalse(self.engine.position(self.position(2, x=40)))
        self.assertEqual(self.engine.view().phase, WorldPhase.RESYNC_REQUIRED)
        self.assertFalse(self.engine.view().authoritative)
        self.assertFalse(self.store.view().connected)
        self.assertFalse(self.store.view().server_state)
        self.assertFalse(self.engine.position(self.position(1)))
        self.assertFalse(self.engine.attach(
            generation=self.generation, role_id=123, outcome=OK,
            world_schema_verified=True))

    def test_bad_role_and_schema_invalidate(self):
        for bad in ({"role": 124}, {"schema": False}, {"scene": 65536}):
            with self.subTest(bad=bad):
                session = SessionStore()
                generation = session.start(authenticated=True,
                                           resources_verified=True)
                e = WorldSync(session)
                self.assertTrue(e.attach(generation=generation, role_id=123,
                                         outcome=OK, world_schema_verified=True))
                self.assertTrue(e.full_snapshot(
                    VerifiedPosition(generation, 0, 123, 1, 1, 1, True)))
                options = dict(revision=1, role_id=123, scene=1, x=1, y=1,
                               generation=generation, schema_verified=True)
                options.update({"role_id" if k == "role" else
                                "schema_verified" if k == "schema" else k: v
                                for k, v in bad.items()})
                self.assertFalse(e.position(VerifiedPosition(**options)))
                self.assertEqual(e.view().phase, WorldPhase.RESYNC_REQUIRED)
                self.assertFalse(session.view().connected)

    def test_timeout_clears_snapshot_and_requires_new_login(self):
        self.attach()
        self.engine.full_snapshot(self.position(0))
        self.now[0] += 29.9
        self.assertTrue(self.engine.tick())
        self.now[0] += .1
        self.assertFalse(self.engine.tick())
        self.assertEqual(self.engine.view().phase, WorldPhase.RESYNC_REQUIRED)
        self.assertFalse(self.store.view().server_state)

    def test_deliberate_disconnect_invalidates_old_generation(self):
        self.attach()
        self.engine.full_snapshot(self.position(0))
        self.engine.disconnect()
        self.assertEqual(self.engine.view().phase, WorldPhase.DISCONNECTED)
        self.assertFalse(self.store.view().server_state)
        self.assertFalse(self.engine.position(self.position(1)))
        self.generation = self.store.start(authenticated=True,
                                           resources_verified=True)
        self.assertTrue(self.attach())
        self.assertFalse(self.engine.full_snapshot(
            self.position(0, generation=self.generation - 2)))
        self.assertFalse(self.store.view().connected)

    def test_fail_closed_with_unreviewed_protocol_or_schema(self):
        for outcome, schema in ((UNVERIFIED, True), (OK, False),
                                (None, True), (OK, 1)):
            with self.subTest(schema=schema, outcome=outcome):
                self.assertFalse(self.engine.attach(
                    generation=self.generation, role_id=123,
                    outcome=outcome, world_schema_verified=schema))
                self.assertEqual(self.store.view().revision, -1)
                self.assertFalse(self.engine.view().authoritative)

    def test_detached_session_generation_can_never_be_revived(self):
        self.attach()
        self.engine.full_snapshot(self.position(0))
        self.store.disconnect()
        self.assertFalse(self.engine.view().authoritative)
        self.assertFalse(self.engine.tick())
        self.assertEqual(self.engine.view().phase, WorldPhase.DISCONNECTED)
        self.assertFalse(self.engine.position(self.position(1)))
        self.assertFalse(self.store.view().server_state)

    def test_initial_snapshot_must_start_at_revision_zero(self):
        self.assertTrue(self.attach())
        self.assertFalse(self.engine.full_snapshot(self.position(1)))
        self.assertFalse(self.store.view().connected)
        self.assertEqual(self.engine.view().phase, WorldPhase.RESYNC_REQUIRED)

    def test_boolean_or_negative_fields_never_count_as_valid(self):
        self.attach()
        for bad in (
            VerifiedPosition(True, 0, 123, 1, 1, 1, True),
            VerifiedPosition(self.generation, True, 123, 1, 1, 1, True),
            VerifiedPosition(self.generation, 0, 123, -1, 1, 1, True),
        ):
            with self.subTest(packet=bad):
                # Start a new genuine session for each intentional invalidation.
                if self.engine.view().phase != WorldPhase.WAITING_SNAPSHOT:
                    self.generation = self.store.start(
                        authenticated=True, resources_verified=True)
                    self.assertTrue(self.attach())
                self.assertFalse(self.engine.full_snapshot(bad))
                self.assertFalse(self.store.view().connected)


if __name__ == "__main__":
    unittest.main()
