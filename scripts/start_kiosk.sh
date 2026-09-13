#!/bin/bash
# HDMI stats view — fills the plugged-in display. No water / lamp / calibrate.
# Detects Wayland (labwc / wayfire / sway / GNOME) or X11 and launches Chromium
# on the compositor that actually owns HDMI. SSH cannot own that display.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${ROOT}/kiosk.log"
URL="${1:-http://127.0.0.1:5000/kiosk}"
UID_NUM="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${UID_NUM}}"

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "---- $(date) start_kiosk ----"
echo "user=$(id -un) uid=$UID_NUM"
echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY-}"
echo "DISPLAY=${DISPLAY-}"
echo "XDG_SESSION_TYPE=${XDG_SESSION_TYPE-}"
echo "DESKTOP_SESSION=${DESKTOP_SESSION-}"
echo "XDG_CURRENT_DESKTOP=${XDG_CURRENT_DESKTOP-}"
ps -eo comm= 2>/dev/null | grep -E '^(labwc|wayfire|sway|weston|mutter|gnome-shell|Xorg|Xwayland|lightdm|gdm|sddm|xfce4-session|cinnamon)$' || echo "no compositor in process list"
ls -l "$XDG_RUNTIME_DIR"/wayland-* /tmp/.X11-unix 2>&1 || true

pick_wayland() {
  local sock
  for sock in \
      ${WAYLAND_DISPLAY:+"$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY"} \
      "$XDG_RUNTIME_DIR"/wayland-0 \
      "$XDG_RUNTIME_DIR"/wayland-1 \
      "$XDG_RUNTIME_DIR"/wayland-2; do
    if [ -n "$sock" ] && [ -S "$sock" ]; then
      export WAYLAND_DISPLAY="$(basename "$sock")"
      return 0
    fi
  done
  return 1
}

pick_x11() {
  if [ -S /tmp/.X11-unix/X0 ]; then
    export DISPLAY="${DISPLAY:-:0}"
    return 0
  fi
  if [ -S /tmp/.X11-unix/X1 ]; then
    export DISPLAY="${DISPLAY:-:1}"
    return 0
  fi
  return 1
}

PLATFORM=""
for i in $(seq 1 90); do
  if pick_wayland; then
    PLATFORM=wayland
    echo "found wayland $WAYLAND_DISPLAY after ${i}s"
    break
  fi
  if pick_x11; then
    PLATFORM=x11
    echo "found x11 $DISPLAY after ${i}s"
    break
  fi
  echo "waiting for display ($i)"
  sleep 1
done

if [ -z "$PLATFORM" ]; then
  echo "no Wayland or X11 socket — HDMI compositor is not up"
  echo "hint: graphical session + autologin, then reboot after install_hdmi.sh"
  exit 1
fi

if [ "$PLATFORM" = wayland ]; then
  export XDG_SESSION_TYPE=wayland
  pkill -u "$UID_NUM" -x swayidle >/dev/null 2>&1 || true
else
  export DISPLAY="${DISPLAY:-:0}"
  export XDG_SESSION_TYPE="${XDG_SESSION_TYPE:-x11}"
  if [ -z "${XAUTHORITY:-}" ]; then
    for a in \
      "$HOME/.Xauthority" \
      /run/lightdm/*/xauthority \
      /run/user/"$UID_NUM"/gdm/Xauthority \
      /run/user/"$UID_NUM"/.mutter-Xwaylandauth*; do
      if [ -f "$a" ]; then
        export XAUTHORITY="$a"
        break
      fi
    done
  fi
  xset s off -dpms >/dev/null 2>&1 || true
  xset s noblank >/dev/null 2>&1 || true
  xrandr --auto >/dev/null 2>&1 || true
fi
echo "platform=$PLATFORM DISPLAY=${DISPLAY-} WAYLAND_DISPLAY=${WAYLAND_DISPLAY-}"

for i in $(seq 1 60); do
  if curl -sf -o /dev/null --max-time 1 "$URL"; then
    echo "dashboard ready"
    break
  fi
  sleep 1
done

pkill -f "chromium.*(kiosk|:5000)" >/dev/null 2>&1 || true
sleep 0.4

CHROME=""
for c in chromium chromium-browser google-chrome; do
  if command -v "$c" >/dev/null 2>&1; then
    CHROME="$c"
    break
  fi
done
if [ -z "$CHROME" ]; then
  echo "chromium is not installed. sudo apt install -y chromium"
  exit 1
fi
echo "using $CHROME"

PROFILE="/tmp/canopy-chrome"
mkdir -p "$PROFILE"

launch() {
  local ozone="$1"
  echo "launch ozone=$ozone"
  "$CHROME" \
    --kiosk \
    --start-fullscreen \
    --start-maximized \
    --window-position=0,0 \
    --force-device-scale-factor=1 \
    --app="$URL" \
    --user-data-dir="$PROFILE" \
    --ozone-platform="$ozone" \
    --no-first-run \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --disable-translate \
    --disable-features=Translate \
    --disable-gpu \
    --disable-dev-shm-usage \
    --autoplay-policy=no-user-gesture-required \
    --no-sandbox
  echo "chromium ozone=$ozone exited $?"
}

launch "$PLATFORM"
if [ "$PLATFORM" = wayland ]; then
  echo "native Wayland failed — retry via Xwayland"
  launch x11
fi
echo "kiosk ended"
