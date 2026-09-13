#!/bin/bash
# One-time: dashboard on boot + Chromium kiosk on the HDMI desktop.
# Run from PuTTY:  cd ~/canopy-station && sudo ./scripts/install_hdmi.sh
set -euo pipefail

USER_NAME="${SUDO_USER:-${USER}}"
USER_HOME="$(eval echo "~${USER_NAME}")"
ROOT="${USER_HOME}/canopy-station"
PY="${USER_HOME}/home_sentinel/sentinel_env/bin/python3"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo ./scripts/install_hdmi.sh" >&2
  exit 1
fi

chmod +x "${ROOT}/scripts/"*.sh

# Python dashboard always on, even before anyone logs into the desktop.
cat >/etc/systemd/system/canopy-station.service <<EOF
[Unit]
Description=Canopy plant dashboard
After=network-online.target
Wants=network-online.target

[Service]
User=${USER_NAME}
Group=${USER_NAME}
WorkingDirectory=${ROOT}
ExecStart=${PY} ${ROOT}/plant_dashboard.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Autostart kiosk inside the graphical login (SSH cannot own HDMI by itself).
# xdg *.desktop works on XFCE/GNOME/Cinnamon. labwc/wayfire ignore those
# unless we also write their own autostart files.
install -d -o "${USER_NAME}" -g "${USER_NAME}" "${USER_HOME}/.config/autostart"
cat >"${USER_HOME}/.config/autostart/canopy-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Canopy HDMI
Comment=Stats-only plant kiosk
Exec=${ROOT}/scripts/start_kiosk.sh
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=4
EOF
chown "${USER_NAME}:${USER_NAME}" "${USER_HOME}/.config/autostart/canopy-kiosk.desktop"

if command -v labwc >/dev/null 2>&1 || [ -d "${USER_HOME}/.config/labwc" ]; then
  install -d -o "${USER_NAME}" -g "${USER_NAME}" "${USER_HOME}/.config/labwc"
  AUTOSTART="${USER_HOME}/.config/labwc/autostart"
  touch "$AUTOSTART"
  if ! grep -q "start_kiosk.sh" "$AUTOSTART" 2>/dev/null; then
    printf '%s\n' "${ROOT}/scripts/start_kiosk.sh &" >>"$AUTOSTART"
  fi
  chown "${USER_NAME}:${USER_NAME}" "$AUTOSTART"
  chmod +x "$AUTOSTART"
  echo "Enabled labwc autostart (Wayland)"
fi

if command -v wayfire >/dev/null 2>&1 || [ -f "${USER_HOME}/.config/wayfire.ini" ]; then
  install -d -o "${USER_NAME}" -g "${USER_NAME}" "${USER_HOME}/.config"
  WF="${USER_HOME}/.config/wayfire.ini"
  touch "$WF"
  if ! grep -q "start_kiosk.sh" "$WF" 2>/dev/null; then
    if ! grep -q '^\[autostart\]' "$WF" 2>/dev/null; then
      printf '\n[autostart]\n' >>"$WF"
    fi
    printf 'canopy = %s\n' "${ROOT}/scripts/start_kiosk.sh" >>"$WF"
  fi
  chown "${USER_NAME}:${USER_NAME}" "$WF"
  echo "Enabled wayfire autostart (Wayland)"
fi

if command -v sway >/dev/null 2>&1 || [ -f "${USER_HOME}/.config/sway/config" ]; then
  install -d -o "${USER_NAME}" -g "${USER_NAME}" "${USER_HOME}/.config/sway"
  SC="${USER_HOME}/.config/sway/config"
  touch "$SC"
  if ! grep -q "start_kiosk.sh" "$SC" 2>/dev/null; then
    printf '\nexec %s\n' "${ROOT}/scripts/start_kiosk.sh" >>"$SC"
  fi
  chown "${USER_NAME}:${USER_NAME}" "$SC"
  echo "Enabled sway autostart (Wayland)"
fi

# Skip the login screen so HDMI comes up on its own.
if [ -d /etc/lightdm ]; then
  mkdir -p /etc/lightdm/lightdm.conf.d
  cat >/etc/lightdm/lightdm.conf.d/12-canopy-autologin.conf <<EOF
[Seat:*]
autologin-user=${USER_NAME}
autologin-user-timeout=0
EOF
  echo "Enabled lightdm autologin for ${USER_NAME}"
fi
if [ -f /etc/gdm3/custom.conf ]; then
  python3 - "$USER_NAME" <<'PY'
from pathlib import Path
import sys
user = sys.argv[1]
p = Path("/etc/gdm3/custom.conf")
text = p.read_text()
lines = []
seen_enable = seen_user = False
for line in text.splitlines():
    if line.startswith("AutomaticLoginEnable"):
        lines.append("AutomaticLoginEnable=true")
        seen_enable = True
    elif line.startswith("AutomaticLogin=") or line.startswith("AutomaticLogin "):
        lines.append(f"AutomaticLogin={user}")
        seen_user = True
    else:
        lines.append(line)
out = "\n".join(lines)
if "[daemon]" not in out:
    out += "\n[daemon]\n"
if not seen_enable:
    out = out.replace("[daemon]", "[daemon]\nAutomaticLoginEnable=true", 1)
if not seen_user:
    out = out.replace("[daemon]", f"[daemon]\nAutomaticLogin={user}", 1)
p.write_text(out + ("\n" if not out.endswith("\n") else ""))
print(f"Enabled gdm autologin for {user}")
PY
fi

usermod -aG video,dialout,render "${USER_NAME}" 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now canopy-station.service

echo
echo "HDMI kiosk is installed."
echo "Reboot once:  sudo reboot"
echo "After boot the panel should show Canopy stats (no buttons)."
echo "If it still shows Armbian, run:  ${ROOT}/scripts/probe_display.sh"
echo "Phone/computer controls: http://$(hostname -I | awk '{print $1}'):5000/"
