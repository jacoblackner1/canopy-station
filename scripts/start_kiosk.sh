#!/bin/bash
# HDMI stats view — fills the plugged-in display. No water / lamp / calibrate.
# Must run ON the desktop session (autostart), not only from SSH.
# Controls stay on phones and computers at http://<pi-lan-ip>:5000/
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${ROOT}/kiosk.log"
URL="${1:-http://127.0.0.1:5000/kiosk}"
export DISPLAY="${DISPLAY:-:0}"

exec >>"$LOG" 2>&1
echo "---- $(date) start_kiosk DISPLAY=$DISPLAY ----"

# Pick the logged-in desktop's Xauthority so this works from systemd too.
if [ -z "${XAUTHORITY:-}" ]; then
  for a in \
    "$HOME/.Xauthority" \
    /run/lightdm/*/xauthority \
    /run/user/"$(id -u)"/gdm/Xauthority \
    /run/user/"$(id -u)"/.mutter-Xwaylandauth*; do
    if [ -f "$a" ]; then
      export XAUTHORITY="$a"
      break
    fi
  done
fi

for i in $(seq 1 60); do
  if [ -S /tmp/.X11-unix/X0 ] || [ -S /tmp/.X11-unix/X1 ]; then
    break
  fi
  echo "waiting for X ($i)"
  sleep 1
done

xset s off -dpms >/dev/null 2>&1 || true
xset s noblank >/dev/null 2>&1 || true
xrandr --auto >/dev/null 2>&1 || true

for i in $(seq 1 60); do
  if curl -sf -o /dev/null --max-time 1 "$URL"; then
    echo "dashboard ready"
    break
  fi
  sleep 1
done

pkill -f "chromium.*(kiosk|:5000)" >/dev/null 2>&1 || true
sleep 0.5

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

# Allwinner H6: GPU path often black-screens Chromium. Software draw is reliable.
PROFILE="/tmp/canopy-chrome"
mkdir -p "$PROFILE"

exec "$CHROME" \
  --kiosk \
  --start-fullscreen \
  --start-maximized \
  --window-position=0,0 \
  --force-device-scale-factor=1 \
  --app="$URL" \
  --user-data-dir="$PROFILE" \
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
