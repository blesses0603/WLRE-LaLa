import unittest
from lala_core.features import BY_KEY, FEATURES


class FeatureTests(unittest.TestCase):
    def test_unique_and_nonempty(self):
        self.assertEqual(len(FEATURES), len(BY_KEY))
        self.assertGreaterEqual(len(FEATURES), 20)
        self.assertTrue(all(f.title and f.description and f.legacy_area for f in FEATURES))

    def test_all_platforms_share_registry(self):
        self.assertIn('dashboard', BY_KEY)
        for key in ('accounts', 'battle', 'world', 'inventory', 'expeditions', 'coop', 'chat', 'resources'):
            self.assertIn(key, BY_KEY)
