"""Unit tests for read-only Roadie supervision diagnostics."""
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pathlib import Path
from roadie_supervision_diagnostics import heartbeat_snapshot, snapshot


class DiagnosticsTests(unittest.TestCase):
    def test_stale_heartbeat_and_missing_supervisor(self):
        rows = [{"pid": 42, "ppid": 1, "role": "watcher"}]
        result = snapshot(rows, {"pid": 42, "age_seconds": 90, "state": "MAP"})
        self.assertTrue(result["heartbeat_stale"])
        self.assertFalse(result["supervision_present"])

    def test_old_pid_does_not_match(self):
        rows = [{"pid": 45, "ppid": 1, "role": "watcher"}]
        result = snapshot(rows, {"pid": 42, "age_seconds": 1, "state": "MAP"})
        self.assertFalse(result["heartbeat_matches_running_watcher"])

    def test_corrupt_heartbeat_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "heartbeat.json"
            path.write_text("{bad json", encoding="utf-8")
            self.assertIn("error", heartbeat_snapshot(path))

    def test_fresh_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "heartbeat.json"
            path.write_text('{"pid": 42, "timestamp": 100, "state": "MAP"}')
            self.assertEqual(0, heartbeat_snapshot(path, now=100)["age_seconds"])


if __name__ == "__main__":
    unittest.main()
