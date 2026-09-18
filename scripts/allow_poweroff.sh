#!/bin/bash
# One-time: let the dashboard Shut down button halt the board without a password.
# Does not open any ports. Run:  sudo ./scripts/allow_poweroff.sh
set -euo pipefail

USER_NAME="${SUDO_USER:-${USER}}"
if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo ./scripts/allow_poweroff.sh" >&2
  exit 1
fi

SYSTEMCTL="$(command -v systemctl)"
POWEROFF_BIN="$(command -v poweroff || true)"
[ -z "$POWEROFF_BIN" ] && [ -x /sbin/poweroff ] && POWEROFF_BIN=/sbin/poweroff
[ -z "$POWEROFF_BIN" ] && [ -x /usr/sbin/poweroff ] && POWEROFF_BIN=/usr/sbin/poweroff

# Root oneshot — the Flask service is a normal user and cannot halt on its own.
cat >/etc/systemd/system/canopy-poweroff.service <<EOF
[Unit]
Description=Canopy station halt
[Service]
Type=oneshot
ExecStart=${POWEROFF_BIN:-/sbin/poweroff}
EOF
systemctl daemon-reload

# No '.' in the filename — Debian ignores sudoers.d files that contain a period.
FILE=/etc/sudoers.d/canopy-halt
{
  echo "Defaults:${USER_NAME} !requiretty"
  echo "${USER_NAME} ALL=(root) NOPASSWD: ${SYSTEMCTL} start canopy-poweroff.service"
  if [ -n "$POWEROFF_BIN" ]; then
    echo "${USER_NAME} ALL=(root) NOPASSWD: ${POWEROFF_BIN}"
  fi
  echo "${USER_NAME} ALL=(root) NOPASSWD: /sbin/poweroff, /usr/sbin/poweroff"
} >"$FILE"
chmod 440 "$FILE"
if ! visudo -cf "$FILE"; then
  rm -f "$FILE"
  echo "sudoers check failed — not installed" >&2
  exit 1
fi

# SSH + kiosk count as multiple sessions; without this, logind refuses power-off.
if [ -d /etc/polkit-1/rules.d ]; then
  cat >/etc/polkit-1/rules.d/50-canopy-poweroff.rules <<EOF
polkit.addRule(function(action, subject) {
    if (subject.user == "${USER_NAME}" &&
        (action.id == "org.freedesktop.login1.power-off" ||
         action.id == "org.freedesktop.login1.power-off-multiple-sessions")) {
        return polkit.Result.YES;
    }
});
EOF
  chmod 644 /etc/polkit-1/rules.d/50-canopy-poweroff.rules
fi

echo "OK: ${USER_NAME} can shut down from the phone/computer dashboard (two taps)."
echo "Then:  sudo systemctl restart canopy-station"
