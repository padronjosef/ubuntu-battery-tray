"""Tray app: one indicator per device, each labelled with its battery percentage."""

import logging
import signal
import threading
import time
from dataclasses import replace
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
gi.require_version("Notify", "0.7")
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import GLib, Gtk, Notify  # noqa: E402

from . import config  # noqa: E402
from .hyperx import HyperxHeadset  # noqa: E402
from .logitech import LogitechMouse  # noqa: E402
from .nuphy import NuphyKeyboard  # noqa: E402
from .estimate import BatteryHistory, format_remaining  # noqa: E402
from .reading import Reading  # noqa: E402

log = logging.getLogger("battery_tray")

LOW_BATTERY_HYSTERESIS = 5
ICON_DIR = Path(__file__).resolve().parent / "icons"
# The GNOME extension in gnome-extension/ styles each indicator from its title suffix:
# green while charging, red (and blinking) at the warning and critical levels.
CHARGING_TITLE_SUFFIX = " (charging)"
LOW_TITLE_SUFFIX = " (low)"
CRITICAL_TITLE_SUFFIX = " (critical)"
# The Ubuntu AppIndicator extension (v58) drops a label change that arrives while it is
# still registering the item, and the label then stays stuck. Wait before the first update.
FIRST_UPDATE_DELAY_SECONDS = 3


class DeviceIndicator:
    def __init__(self, device, settings: config.Settings, on_refresh, on_quit) -> None:
        self.device = device
        self.settings = settings
        self.indicator = AppIndicator.Indicator.new(
            f"battery-tray-{device.key}", device.icon, AppIndicator.IndicatorCategory.HARDWARE
        )
        if (ICON_DIR / f"{device.icon}.svg").exists():
            # Only bundled icons: a theme path makes the extension stop looking in the system theme.
            self.indicator.set_icon_theme_path(str(ICON_DIR))
        self.indicator.set_title(device.name)
        self.indicator.set_label("--", "100%")

        menu = Gtk.Menu()
        self.name_item = self._info_item(menu, device.name)
        self.status_item = self._info_item(menu, "")
        self.remaining_item = self._info_item(menu, "")
        self.updated_item = self._info_item(menu, "")
        menu.append(Gtk.SeparatorMenuItem())
        refresh = Gtk.MenuItem(label="Refresh now")
        refresh.connect("activate", lambda _item: on_refresh())
        menu.append(refresh)
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _item: on_quit())
        menu.append(quit_item)
        menu.show_all()
        self.indicator.set_menu(menu)
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

    @staticmethod
    def _info_item(menu: Gtk.Menu, label: str) -> Gtk.MenuItem:
        item = Gtk.MenuItem(label=label)
        item.set_sensitive(False)
        menu.append(item)
        return item

    def update(self, reading: Reading, remaining_seconds: float | None) -> None:
        self.indicator.set_title(indicator_title(self.device.name, reading, self.settings))
        if reading.percent is None:
            self.indicator.set_label("--", "100%")
            self.status_item.set_label(reading.detail or "No data")
            self.remaining_item.set_label("")
            self.updated_item.set_label("")
            return
        self.remaining_item.set_label(
            remaining_label(reading, remaining_seconds, self.device.level_while_charging)
        )
        self.indicator.set_label(f"{reading.percent}%", "100%")
        state = "Charging" if reading.charging else "Discharging"
        self.status_item.set_label(f"{reading.percent}% · {state}")
        when = time.strftime("%H:%M", time.localtime(reading.timestamp))
        if reading.stale:
            self.updated_item.set_label(f"Last report {when}" + (f" · {reading.detail}" if reading.detail else ""))
        else:
            self.updated_item.set_label(f"Updated {when}")


