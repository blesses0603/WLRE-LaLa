import unittest
from lala_core.session import SessionStore


class SessionTests(unittest.TestCase):
    def test_requires_authenticated_resources_and_authoritative_source(self):
        store = SessionStore()
        self.assertFalse(store.apply(generation=0, revision=1, data={"hp": 10},
                                     authoritative=True))
        generation = store.start(authenticated=True, resources_verified=False)
        self.assertFalse(store.apply(generation=generation, revision=1, data={"hp": 10},
                                     authoritative=True))
        generation = store.start(authenticated=True, resources_verified=True)
        self.assertFalse(store.apply(generation=generation, revision=1, data={"hp": 10},
                                     authoritative=False))
        self.assertTrue(store.apply(generation=generation, revision=1, data={"hp": 10},
                                    authoritative=True))
        self.assertFalse(store.apply(generation=generation, revision=1, data={"hp": 20},
                                     authoritative=True))
        self.assertEqual(store.view().server_state["hp"], 10)

    def test_new_generation_and_disconnect_clear_old_data(self):
        store = SessionStore()
        first = store.start(authenticated=True, resources_verified=True)
        self.assertTrue(store.apply(generation=first, revision=0,
                                    data={"map": 33}, authoritative=True))
        store.disconnect()
        self.assertFalse(store.view().connected)
        self.assertFalse(store.view().server_state)
        second = store.start(authenticated=True, resources_verified=True)
        self.assertNotEqual(first, second)
        self.assertFalse(store.apply(generation=first, revision=200,
                                     data={"map": 77}, authoritative=True))

    def test_prevents_reference_mutation(self):
        store = SessionStore()
        gen = store.start(authenticated=True, resources_verified=True)
        source = {"items": [{"id": "a", "qty": 3}]}
        self.assertTrue(store.apply(generation=gen, revision=0, data=source,
                                    authoritative=True))
        source["items"][0]["qty"] = 999
        self.assertEqual(store.view().server_state["items"][0]["qty"], 3)
        with self.assertRaises(TypeError):
            store.view().server_state["hack"] = True

    def test_unsupported_data_type_rejected(self):
        store = SessionStore()
        gen = store.start(authenticated=True, resources_verified=True)
        with self.assertRaises(TypeError):
            store.apply(generation=gen, revision=0, data={"object": object()},
                        authoritative=True)
        self.assertEqual(store.view().revision, -1)
