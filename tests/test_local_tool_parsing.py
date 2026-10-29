import unittest
from lala_desktop.local_tools import parse_pairs, description
from lala_core.feature_progress import PROGRESS


class ToolInputTests(unittest.TestCase):
    def test_comma_delimited_material_input(self):
        self.assertEqual(parse_pairs("1:2, 3:5, 1:4"), {1: 6, 3: 5})
        self.assertEqual(parse_pairs(""), {})
        with self.assertRaises(ValueError):
            parse_pairs("1;2")
        with self.assertRaises(ValueError):
            parse_pairs("0:3")
        with self.assertRaises(ValueError):
            parse_pairs("1:-2")

    def test_feature_labels_match_registry(self):
        self.assertEqual(description("efficiency"), PROGRESS["efficiency"].local_capability)
