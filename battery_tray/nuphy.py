"""NuPhy Air60 V2 battery pushed by the battery-report firmware (see firmware/README.md)."""

import json
import logging
from collections.abc import Callable
from pathlib import Path

from . import hidraw
from .reading import Reading

log = logging.getLogger(__name__)

VENDOR_ID = 0x19F5
PRODUCT_IDS = (0x3247,)  # 2.4G dongle
CONSUMER_REPORT_ID = 3
DESCRIPTOR_MARKER = bytes([0x85, CONSUMER_REPORT_ID])
DISCHARGING = 0x0300
CHARGING = 0x0400


def decode(report: bytes) -> tuple[int, bool] | None:
    if len(report) < 3 or report[0] != CONSUMER_REPORT_ID:
        return None
    usage = report[1] | (report[2] << 8)
    kind, percent = usage & 0xFF00, usage & 0x00FF
    if kind not in (DISCHARGING, CHARGING) or percent > 100:
        return None
    return percent, kind == CHARGING


class NuphyKeyboard:
    """Listens on the dongle; the keyboard pushes its level, so there is nothing to poll."""

    key = "keyboard"
    name = "NuPhy Air60 V2"
    icon = "input-keyboard-symbolic"
    level_while_charging = False  # the RF module reports a fixed 100% while charging

    def __init__(self, cache_path: Path, on_reading: Callable[[Reading], None]) -> None:
        self._cache_path = cache_path
        self._on_reading = on_reading
        self._last = self._load_cache()

    def read(self) -> Reading:
        return self._last

    def handle_report(self, report: bytes) -> None:
        battery = decode(report)
        if battery is None:
            return
        percent, charging = battery
        self._last = Reading(percent=percent, charging=charging)
        self._save_cache()
        self._on_reading(self._last)

    def start(self) -> None:
        hidraw.listen("nuphy", lambda: hidraw.find(VENDOR_ID, PRODUCT_IDS, DESCRIPTOR_MARKER), self.handle_report)

    def _load_cache(self) -> Reading:
        try:
            data = json.loads(self._cache_path.read_text())
            return Reading(percent=int(data["percent"]), charging=bool(data["charging"]),
                           timestamp=float(data["timestamp"]), stale=True)
        except FileNotFoundError:
            return Reading.unavailable("No report yet, press Fn + \\")
        except (OSError, ValueError, KeyError, TypeError) as error:
            log.warning("ignoring unreadable cache %s: %s", self._cache_path, error)
            return Reading.unavailable("No report yet, press Fn + \\")

    def _save_cache(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps({
                "percent": self._last.percent,
                "charging": self._last.charging,
                "timestamp": self._last.timestamp,
            }))
        except OSError as error:
            log.error("cannot write cache %s: %s", self._cache_path, error)
