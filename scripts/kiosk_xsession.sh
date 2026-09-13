#!/bin/bash
# X11 session used when this board has no desktop — openbox + Chromium.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DISPLAY="${DISPLAY:-:0}"
if command -v openbox >/dev/null 2>&1; then
  openbox &
elif command -v matchbox-window-manager >/dev/null 2>&1; then
  matchbox-window-manager -use_titlebar no &
fi
if command -v unclutter >/dev/null 2>&1; then
  unclutter -idle 0.5 -root &
fi
xset s off -dpms >/dev/null 2>&1 || true
xset s noblank >/dev/null 2>&1 || true
xrandr --auto >/dev/null 2>&1 || true
export OZONE=x11
exec "$ROOT/scripts/chromium_kiosk.sh" "${1:-http://127.0.0.1:5000/kiosk}"
