#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Create .venv first: python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt && ./.venv/bin/python -m playwright install chromium"
  exit 1
fi

cd "$ROOT_DIR"

INSTAHYRE_USER_DATA_DIR="$ROOT_DIR/data/browser-profile" \
HEADLESS=false \
"$ROOT_DIR/.venv/bin/python" -m app.worker.manual_login
