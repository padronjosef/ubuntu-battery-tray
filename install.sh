#!/bin/sh
# Install Battery Tray for the current user under ~/.local and start it on login.
# The checkout is copied, so it can be moved or deleted afterwards. Run again to update.
set -eu

root="$(cd "$(dirname "$0")" && pwd)"
data="${XDG_DATA_HOME:-$HOME/.local/share}"
app="$data/battery-tray"
bin="$HOME/.local/bin/battery-tray"
uuid="battery-tray-left@padronjosef.github.io"
extension="$data/gnome-shell/extensions/$uuid"
autostart="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/battery-tray.desktop"

# App
rm -rf "$app"
mkdir -p "$app"
cp -r "$root/battery_tray" "$app/"
find "$app" -name __pycache__ -prune -exec rm -rf {} +
echo "Installed $app"

# Command
mkdir -p "$(dirname "$bin")"
cat > "$bin" <<EOF
#!/bin/sh
# python3 -m looks in the current directory first, so start from the installed copy.
cd "$app" && exec python3 -m battery_tray "\$@"
EOF
chmod +x "$bin"
echo "Installed $bin"

# Start on login
mkdir -p "$(dirname "$autostart")"
sed "s|@BIN@|$bin|" "$root/packaging/battery-tray.desktop.in" > "$autostart"
echo "Installed $autostart"

# GNOME Shell extension: colors, animation and left-side position of the icons
rm -rf "$extension"
mkdir -p "$extension"
cp "$root/gnome-extension/"* "$extension/"
echo "Installed $extension"
echo "First install: restart GNOME Shell, then run: gnome-extensions enable $uuid"
