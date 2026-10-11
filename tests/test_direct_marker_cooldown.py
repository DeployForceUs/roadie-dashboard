"""Static regression checks for the bounded direct-marker retry guard.

Run: python3 -m unittest discover -s tests -p 'test_direct_marker_cooldown.py'
These tests never connect to Android or touch the Roadie database.
"""
import ast
import pathlib
import unittest

WATCHER = pathlib.Path(__file__).resolve().parents[1] / "roadie_watcher_with_destinations.py"


class DirectMarkerCooldownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WATCHER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_retry_is_bounded(self):
        self.assertIn("DIRECT_MARKER_RETRY_SECONDS = 120", self.source)
        self.assertIn("time.monotonic() + DIRECT_MARKER_RETRY_SECONDS", self.source)

    def test_map_sightings_are_not_filtered(self):
        self.assertIn('json.dumps([e["desc"] for e in id_nodes])', self.source)
        self.assertIn('e["desc"] not in direct_marker_retry_after', self.source)

    def test_price_tracking_remains(self):
        self.assertIn('"PRICE_CHANGED"', self.source)
        self.assertIn("record_cards_if_complete()", self.source)

    def test_source_parses(self):
        self.assertIsInstance(self.tree, ast.Module)


if __name__ == "__main__":
    unittest.main()
