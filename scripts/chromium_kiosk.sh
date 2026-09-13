#!/bin/bash
# Chromium on whatever compositor start_kiosk already attached to.
set -u
URL="${1:-http://127.0.0.1:5000/kiosk}"
OZONE="${OZONE:-x11}"

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

PROFILE="/tmp/canopy-chrome"
mkdir -p "$PROFILE"

echo "chromium ozone=$OZONE url=$URL"
exec "$CHROME" \
  --kiosk \
  --start-fullscreen \
  --start-maximized \
  --window-position=0,0 \
  --force-device-scale-factor=1 \
  --app="$URL" \
  --user-data-dir="$PROFILE" \
  --ozone-platform="$OZONE" \
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
