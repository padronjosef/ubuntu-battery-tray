# Ubuntu Battery Tray

Battery levels of your wireless peripherals in the GNOME top bar, one icon each, right next to the workspace indicator.

| Device | Supported model | How it is read |
|---|---|---|
| 🖱️ Mouse | Logitech mice on a Lightspeed / Unifying receiver (HID++ 2.0 with Unified Battery) | Asked every minute, plus instant events from the receiver |
| 🎧 Headset | HyperX Cloud III S Wireless (`03f0:06be` and `03f0:02cc`) | Asked every minute, plus instant charger events |
| ⌨️ Keyboard | NuPhy Air60 V2 over its 2.4G dongle, with the [custom firmware](https://github.com/padronjosef/nuphy-air60-v2-firmware) | Pushed by the keyboard itself |

No Solaar, no vendor apps, no root.

## What you get

- **Percentage next to each icon.** If a device sleeps or turns off, it keeps showing its last known level.
- **Green** icon and text while charging.
- **Red** icon and text at 20% or less; the text "breathes" twice every 10 minutes, and every minute at 10% or less.
- **Menu per device** with the state, the estimated time left (`~3 days left`) or time to full while charging (`~1 hour to full`), and when it was last updated.
- **Desktop notification** when a device drops to 15%.
- Only the battery icons move to the left of the top bar; every other tray icon stays on the right.

---

## 🚀 Install (step by step)

Tested on Ubuntu 24.04 (GNOME 46, X11).

**1. Install the dependencies**

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 gir1.2-notify-0.7 gnome-shell-extension-appindicator
```

**2. Download this repo**

```bash
git clone https://github.com/padronjosef/ubuntu-battery-tray.git
cd ubuntu-battery-tray
```

**3. Allow access to the devices**

By default only root can talk to `/dev/hidraw*`. This rule gives the logged-in user access to these devices only:

```bash
sudo cp packaging/70-battery-tray.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger
```

**4. Install it**

```bash
./install.sh
```

Everything is copied under `~/.local`, the standard place for per-user apps, so you can delete the cloned folder afterwards:

| What | Where |
|---|---|
| App | `~/.local/share/battery-tray/` |
| Command | `~/.local/bin/battery-tray` |
| Start on login | `~/.config/autostart/battery-tray.desktop` |
| GNOME extension | `~/.local/share/gnome-shell/extensions/battery-tray-left@padronjosef.github.io/` |

To update later, `git pull` and run `./install.sh` again.

**5. Restart GNOME Shell and enable the extension**

On X11 press `Alt` + `F2`, type `r` and press `Enter`. On Wayland, log out and back in. Then:

```bash
gnome-extensions enable battery-tray-left@padronjosef.github.io
```

**6. Run it now**

```bash
~/.local/bin/battery-tray &
```

From now on it starts by itself when you log in.

### Keyboard

The NuPhy keyboard only reports its battery with the custom firmware from [nuphy-air60-v2-firmware](https://github.com/padronjosef/nuphy-air60-v2-firmware). Without it, its icon shows `--`. After flashing, press `Fn` + `\` once to send the first report.

### Uninstall

```bash
gnome-extensions disable battery-tray-left@padronjosef.github.io
pkill -f "python3 -m battery_tray"
rm -rf ~/.local/share/battery-tray ~/.local/bin/battery-tray ~/.config/autostart/battery-tray.desktop \
  ~/.local/share/gnome-shell/extensions/battery-tray-left@padronjosef.github.io
sudo rm /etc/udev/rules.d/70-battery-tray.rules
```

---

## ⚙️ Settings

Optional, in `~/.config/battery-tray/config.toml`. Every key has a default:

```toml
poll_interval_seconds = 60   # how often the mouse and headset are asked
low_battery_percent = 15     # desktop notification
warning_percent = 20         # red, text breathes twice every 10 minutes
critical_percent = 10        # red, text breathes twice every minute
```

Restart the tray after changing it.

---

## 🔍 How it works

### Mouse (Logitech)

Talks HID++ 2.0 directly to the receiver: it finds the Unified Battery feature (`0x1004`) and asks for its status. The mouse also pushes an event whenever its level or charging state changes, so plugging the cable turns the icon green right away. A wake-up notification from the receiver triggers a fresh read.

### Headset (HyperX Cloud III S)

Uses NGENUITY's vendor protocol on the `0x01C0` HID collection, documented in [HeadsetControl #486](https://github.com/Sapd/HeadsetControl/issues/486):

| | Bytes |
|---|---|
| Battery query | `0C 02 03 01 00 06` (reply byte 6 = percent, over 100 = headset off) |
| Charger plugged / unplugged (pushed) | `0D 02 03 00 0A 01` / `0D 02 03 00 0A 00` |

The charger event was found by capturing plug and unplug on this headset. There is no known query for the charging state, so if the tray starts while the headset is already charging, it turns green on the next plug event.

### Keyboard (NuPhy Air60 V2)

The custom firmware sends the level inside a media key report with a value no real key uses (`0x0300` + percent, or `0x0400` + percent while charging). The tray listens on the dongle and keeps the last value in `~/.cache/battery-tray/nuphy.json`.

### Time left

Each device's level changes are recorded since the last charge (or since charging started) in `~/.cache/battery-tray/history.json`. The estimate is linear from the first to the last change and needs at least a 2% change over 30 minutes, so right after a charge it shows `Estimating…`. The keyboard reports a fixed 100% while charging, so for it the menu only says `Charging`.

### Colors and position

The tray (Python, AyatanaAppIndicator) adds a suffix to each indicator title: ` (charging)`, ` (low)` or ` (critical)`. The GNOME extension in `gnome-extension/` reads it, applies the color and the breathing animation, and moves the three indicators to the left box of the top bar.

---

## 🧪 Development

```bash
python3 -m unittest      # 43 tests, standard library only
bin/battery-tray         # run this checkout in the foreground with logs
```

| Path | |
|---|---|
| `battery_tray/` | The tray: one module per device, the time estimate, the app |
| `gnome-extension/` | GNOME Shell 46 extension (position, colors, animation) |
| `packaging/` | Autostart entry and udev rule |
| `tests/` | Unit tests for the protocols, the estimate and the labels |

## Credits

- HyperX Cloud III S protocol: [Sapd/HeadsetControl#486](https://github.com/Sapd/HeadsetControl/issues/486).
- Mouse icon: `input-mouse-symbolic` from the [Adwaita icon theme](https://gitlab.gnome.org/GNOME/adwaita-icon-theme) (CC BY-SA 3.0 / LGPL-3.0), bundled in `battery_tray/icons/`.

## License

MIT, see [LICENSE](LICENSE). The bundled Adwaita icon keeps its own license.
