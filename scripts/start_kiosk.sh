#!/bin/bash
# HDMI stats view. Attaches to an existing desktop if one is running;
# otherwise starts our own compositor (cage / xinit) on tty1.
# SSH cannot own HDMI — that is what the canopy-kiosk systemd unit is for.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${ROOT}/kiosk.log"
URL="${1:-http://127.0.0.1:5000/kiosk}"
UID_NUM="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${UID_NUM}}"
export HOME="${HOME:-$(eval echo "~$(id -un)")}"

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "---- $(date) start_kiosk ----"
echo "user=$(id -un) uid=$UID_NUM invocation=${INVOCATION_ID-none}"
echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY-}"
echo "DISPLAY=${DISPLAY-}"
echo "XDG_SESSION_TYPE=${XDG_SESSION_TYPE-}"
echo "tty=$(tty 2>/dev/null || echo none)"
ps -eo comm= 2>/dev/null | grep -E '^(cage|labwc|wayfire|sway|weston|mutter|gnome-shell|Xorg|Xwayland|lightdm|gdm|sddm|xfce4-session)$' || echo "no compositor yet"
ls -l "$XDG_RUNTIME_DIR"/wayland-* /tmp/.X11-unix /dev/dri 2>&1 || true

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

WAIT=8
if [ -z "${INVOCATION_ID:-}" ]; then
  WAIT=20
fi

PLATFORM=""
for i in $(seq 1 "$WAIT"); do
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
  echo "waiting for display ($i/$WAIT)"
  sleep 1
done

wait_dashboard() {
  local i
  for i in $(seq 1 60); do
    if curl -sf -o /dev/null --max-time 1 "$URL"; then
      echo "dashboard ready"
      return 0
    fi
    sleep 1
  done
  echo "dashboard not up yet — launching anyway"
}

start_own_session() {
  echo "no existing desktop — starting a kiosk compositor on this tty"
  wait_dashboard
  if command -v cage >/dev/null 2>&1; then
    echo "using cage (Wayland)"
    export XDG_SESSION_TYPE=wayland
    export OZONE=wayland
    exec cage -s -- "$ROOT/scripts/chromium_kiosk.sh" "$URL"
  fi
  if command -v xinit >/dev/null 2>&1; then
    echo "using xinit + openbox (X11)"
    export XDG_SESSION_TYPE=x11
    exec xinit "$ROOT/scripts/kiosk_xsession.sh" "$URL" -- :0 vt1 -nolisten tcp -keeptty
  fi
  echo "cage and xinit missing. Re-run: sudo ./scripts/install_hdmi.sh"
  exit 1
}

if [ -z "$PLATFORM" ]; then
  if [ -n "${INVOCATION_ID:-}" ]; then
    start_own_session
  fi
  echo "No graphical session on this board (no Wayland, no X11, no seat)."
  echo "SSH cannot take HDMI. Run:  sudo ./scripts/install_hdmi.sh && sudo reboot"
  exit 1
fi

if [ "$PLATFORM" = wayland ]; then
  export XDG_SESSION_TYPE=wayland
  pkill -u "$UID_NUM" -x swayidle >/dev/null 2>&1 || true
else
  export XDG_SESSION_TYPE="${XDG_SESSION_TYPE:-x11}"
  if [ -z "${XAUTHORITY:-}" ]; then
    for a in \
      "$HOME/.Xauthority" \
      /run/lightdm/*/xauthority \
      /run/user/"$UID_NUM"/gdm/Xauthority; do
      if [ -f "$a" ]; then
        export XAUTHORITY="$a"
        break
      fi
    done
  fi
  xset s off -dpms >/dev/null 2>&1 || true
  xrandr --auto >/dev/null 2>&1 || true
fi

wait_dashboard
pkill -f "chromium.*(kiosk|:5000)" >/dev/null 2>&1 || true
sleep 0.3
export OZONE="$PLATFORM"
echo "attach ozone=$OZONE"
"$ROOT/scripts/chromium_kiosk.sh" "$URL"
if [ "$PLATFORM" = wayland ]; then
  echo "wayland chromium exited — retry x11"
  export OZONE=x11
  exec "$ROOT/scripts/chromium_kiosk.sh" "$URL"
fi