class BatteryTray:
    def __init__(self, settings: config.Settings) -> None:
        self.settings = settings
        self.refresh_event = threading.Event()
        self.low_notified: set[str] = set()
        self.last_known: dict[str, Reading] = {}
        cache_dir = Path(GLib.get_user_cache_dir()) / "battery-tray"
        self.history = BatteryHistory(cache_dir / "history.json")
        cache = cache_dir / "nuphy.json"
        self.keyboard = NuphyKeyboard(cache, lambda reading: GLib.idle_add(self.show, self.keyboard, reading))
        self.mouse = LogitechMouse()
        self.headset = HyperxHeadset()
        self.polled = [self.mouse, self.headset]
        self.indicators = {
            device.key: DeviceIndicator(device, settings, self.refresh_event.set, Gtk.main_quit)
            for device in (*self.polled, self.keyboard)
        }

    def run(self) -> None:
        Notify.init("Battery Tray")
        GLib.timeout_add_seconds(FIRST_UPDATE_DELAY_SECONDS, self._start_updates)
        for signum in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, Gtk.main_quit)
        Gtk.main()

    def _start_updates(self) -> bool:
        self.show(self.keyboard, self.keyboard.read())
        self.keyboard.start()
        self.mouse.start(
            on_reading=lambda reading: GLib.idle_add(self.show, self.mouse, reading),
            on_wake=self.refresh_event.set,
        )
        self.headset.start(on_change=self.refresh_event.set)
        threading.Thread(target=self._poll, name="poller", daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _poll(self) -> None:
        while True:
            for device in self.polled:
                try:
                    reading = device.read()
                except OSError as error:
                    log.error("%s: %s", device.name, error)
                    reading = Reading.unavailable(f"Error: {error.strerror or error}")
                GLib.idle_add(self.show, device, reading)
            # The keyboard pushes its level; re-show it so its remaining time keeps counting down.
            GLib.idle_add(self.show, self.keyboard, self.keyboard.read())
            self.refresh_event.wait(self.settings.poll_interval_seconds)
            self.refresh_event.clear()

    def show(self, device, reading: Reading) -> bool:
        reading = with_last_known(reading, self.last_known.get(device.key))
        if reading.percent is not None:
            self.last_known[device.key] = reading
        self.history.record(device.key, reading)
        remaining = self.history.remaining_seconds(device.key, time.time())
        self.indicators[device.key].update(reading, remaining)
        self._notify_if_low(device, reading)
        return GLib.SOURCE_REMOVE

    def _notify_if_low(self, device, reading: Reading) -> None:
        if reading.percent is None or reading.stale:
            return
        threshold = self.settings.low_battery_percent
        if reading.charging or reading.percent > threshold + LOW_BATTERY_HYSTERESIS:
            self.low_notified.discard(device.key)
            return
        if reading.percent <= threshold and device.key not in self.low_notified:
            self.low_notified.add(device.key)
            notification = Notify.Notification.new(
                f"{device.name}: {reading.percent}% battery", "Charge it soon.", "battery-caution-symbolic"
            )
            try:
                notification.show()
            except GLib.Error as error:
                log.error("cannot show notification: %s", error.message)


def indicator_title(name: str, reading: Reading, settings: config.Settings) -> str:
    """Title with the suffix the GNOME extension maps to green (charging) or red (low, critical)."""
    if reading.percent is None:
        return name
    if reading.charging and not reading.stale:
        return name + CHARGING_TITLE_SUFFIX
    if reading.percent <= settings.critical_percent:
        return name + CRITICAL_TITLE_SUFFIX
    if reading.percent <= settings.warning_percent:
        return name + LOW_TITLE_SUFFIX
    return name


def remaining_label(reading: Reading, remaining_seconds: float | None, level_while_charging: bool) -> str:
    if reading.charging and not reading.stale:
        if not level_while_charging:
            return "Charging"
        if reading.percent is not None and reading.percent >= 100:
            return "Fully charged"
        if remaining_seconds is None:
            return "Estimating charge time…"
        return f"{format_remaining(remaining_seconds)} to full"
    if remaining_seconds is None:
        return "Estimating remaining time…"
    return f"{format_remaining(remaining_seconds)} left"


def with_last_known(reading: Reading, last: Reading | None) -> Reading:
    """Keep showing the last level when a device stops answering (asleep, off, out of range)."""
    if reading.percent is not None or last is None:
        return reading
    return replace(last, stale=True, detail=reading.detail)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    BatteryTray(config.load()).run()
