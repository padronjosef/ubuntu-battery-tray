"""HyperX Cloud III S Wireless battery (protocol from Sapd/HeadsetControl issue #486)."""

from collections.abc import Callable

from . import hidraw
from .reading import Reading

VENDOR_ID = 0x03F0
PRODUCT_IDS = (0x06BE, 0x02CC)  # same headset, depends on hardware revision
DESCRIPTOR_MARKER = bytes([0x06, 0xC0, 0x01])  # vendor usage page 0x01C0
BATTERY_OPCODE = 0x06
QUERY = bytes([0x0C, 0x02, 0x03, 0x01, 0x00, BATTERY_OPCODE]).ljust(64, b"\0")
PUSH_REPORT_ID = 0x0D  # state changes the headset sends on its own
CHARGER_OPCODE = 0x0A  # pushed with 01 when the charger is plugged in, 00 when unplugged


def parse_reply(report: bytes) -> int | None:
    if len(report) < 7 or report[0] != 0x0C or report[5] != BATTERY_OPCODE:
        return None
    return report[6]


def parse_charging_push(report: bytes) -> bool | None:
    if len(report) < 6 or report[0] != PUSH_REPORT_ID or report[4] != CHARGER_OPCODE:
        return None
    return report[5] == 0x01


class HyperxHeadset:
    key = "headset"
    name = "HyperX Cloud III S"
    icon = "audio-headphones-symbolic"
    level_while_charging = True

    def __init__(self) -> None:
        # The battery reply has no charging flag and no read for it is known, so this
        # follows the charger push events and starts as "not charging".
        self._charging = False

    def start(self, on_change: Callable[[], None]) -> None:
        """Track charger plug events; each one triggers a fresh battery poll."""

        def handle(report: bytes) -> None:
            charging = parse_charging_push(report)
            if charging is not None:
                self._charging = charging
                on_change()

        hidraw.listen("hyperx", lambda: hidraw.find(VENDOR_ID, PRODUCT_IDS, DESCRIPTOR_MARKER), handle)

    def read(self) -> Reading:
        path = hidraw.find(VENDOR_ID, PRODUCT_IDS, DESCRIPTOR_MARKER)
        if path is None:
            return Reading.unavailable("Dongle not connected")
        percent = hidraw.transact(path, QUERY, parse_reply)
        if percent is None:
            return Reading.unavailable("No reply from headset")
        if percent > 100:
            return Reading.unavailable("Headset off")
        return Reading(percent=percent, charging=self._charging)
