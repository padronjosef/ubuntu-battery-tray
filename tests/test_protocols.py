import tempfile
import unittest
from pathlib import Path

from battery_tray import config, hyperx, logitech, nuphy


def pad(data: bytes, size: int) -> bytes:
    return data.ljust(size, b"\0")


class LogitechTest(unittest.TestCase):
    def test_request_is_a_20_byte_long_report(self):
        request = logitech.request(0x00, 0x0, b"\x10\x04")
        self.assertEqual(request, pad(bytes([0x11, 0x01, 0x00, 0x0A, 0x10, 0x04]), 20))

    def test_matching_reply_returns_parameters(self):
        reply = pad(bytes([0x11, 0x01, 0x06, 0x1A, 0x4D, 0x08, 0x00]), 20)
        params = logitech.match_reply(reply, feature_index=0x06, function=0x1)
        self.assertEqual(params[:3], bytes([0x4D, 0x08, 0x00]))

    def test_reply_for_another_request_is_ignored(self):
        reply = pad(bytes([0x11, 0x01, 0x06, 0x0B, 0x4D]), 20)  # other software id
        self.assertIsNone(logitech.match_reply(reply, feature_index=0x06, function=0x1))

    def test_device_off_error_returns_empty(self):
        hidpp10_error = pad(bytes([0x10, 0x01, 0x8F, 0x06, 0x1A, 0x09]), 7)
        hidpp20_error = pad(bytes([0x11, 0x01, 0xFF, 0x06, 0x1A, 0x05]), 20)
        self.assertEqual(logitech.match_reply(hidpp10_error, 0x06, 0x1), b"")
        self.assertEqual(logitech.match_reply(hidpp20_error, 0x06, 0x1), b"")

    def test_unified_battery_status(self):
        self.assertEqual(logitech.parse_unified_battery(bytes([0x4D, 0x08, 0x00])), (77, False))
        self.assertEqual(logitech.parse_unified_battery(bytes([0x32, 0x08, 0x01])), (50, True))
        self.assertIsNone(logitech.parse_unified_battery(b""))
        self.assertIsNone(logitech.parse_unified_battery(bytes([0x96, 0x00, 0x00])))

    def test_battery_event_from_the_mouse(self):
        event = pad(bytes([0x11, 0x01, 0x06, 0x00, 0x4D, 0x08, 0x01]), 20)
        self.assertEqual(logitech.parse_battery_event(event, feature_index=0x06), (77, True))

    def test_battery_event_needs_known_feature_and_software_id_zero(self):
        event = pad(bytes([0x11, 0x01, 0x06, 0x00, 0x4D, 0x08, 0x01]), 20)
        reply = pad(bytes([0x11, 0x01, 0x06, 0x1A, 0x4D, 0x08, 0x01]), 20)  # our own poll reply
        self.assertIsNone(logitech.parse_battery_event(event, feature_index=None))
        self.assertIsNone(logitech.parse_battery_event(reply, feature_index=0x06))

    def test_connection_event(self):
        self.assertTrue(logitech.is_connection_event(pad(bytes([0x10, 0x01, 0x41, 0x0C]), 7)))
        self.assertFalse(logitech.is_connection_event(pad(bytes([0x10, 0x02, 0x41, 0x0C]), 7)))


class HyperxTest(unittest.TestCase):
    def test_charger_push_events(self):
        self.assertTrue(hyperx.parse_charging_push(pad(bytes([0x0D, 0x02, 0x03, 0x00, 0x0A, 0x01]), 64)))
        self.assertFalse(hyperx.parse_charging_push(pad(bytes([0x0D, 0x02, 0x03, 0x00, 0x0A, 0x00]), 64)))

    def test_other_pushes_and_replies_are_not_charger_events(self):
        self.assertIsNone(hyperx.parse_charging_push(pad(bytes([0x0D, 0x02, 0x03, 0x00, 0x04, 0x01]), 64)))
        self.assertIsNone(hyperx.parse_charging_push(pad(bytes([0x0C, 0x02, 0x03, 0x01, 0x00, 0x0A, 0x04]), 64)))

    def test_query_is_64_bytes(self):
        self.assertEqual(len(hyperx.QUERY), 64)
        self.assertEqual(hyperx.QUERY[:6], bytes([0x0C, 0x02, 0x03, 0x01, 0x00, 0x06]))

    def test_battery_reply(self):
        reply = pad(bytes([0x0C, 0x02, 0x03, 0x01, 0x00, 0x06, 0x47, 0x0F, 0x3E]), 64)
        self.assertEqual(hyperx.parse_reply(reply), 71)

    def test_unrelated_report_is_ignored(self):
        self.assertIsNone(hyperx.parse_reply(pad(bytes([0x0D, 0x02, 0x03]), 64)))
        self.assertIsNone(hyperx.parse_reply(pad(bytes([0x0C, 0x02, 0x03, 0x01, 0x00, 0x16, 0x47]), 64)))


class NuphyTest(unittest.TestCase):
    def test_decode_battery_reports(self):
        self.assertEqual(nuphy.decode(bytes([0x03, 0x47, 0x03])), (71, False))
        self.assertEqual(nuphy.decode(bytes([0x03, 0x64, 0x04])), (100, True))

    def test_decode_ignores_regular_media_keys_and_other_reports(self):
        self.assertIsNone(nuphy.decode(bytes([0x03, 0xE9, 0x00])))  # volume up
        self.assertIsNone(nuphy.decode(bytes([0x03, 0x00, 0x00])))  # release
        self.assertIsNone(nuphy.decode(bytes([0x03, 0x65, 0x03])))  # 101%
        self.assertIsNone(nuphy.decode(bytes([0x01, 0x47, 0x03])))  # other report id

    def test_last_reading_survives_restart_as_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "nuphy.json"
            first = nuphy.NuphyKeyboard(cache_path=cache, on_reading=lambda reading: None)
            first.handle_report(bytes([0x03, 0x3C, 0x03]))
            second = nuphy.NuphyKeyboard(cache_path=cache, on_reading=lambda reading: None)
            reading = second.read()
            self.assertEqual(reading.percent, 60)
            self.assertTrue(reading.stale)

    def test_without_cache_reports_no_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            keyboard = nuphy.NuphyKeyboard(cache_path=Path(tmp) / "none.json", on_reading=lambda reading: None)
            self.assertIsNone(keyboard.read().percent)


class ConfigTest(unittest.TestCase):
    def test_defaults_when_file_is_missing(self):
        settings = config.load(Path("/nonexistent/config.toml"))
        self.assertEqual(settings.poll_interval_seconds, 60)
        self.assertEqual(settings.low_battery_percent, 15)
        self.assertEqual(settings.warning_percent, 20)
        self.assertEqual(settings.critical_percent, 10)

    def test_file_overrides_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("low_battery_percent = 25\n")
            settings = config.load(path)
            self.assertEqual(settings.low_battery_percent, 25)
            self.assertEqual(settings.poll_interval_seconds, 60)


if __name__ == "__main__":
    unittest.main()
