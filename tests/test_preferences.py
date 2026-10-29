import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from lala_core.settings import LocalPreferences, load_preferences, save_preferences


class PreferenceTests(unittest.TestCase):
    def test_round_trip_only_whitelisted_values(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "config" / "preferences.json"
            self.assertEqual(load_preferences(path), LocalPreferences())
            prefs = LocalPreferences(False, True, 75)
            save_preferences(path, prefs)
            self.assertEqual(load_preferences(path), prefs)
            self.assertNotIn("password", path.read_text(encoding="utf-8"))

    def test_credentials_are_rejected(self):
        with TemporaryDirectory() as temp:
            p = Path(temp) / "settings.json"
            p.write_text(json.dumps({"show_event_log": True,
                                     "show_map_grid": True,
                                     "log_limit": 120, "token": "abc"}))
            with self.assertRaises(ValueError):
                load_preferences(p)

    def test_invalid_limit(self):
        with TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                save_preferences(Path(temp) / "x", LocalPreferences(log_limit=0))
