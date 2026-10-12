#!/usr/bin/env bash
# Run ON EACH UNIT once, BEFORE the first `git pull` that includes the
# station.local.json change. Saves this unit's calibration so the pull
# (which stops tracking station.json) can't conflict or drop it.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f station.local.json ]]; then
  echo "station.local.json already exists; nothing to do."
  exit 0
fi
if [[ -f station.json ]]; then
  cp station.json station.local.json
  echo "Copied station.json -> station.local.json"
  git checkout -- station.json 2>/dev/null || true   # drop local edits so pull is clean
fi
echo "Now run: git pull"
