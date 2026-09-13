#!/bin/bash
# HDMI stats view — fills the plugged-in display. No water / lamp / calibrate.
# Controls stay on phones and computers at http://<pi-lan-ip>:5000/
set -euo pipefail
export DISPLAY="${DISPLAY:-:0}"
URL="${1:-http://127.0.0.1:5000/kiosk}"

xset s off -dpms >/dev/null 2>&1 || true
xrandr --auto >/dev/null 2>&1 || true

for i in $(seq 1 30); do
  if curl -sf -o /dev/null --max-time 1 "$URL"; then
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
  echo "chromium is not installed. sudo apt install -y chromium" >&2
  exit 1
fi

exec "$CHROME" \
  --kiosk \
  --start-fullscreen \
  --start-maximized \
  --window-position=0,0 \
  --force-device-scale-factor=1 \
  --app="$URL" \
  --no-first-run \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-translate \
  --disable-restore-session-state \
  --autoplay-policy=no-user-gesture-required \
  --no-sandbox
