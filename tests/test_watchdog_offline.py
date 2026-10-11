"""Offline tests for the macOS test watchdog. No watcher or ADB is launched."""
import json
from collections import deque
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import roadie_test_watchdog as wd


class WatchdogTests(unittest.TestCase):
    def test_restart_budget_allows_fewer_than_three(self):
        history = deque([100, 110])
        self.assertFalse(wd.restart_budget_exhausted(history, 120))

    def test_restart_budget_stops_after_three(self):
        history = deque([100, 110, 120])
        self.assertTrue(wd.restart_budget_exhausted(history, 121))

    def test_restart_budget_expires_old_failures(self):
        history = deque([100, 110, 120])
        self.assertFalse(wd.restart_budget_exhausted(history, 1001))
        self.assertEqual(list(history), [])

    def test_restart_budget_window_boundary(self):
        history = deque([100, 110, 120])
        self.assertTrue(wd.restart_budget_exhausted(history, 1000))
        self.assertFalse(wd.restart_budget_exhausted(history, 1001))

    def test_missing_heartbeat_uses_start_time(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(wd, "HEARTBEAT", Path(d) / "missing.json"):
                self.assertEqual(wd.progress_for(123, 100), (100, "NO_HEARTBEAT"))

    def test_old_pid_cannot_keep_new_watcher_alive(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "heartbeat.json"
            p.write_text(json.dumps({"pid": 10, "timestamp": 190, "state": "CYCLE_DONE"}))
            with patch.object(wd, "HEARTBEAT", p):
                self.assertEqual(wd.progress_for(11, 180), (180, "STARTING"))

    def test_prelaunch_heartbeat_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "heartbeat.json"
            p.write_text(json.dumps({"pid": 11, "timestamp": 150, "state": "CYCLE_DONE"}))
            with patch.object(wd, "HEARTBEAT", p):
                self.assertEqual(wd.progress_for(11, 180), (180, "STARTING"))

    def test_current_heartbeat(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "heartbeat.json"
            p.write_text(json.dumps({"pid": 11, "timestamp": 190, "state": "MAP"}))
            with patch.object(wd, "HEARTBEAT", p):
                self.assertEqual(wd.progress_for(11, 180), (190, "MAP"))

    def test_corrupt_heartbeat_is_not_progress(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "heartbeat.json"
            p.write_text("{invalid")
            with patch.object(wd, "HEARTBEAT", p):
                self.assertEqual(wd.progress_for(11, 180), (180, "NO_HEARTBEAT"))

    def test_stop_child_does_not_terminate_exited_process(self):
        class Child:
            def poll(self):
                return 0
            def terminate(self):
                raise AssertionError("must not terminate exited process")
        wd.stop_child(Child())

    def test_stop_child_escalates_after_timeout(self):
        from subprocess import TimeoutExpired
        class Child:
            terminated = False
            killed = False
            def poll(self):
                return None
            def terminate(self):
                self.terminated = True
            def wait(self, timeout):
                if timeout == 10:
                    raise TimeoutExpired("watcher", timeout)
                return 0
            def kill(self):
                self.killed = True
        child = Child()
        wd.stop_child(child)
        self.assertTrue(child.terminated)
        self.assertTrue(child.killed)


if __name__ == "__main__":
    unittest.main()
