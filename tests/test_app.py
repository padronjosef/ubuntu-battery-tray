import unittest

from battery_tray.app import indicator_title, remaining_label, with_last_known
from battery_tray.config import Settings
from battery_tray.reading import Reading


class WithLastKnownTest(unittest.TestCase):
    def test_live_reading_is_shown_as_is(self):
        live = Reading(percent=50)
        self.assertIs(with_last_known(live, Reading(percent=80)), live)

    def test_unavailable_device_keeps_last_level_as_stale(self):
        last = Reading(percent=77, timestamp=100.0)
        shown = with_last_known(Reading.unavailable("Mouse off or out of range"), last)
        self.assertEqual(shown.percent, 77)
        self.assertTrue(shown.stale)
        self.assertEqual(shown.timestamp, 100.0)
        self.assertEqual(shown.detail, "Mouse off or out of range")

    def test_unavailable_without_history_stays_unavailable(self):
        self.assertIsNone(with_last_known(Reading.unavailable("Receiver not connected"), None).percent)


class IndicatorTitleTest(unittest.TestCase):
    settings = Settings(warning_percent=20, critical_percent=10)

    def title(self, reading: Reading) -> str:
        return indicator_title("Mouse", reading, self.settings)

    def test_live_charging_reading_gets_charging_suffix(self):
        self.assertEqual(self.title(Reading(percent=40, charging=True)), "Mouse (charging)")

    def test_charging_wins_over_low_battery(self):
        self.assertEqual(self.title(Reading(percent=5, charging=True)), "Mouse (charging)")

    def test_low_and_critical_levels(self):
        self.assertEqual(self.title(Reading(percent=21)), "Mouse")
        self.assertEqual(self.title(Reading(percent=20)), "Mouse (low)")
        self.assertEqual(self.title(Reading(percent=11)), "Mouse (low)")
        self.assertEqual(self.title(Reading(percent=10)), "Mouse (critical)")
        self.assertEqual(self.title(Reading(percent=0)), "Mouse (critical)")

    def test_last_known_low_level_stays_red_but_never_green(self):
        self.assertEqual(self.title(Reading(percent=8, stale=True)), "Mouse (critical)")
        self.assertEqual(self.title(Reading(percent=40, charging=True, stale=True)), "Mouse")

    def test_unknown_level_keeps_plain_name(self):
        self.assertEqual(self.title(Reading.unavailable("off")), "Mouse")

class RemainingLabelTest(unittest.TestCase):
    def test_discharging_labels(self):
        self.assertEqual(remaining_label(Reading(percent=50), None, True), "Estimating remaining time…")
        self.assertEqual(remaining_label(Reading(percent=50), 3 * 86400, True), "~3 days left")
        self.assertEqual(remaining_label(Reading(percent=50), 5 * 3600, True), "~5 hours left")

    def test_charging_labels(self):
        charging = Reading(percent=50, charging=True)
        self.assertEqual(remaining_label(charging, None, True), "Estimating charge time…")
        self.assertEqual(remaining_label(charging, 3600, True), "~1 hour to full")
        self.assertEqual(remaining_label(Reading(percent=100, charging=True), 0, True), "Fully charged")

    def test_device_without_real_level_while_charging(self):
        self.assertEqual(remaining_label(Reading(percent=100, charging=True), 0, False), "Charging")


if __name__ == "__main__":
    unittest.main()
