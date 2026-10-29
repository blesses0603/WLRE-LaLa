import unittest
from lala_core.efficiency import ExperienceSample, estimate_experience


class ExperienceTests(unittest.TestCase):
    def test_rate_and_target(self):
        result = estimate_experience(ExperienceSample(0, 100),
                                     ExperienceSample(3600, 500), 900)
        self.assertEqual(result.experience_per_hour, 400)
        self.assertEqual(result.hours_to_target, 1)

    def test_no_gain_has_no_eta(self):
        result = estimate_experience(ExperienceSample(10, 50),
                                     ExperienceSample(20, 50), 100)
        self.assertEqual(result.experience_per_hour, 0)
        self.assertIsNone(result.hours_to_target)

    def test_invalid_or_reset_samples(self):
        with self.assertRaises(ValueError):
            estimate_experience(ExperienceSample(10, 20), ExperienceSample(10, 30))
        with self.assertRaises(ValueError):
            estimate_experience(ExperienceSample(10, 30), ExperienceSample(20, 20))
