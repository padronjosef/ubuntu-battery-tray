"""Time to empty or to full, estimated from how fast each device's level has been moving."""

import json
import logging
import math
import os
from pathlib import Path

from .reading import Reading

log = logging.getLogger(__name__)

MIN_CHANGE_PERCENT = 2  # levels are whole numbers, so one step alone says little about the rate
MIN_SPAN_SECONDS = 30 * 60
MAX_POINTS = 200
DISCHARGING = "discharging"
CHARGING = "charging"


class BatteryHistory:
    """Per device, one session: the time each new level was first seen while the level
    keeps moving in one direction (down while discharging, up while charging).

    Switching between charging and discharging, or a level moving the other way, starts
    a new session. Kept on disk because the keyboard takes days to lose a few percent.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._sessions: dict[str, dict] = self._load()

    def record(self, key: str, reading: Reading) -> None:
        if reading.percent is None or reading.stale:
            return
        mode = CHARGING if reading.charging else DISCHARGING
        session = self._sessions.get(key)
        if session is None or session["mode"] != mode:
            session = {"mode": mode, "points": []}
        points = session["points"]
        if points and self._moved_backwards(mode, points[-1][0], reading.percent):
            points.clear()
        if not points or reading.percent != points[-1][0]:
            points.append([reading.percent, reading.timestamp])
            session["points"] = points[-MAX_POINTS:]
            self._sessions[key] = session
            self._save()

    def remaining_seconds(self, key: str, now: float) -> float | None:
        """Seconds to 0% while discharging, or to 100% while charging."""
        session = self._sessions.get(key)
        if session is None or len(session["points"]) < 2:
            return None
        (first_percent, first_time), (last_percent, last_time) = session["points"][0], session["points"][-1]
        changed = abs(last_percent - first_percent)
        span = last_time - first_time
        if changed < MIN_CHANGE_PERCENT or span < MIN_SPAN_SECONDS:
            return None
        to_go = (100 - last_percent) if session["mode"] == CHARGING else last_percent
        return max(0.0, to_go / (changed / span) - (now - last_time))

    @staticmethod
    def _moved_backwards(mode: str, previous: float, current: float) -> bool:
        return current > previous if mode == DISCHARGING else current < previous

    def _load(self) -> dict[str, dict]:
        try:
            data = json.loads(self._path.read_text())
            sessions = {}
            for key, value in data.items():
                if isinstance(value, list):  # older files only tracked discharging
                    value = {"mode": DISCHARGING, "points": value}
                points = [[float(p), float(t)] for p, t in value["points"]]
                sessions[key] = {"mode": value["mode"], "points": points}
            return sessions
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            log.warning("ignoring unreadable history %s: %s", self._path, error)
            return {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._sessions))
            os.replace(tmp, self._path)
        except OSError as error:
            log.error("cannot write history %s: %s", self._path, error)


def format_remaining(seconds: float) -> str:
    hours = seconds / 3600
    if hours >= 24:
        days = int(hours // 24)
        return f"~{days} day" + ("s" if days != 1 else "")
    if hours >= 1:
        whole = int(hours)
        return f"~{whole} hour" + ("s" if whole != 1 else "")
    minutes = max(1, math.ceil(seconds / 60))
    return f"~{minutes} minute" + ("s" if minutes != 1 else "")
