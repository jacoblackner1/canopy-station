#!/bin/bash
# One-time: cloudflared on boot, proxying to the existing Canopy dashboard.
# Does not touch canopy-kiosk, HDMI, or LAN :5000.
# Run:  cd ~/canopy-station && sudo ./scripts/install_tunnel.sh
set -euo pipefail

USER_NAME="${SUDO_USER:-${USER}}"
USER_HOME="$(eval echo "~${USER_NAME}")"
STATION="${USER_HOME}/canopy-station"
ACCESS="${USER_HOME}/canopy-cloudflare-access"
PACK="${STATION}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo ./scripts/install_tunnel.sh" >&2
  exit 1
fi

chmod +x "${STATION}/scripts/"*.sh 2>/dev/null || true

if [ ! -d "$ACCESS/.git" ]; then
  echo "Cloning canopy-cloudflare-access…"
  git clone https://github.com/jacoblackner1/canopy-cloudflare-access.git "$ACCESS"
  chown -R "${USER_NAME}:${USER_NAME}" "$ACCESS"
else
  git -C "$ACCESS" pull --ff-only || true
fi
PACK="$ACCESS"
chmod +x "${PACK}/scripts/"*.sh 2>/dev/null || true

if [ -x "${PACK}/scripts/install-cloudflared.sh" ]; then
  bash "${PACK}/scripts/install-cloudflared.sh"
else
  echo "Missing ${PACK}/scripts/install-cloudflared.sh" >&2
  exit 1
fi

install -d -m 0750 -o cloudflared -g cloudflared /etc/cloudflared

EXAMPLE="${PACK}/config/config.example.yml"
if [ -f "$EXAMPLE" ] && [ ! -f /etc/cloudflared/config.yml ]; then
  cp "$EXAMPLE" /etc/cloudflared/config.yml
  echo "Wrote /etc/cloudflared/config.yml (fill TUNNEL_UUID_HERE and canopy.EXAMPLE.com)"
fi
chown -R cloudflared:cloudflared /etc/cloudflared
chmod 0750 /etc/cloudflared
chmod 0640 /etc/cloudflared/config.yml 2>/dev/null || true

CF="$(command -v cloudflared || true)"
if [ -z "$CF" ]; then
  echo "cloudflared is not on PATH after install" >&2
  exit 1
fi

# Match canopy-station.service / canopy-kiosk.service style. Do not replace kiosk.
cat >/etc/systemd/system/cloudflared.service <<EOF
[Unit]
Description=Cloudflare Tunnel (Canopy)
After=network-online.target canopy-station.service
Wants=network-online.target
Wants=canopy-station.service

[Service]
Type=simple
User=cloudflared
Group=cloudflared
ExecStart=${CF} --no-autoupdate --config /etc/cloudflared/config.yml tunnel run
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cloudflared.service

if grep -E 'TUNNEL_UUID_HERE|EXAMPLE\\.com' /etc/cloudflared/config.yml >/dev/null 2>&1; then
  echo
  echo "cloudflared is installed and enabled, but config still has placeholders."
  echo "It will not stay up until you fill /etc/cloudflared/config.yml."
  echo "See ${STATION}/docs/REMOTE-ACCESS.md"
else
  systemctl restart cloudflared.service
  echo "cloudflared started."
fi

echo
echo "LAN dashboard is unchanged: http://$(hostname -I | awk '{print $1}'):5000/"
echo "HDMI kiosk is unchanged."
echo "No router port-forward. Remote URL is Access-gated HTTPS after you finish REMOTE-ACCESS.md"
