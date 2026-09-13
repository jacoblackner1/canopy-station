#!/bin/bash
# Print how this Pi is serving HDMI. Run from PuTTY and paste the output if
# the panel still shows Armbian after install_hdmi.sh + reboot.
set -u
UID_NUM="$(id -u)"
RD="${XDG_RUNTIME_DIR:-/run/user/${UID_NUM}}"
echo "user=$(id -un) uid=$UID_NUM"
echo "XDG_RUNTIME_DIR=$RD"
echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY-}"
echo "DISPLAY=${DISPLAY-}"
echo "XDG_SESSION_TYPE=${XDG_SESSION_TYPE-}"
echo "XDG_CURRENT_DESKTOP=${XDG_CURRENT_DESKTOP-}"
echo "DESKTOP_SESSION=${DESKTOP_SESSION-}"
echo
echo "== compositors / display managers =="
ps -eo comm= 2>/dev/null | grep -E '^(labwc|wayfire|sway|weston|mutter|gnome-shell|Xorg|Xwayland|lightdm|gdm|sddm|xfce4-session|cinnamon)$' || echo "(none in this SSH session — that is normal)"
echo
echo "== wayland sockets =="
ls -l "$RD"/wayland-* 2>/dev/null || echo "(none under $RD)"
echo
echo "== x11 sockets =="
ls -l /tmp/.X11-unix 2>/dev/null || echo "(none)"
echo
echo "== sessions =="
loginctl 2>/dev/null || true
echo
echo "== chromium =="
command -v chromium chromium-browser google-chrome 2>/dev/null || echo "(not installed)"
echo
echo "== autostart =="
ls -l "$HOME/.config/autostart" "$HOME/.config/labwc/autostart" "$HOME/.config/wayfire.ini" 2>/dev/null || true
