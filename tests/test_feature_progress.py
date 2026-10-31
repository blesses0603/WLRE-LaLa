import unittest
from lala_core.features import FEATURES
from lala_core.feature_progress import PROGRESS, report_lines


class ProgressTests(unittest.TestCase):
    def test_every_feature_is_accounted_for(self):
        self.assertEqual(set(PROGRESS), {feature.key for feature in FEATURES})
        self.assertEqual(len(PROGRESS), 27)
        self.assertTrue(all(not p.server_ready and not p.real_server_tested
                            for p in PROGRESS.values()))

    def test_no_false_e2e_claims(self):
        self.assertEqual(len(report_lines()), 27)
        self.assertTrue(all("尚未驗收" in line for line in report_lines()))
