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
echo "default-target=$(systemctl get-default 2>/dev/null || echo ?)"
echo
echo "== compositors / display managers =="
ps -eo comm= 2>/dev/null | grep -E '^(cage|labwc|wayfire|sway|weston|mutter|gnome-shell|Xorg|Xwayland|lightdm|gdm|sddm|xfce4-session|openbox)$' || echo "(none)"
echo
echo "== drm =="
ls -l /sys/class/drm /dev/dri 2>/dev/null || echo "(no drm)"
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
echo "== packages =="
dpkg-query -W -f='${Status} ${Package}\n' cage seatd openbox xinit xserver-xorg chromium 2>/dev/null | grep "install ok" || true
echo
echo "== services =="
for u in canopy-station canopy-kiosk getty@tty1 lightdm gdm3; do
  printf '%-18s enabled=%s active=%s\n' "$u" \
    "$(systemctl is-enabled "$u" 2>/dev/null || echo n/a)" \
    "$(systemctl is-active "$u" 2>/dev/null || echo n/a)"
done
echo
echo "== chromium =="
command -v chromium chromium-browser cage xinit openbox 2>/dev/null || true
echo
echo "== autostart =="
ls -l "$HOME/.config/autostart" 2>/dev/null || true
