#!/bin/bash
# HDMI kiosk at native 800×480. Bind Chromium to the local dashboard only.
set -euo pipefail
export DISPLAY="${DISPLAY:-:0}"
URL="${1:-http://127.0.0.1:5000/}"

for i in $(seq 1 30); do
  if curl -sf -o /dev/null --max-time 1 "$URL"; then
    break
  fi
  sleep 1
done

exec chromium \
  --kiosk \
  --window-size=800,480 \
  --window-position=0,0 \
  --force-device-scale-factor=1 \
  --app="$URL" \
  --no-first-run \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-translate \
  --no-sandbox \
  "$URL"
