import unittest

from roadie_health import Health, Observation, classify


class HealthTests(unittest.TestCase):
    def obs(self, **kwargs):
        fields = dict(now=200, started_at=100, process_alive=True,
                      heartbeat_at=190, heartbeat_owner_matches=True)
        fields.update(kwargs)
        return Observation(**fields)

    def test_recent_heartbeat(self):
        self.assertEqual(classify(self.obs()), Health.HEALTHY)

    def test_stale_heartbeat(self):
        self.assertEqual(classify(self.obs(heartbeat_at=120)), Health.STALLED)

    def test_missing_heartbeat_grace(self):
        self.assertEqual(classify(self.obs(now=120, heartbeat_at=None)), Health.STARTING)
        self.assertEqual(classify(self.obs(heartbeat_at=None)), Health.STALLED)

    def test_dead_process(self):
        self.assertEqual(classify(self.obs(process_alive=False)), Health.EXITED)

    def test_wrong_owner(self):
        self.assertEqual(classify(self.obs(heartbeat_owner_matches=False)), Health.INVALID)

    def test_future_heartbeat(self):
        self.assertEqual(classify(self.obs(heartbeat_at=220)), Health.INVALID)

    def test_old_heartbeat_from_previous_process(self):
        self.assertEqual(classify(self.obs(heartbeat_at=99)), Health.INVALID)

    def test_invalid_clock(self):
        self.assertEqual(classify(self.obs(now=99)), Health.INVALID)

    def test_invalid_threshold(self):
        self.assertEqual(classify(self.obs(), stale_seconds=0), Health.INVALID)


if __name__ == "__main__":
    unittest.main()
