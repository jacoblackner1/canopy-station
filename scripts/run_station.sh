#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -d "$HOME/home_sentinel/sentinel_env" ]; then
  # shellcheck disable=SC1091
  source "$HOME/home_sentinel/sentinel_env/bin/activate"
elif [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
exec python3 plant_dashboard.py
