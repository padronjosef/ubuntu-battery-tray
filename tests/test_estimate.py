import tempfile
import unittest
from pathlib import Path

from battery_tray.estimate import BatteryHistory, format_remaining
from battery_tray.reading import Reading

HOUR = 3600


def reading(percent: int, at: float, charging: bool = False, stale: bool = False) -> Reading:
    return Reading(percent=percent, charging=charging, timestamp=at, stale=stale)


class BatteryHistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "history.json"
        self.history = BatteryHistory(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_estimate_until_enough_drop_and_time(self):
        self.history.record("mouse", reading(80, 0))
        self.assertIsNone(self.history.remaining_seconds("mouse", now=10))
        self.history.record("mouse", reading(79, 10 * 60))
        self.assertIsNone(self.history.remaining_seconds("mouse", now=10 * 60))

    def test_linear_estimate_from_first_and_last_drop(self):
        # 1% per hour: 80% at t=0, 78% at t=2h, so 78 hours remain from the last drop.
        self.history.record("mouse", reading(80, 0))
        self.history.record("mouse", reading(79, 1 * HOUR))
        self.history.record("mouse", reading(78, 2 * HOUR))
        self.assertAlmostEqual(self.history.remaining_seconds("mouse", now=2 * HOUR), 78 * HOUR)
        # Time since the last drop is subtracted.
        self.assertAlmostEqual(self.history.remaining_seconds("mouse", now=3 * HOUR), 77 * HOUR)

    def test_repeated_same_level_keeps_first_time_seen(self):
        self.history.record("mouse", reading(80, 0))
        self.history.record("mouse", reading(80, 1 * HOUR))
        self.history.record("mouse", reading(78, 2 * HOUR))
        self.assertAlmostEqual(self.history.remaining_seconds("mouse", now=2 * HOUR), 78 * HOUR)

    def test_level_rise_without_charging_flag_starts_a_new_session(self):
        self.history.record("headset", reading(60, 0))
        self.history.record("headset", reading(58, 2 * HOUR))
        self.history.record("headset", reading(70, 3 * HOUR))  # charged without a charging flag
        self.assertIsNone(self.history.remaining_seconds("headset", now=3 * HOUR))

    def test_time_to_full_while_charging(self):
        # +10% per hour: 50% at t=0, 70% at t=2h, so 3 hours to 100% from the last rise.
        self.history.record("mouse", reading(50, 0, charging=True))
        self.history.record("mouse", reading(60, 1 * HOUR, charging=True))
        self.history.record("mouse", reading(70, 2 * HOUR, charging=True))
        self.assertAlmostEqual(self.history.remaining_seconds("mouse", now=2 * HOUR), 3 * HOUR)

    def test_full_battery_needs_no_more_time(self):
        self.history.record("mouse", reading(96, 0, charging=True))
        self.history.record("mouse", reading(100, 1 * HOUR, charging=True))
        self.assertEqual(self.history.remaining_seconds("mouse", now=1 * HOUR), 0)

    def test_switching_between_charging_and_discharging_starts_over(self):
        self.history.record("mouse", reading(50, 0, charging=True))
        self.history.record("mouse", reading(70, 2 * HOUR, charging=True))
        self.history.record("mouse", reading(70, 3 * HOUR))
        self.assertIsNone(self.history.remaining_seconds("mouse", now=3 * HOUR))

    def test_old_discharge_only_file_still_loads(self):
        self.path.write_text('{"mouse": [[80, 0], [78, 7200]]}')
        self.assertAlmostEqual(BatteryHistory(self.path).remaining_seconds("mouse", now=7200), 78 * HOUR)

    def test_stale_and_unknown_readings_are_ignored(self):
        self.history.record("mouse", reading(80, 0))
        self.history.record("mouse", reading(78, 2 * HOUR))
        self.history.record("mouse", reading(10, 3 * HOUR, stale=True))
        self.history.record("mouse", Reading.unavailable("off"))
        self.assertAlmostEqual(self.history.remaining_seconds("mouse", now=2 * HOUR), 78 * HOUR)

    def test_never_negative(self):
        self.history.record("mouse", reading(3, 0))
        self.history.record("mouse", reading(1, 2 * HOUR))
        self.assertEqual(self.history.remaining_seconds("mouse", now=10 * HOUR), 0)

    def test_history_survives_restart(self):
        self.history.record("keyboard", reading(90, 0))
        self.history.record("keyboard", reading(88, 24 * HOUR))
        reloaded = BatteryHistory(self.path)
        self.assertAlmostEqual(reloaded.remaining_seconds("keyboard", now=24 * HOUR), 88 * 12 * HOUR)

    def test_corrupt_file_starts_empty(self):
        self.path.write_text("{not json")
        self.assertIsNone(BatteryHistory(self.path).remaining_seconds("mouse", now=0))


class FormatRemainingTest(unittest.TestCase):
    def test_days_hours_minutes(self):
        self.assertEqual(format_remaining(3 * 24 * HOUR + 5 * HOUR), "~3 days")
        self.assertEqual(format_remaining(24 * HOUR), "~1 day")
        self.assertEqual(format_remaining(23.6 * HOUR), "~23 hours")
        self.assertEqual(format_remaining(1 * HOUR), "~1 hour")
        self.assertEqual(format_remaining(40 * 60), "~40 minutes")
        self.assertEqual(format_remaining(30), "~1 minute")


if __name__ == "__main__":
    unittest.main()
