#!/bin/bash
# One-time: let the dashboard Shut down button halt the board without a password.
# Does not open any ports. Run:  sudo ./scripts/allow_poweroff.sh
set -euo pipefail

USER_NAME="${SUDO_USER:-${USER}}"
if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo:  sudo ./scripts/allow_poweroff.sh" >&2
  exit 1
fi

FILE=/etc/sudoers.d/canopy-poweroff
printf '%s ALL=(root) NOPASSWD: /sbin/poweroff, /usr/sbin/poweroff\n' "$USER_NAME" >"$FILE"
chmod 440 "$FILE"
if ! visudo -cf "$FILE"; then
  rm -f "$FILE"
  echo "sudoers check failed — not installed" >&2
  exit 1
fi
echo "OK: ${USER_NAME} can shut down from the phone/computer dashboard (two taps)."
