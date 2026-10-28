#!/bin/sh
# Start Battery Tray on login for the current user.
set -eu
root="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.config/autostart"
sed "s|@BIN@|$root/bin/battery-tray|" "$root/packaging/battery-tray.desktop.in" > "$HOME/.config/autostart/battery-tray.desktop"
echo "Installed $HOME/.config/autostart/battery-tray.desktop"

# GNOME Shell extension that moves the battery icons to the left of the top bar.
uuid="battery-tray-left@padronjosef.github.io"
mkdir -p "$HOME/.local/share/gnome-shell/extensions"
ln -sfn "$root/gnome-extension" "$HOME/.local/share/gnome-shell/extensions/$uuid"
echo "Linked $uuid (restart GNOME Shell, then: gnome-extensions enable $uuid)"
