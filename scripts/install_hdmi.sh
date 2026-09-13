#!/bin/bash
# One-time: dashboard on boot + a kiosk compositor that OWNS HDMI.
# This board has no desktop (probe showed no seat / no wayland / no X).
# Run from PuTTY:  cd ~/canopy-station && sudo ./scripts/install_hdmi.sh
set -euo pipefail

USER_NAME="${SUDO_USER:-${USER}}"
USER_HOME="$(eval echo "~${USER_NAME}")"
USER_UID="$(id -u "${USER_NAME}")"
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

export DEBIAN_FRONTEND=noninteractive
echo "Installing a tiny HDMI stack (chromium + cage/X)…"
apt-get update -qq
apt-get install -y --no-install-recommends \
  chromium \
  xserver-xorg \
  xserver-xorg-legacy \
  xinit \
  openbox \
  unclutter \
  x11-xserver-utils \
  dbus-x11 \
  xserver-xorg-video-modesetting \
  xserver-xorg-video-fbdev
apt-get install -y --no-install-recommends cage seatd || true

if [ -f /etc/X11/Xwrapper.config ]; then
  if grep -q '^allowed_users=' /etc/X11/Xwrapper.config; then
    sed -i 's/^allowed_users=.*/allowed_users=anybody/' /etc/X11/Xwrapper.config
  else
    echo "allowed_users=anybody" >>/etc/X11/Xwrapper.config
  fi
  if grep -q '^needs_root_rights=' /etc/X11/Xwrapper.config; then
    sed -i 's/^needs_root_rights=.*/needs_root_rights=yes/' /etc/X11/Xwrapper.config
  else
    echo "needs_root_rights=yes" >>/etc/X11/Xwrapper.config
  fi
else
  printf 'allowed_users=anybody\nneeds_root_rights=yes\n' >/etc/X11/Xwrapper.config
fi

usermod -aG video,dialout,render,input,tty "${USER_NAME}" 2>/dev/null || true
loginctl enable-linger "${USER_NAME}" >/dev/null 2>&1 || true

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

cat >/etc/systemd/system/canopy-kiosk.service <<EOF
[Unit]
Description=Canopy HDMI kiosk
After=canopy-station.service systemd-user-sessions.service
Wants=canopy-station.service
Conflicts=getty@tty1.service
After=getty@tty1.service

[Service]
Type=simple
User=${USER_NAME}
Group=${USER_NAME}
SupplementaryGroups=video render input tty
PAMName=login
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
StandardInput=tty
StandardOutput=journal
StandardError=journal
UtmpIdentifier=tty1
UtmpMode=user
WorkingDirectory=${ROOT}
Environment=HOME=${USER_HOME}
Environment=XDG_RUNTIME_DIR=/run/user/${USER_UID}
ExecStartPre=+/bin/mkdir -p /run/user/${USER_UID}
ExecStartPre=+/bin/chown ${USER_UID}:${USER_UID} /run/user/${USER_UID}
ExecStartPre=+/bin/chmod 700 /run/user/${USER_UID}
ExecStart=${ROOT}/scripts/start_kiosk.sh
Restart=always
RestartSec=4

[Install]
WantedBy=multi-user.target
EOF

# If they later install a desktop, this still helps.
install -d -o "${USER_NAME}" -g "${USER_NAME}" "${USER_HOME}/.config/autostart"
cat >"${USER_HOME}/.config/autostart/canopy-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Canopy HDMI
Exec=${ROOT}/scripts/start_kiosk.sh
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
EOF
chown "${USER_NAME}:${USER_NAME}" "${USER_HOME}/.config/autostart/canopy-kiosk.desktop"

if [ -d /etc/lightdm ]; then
  mkdir -p /etc/lightdm/lightdm.conf.d
  cat >/etc/lightdm/lightdm.conf.d/12-canopy-autologin.conf <<EOF
[Seat:*]
autologin-user=${USER_NAME}
autologin-user-timeout=0
EOF
fi

systemctl daemon-reload
systemctl enable canopy-station.service
systemctl enable canopy-kiosk.service
systemctl disable getty@tty1.service >/dev/null 2>&1 || true
systemctl restart canopy-station.service

echo
echo "HDMI kiosk compositor is installed."
echo "Stop any manual python dashboard (Ctrl+C), then:  sudo reboot"
echo "The panel should show Canopy stats after boot — not the Armbian splash."
echo "Phone/computer controls: http://$(hostname -I | awk '{print $1}'):5000/"
echo "If it is still Armbian:  journalctl -u canopy-kiosk -n 80 --no-pager"
