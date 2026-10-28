"""Logitech mouse battery over HID++ 2.0 (Unified Battery feature 0x1004), no Solaar needed."""

from collections.abc import Callable

from . import hidraw
from .reading import Reading

VENDOR_ID = 0x046D
HIDPP_DESCRIPTOR_MARKERS = (
    bytes([0x06, 0x00, 0xFF]),  # vendor usage page 0xFF00
    bytes([0x85, 0x11]),  # HID++ long report ID
)
SHORT_REPORT = 0x10
LONG_REPORT = 0x11
DEVICE_INDEX = 1  # first device paired to the receiver
SOFTWARE_ID = 0x0A
ROOT_FEATURE_INDEX = 0x00
UNIFIED_BATTERY = 0x1004
CHARGING_STATES = {1, 2, 3}  # charging, slow charging, charge complete
EVENT_SOFTWARE_ID = 0x00  # device-initiated notifications carry software id 0
DEVICE_CONNECTION = 0x41  # HID++ 1.0 receiver notification: device connected or woke up


def request(feature_index: int, function: int, params: bytes = b"") -> bytes:
    header = bytes([LONG_REPORT, DEVICE_INDEX, feature_index, (function << 4) | SOFTWARE_ID])
    return header + params.ljust(16, b"\0")


def match_reply(report: bytes, feature_index: int, function: int) -> bytes | None:
    """Return the reply parameters, b"" for an error reply (device off), or None if unrelated."""
    if len(report) < 4 or report[1] != DEVICE_INDEX:
        return None
    if report[0] == SHORT_REPORT and report[2] == 0x8F and report[3] == feature_index:
        return b""
    if report[0] == LONG_REPORT and report[2] == 0xFF and report[3] == feature_index:
        return b""
    if report[0] == LONG_REPORT and report[2] == feature_index and report[3] == (function << 4) | SOFTWARE_ID:
        return bytes(report[4:20])
    return None


def parse_unified_battery(params: bytes) -> tuple[int, bool] | None:
    if len(params) < 3 or params[0] > 100:
        return None
    return params[0], params[2] in CHARGING_STATES


def parse_battery_event(report: bytes, feature_index: int | None) -> tuple[int, bool] | None:
    """Unified Battery status pushed by the mouse when its level or charging state changes."""
    if feature_index is None or len(report) < 7:
        return None
    if report[0] != LONG_REPORT or report[1] != DEVICE_INDEX or report[2] != feature_index:
        return None
    if report[3] != EVENT_SOFTWARE_ID:  # event 0 (status), software id 0
        return None
    return parse_unified_battery(bytes(report[4:7]))


def is_connection_event(report: bytes) -> bool:
    return len(report) >= 3 and report[0] == SHORT_REPORT and report[1] == DEVICE_INDEX and report[2] == DEVICE_CONNECTION


class LogitechMouse:
    key = "mouse"
    name = "Logitech mouse"
    icon = "battery-tray-mouse-symbolic"  # bundled in battery_tray/icons
    level_while_charging = True

    def __init__(self) -> None:
        self._feature_index: int | None = None

    def start(self, on_reading: Callable[[Reading], None], on_wake: Callable[[], None]) -> None:
        """Push battery changes as they happen; a wake-up triggers a fresh poll."""

        def handle(report: bytes) -> None:
            status = parse_battery_event(report, self._feature_index)
            if status is not None:
                percent, charging = status
                on_reading(Reading(percent=percent, charging=charging))
            elif is_connection_event(report):
                on_wake()

        hidraw.listen("logitech", lambda: hidraw.find(VENDOR_ID, None, *HIDPP_DESCRIPTOR_MARKERS), handle)

    def read(self) -> Reading:
        path = hidraw.find(VENDOR_ID, None, *HIDPP_DESCRIPTOR_MARKERS)
        if path is None:
            return Reading.unavailable("Receiver not connected")

        if self._feature_index is None:
            params = hidraw.transact(
                path,
                request(ROOT_FEATURE_INDEX, 0, UNIFIED_BATTERY.to_bytes(2, "big")),
                lambda report: match_reply(report, ROOT_FEATURE_INDEX, 0),
            )
            if not params:
                return Reading.unavailable("Mouse off or out of range")
            if params[0] == 0:
                return Reading.unavailable("Mouse has no Unified Battery feature")
            self._feature_index = params[0]

        feature_index = self._feature_index
        params = hidraw.transact(path, request(feature_index, 1), lambda report: match_reply(report, feature_index, 1))
        status = parse_unified_battery(params or b"")
        if status is None:
            self._feature_index = None
            return Reading.unavailable("Mouse off or out of range")
        percent, charging = status
        return Reading(percent=percent, charging=charging)
