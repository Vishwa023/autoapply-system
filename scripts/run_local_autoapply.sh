#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Missing virtualenv. Create it with: python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt && ./.venv/bin/python -m playwright install chromium"
  exit 1
fi

cd "$ROOT_DIR"

mkdir -p "$ROOT_DIR/data" "$ROOT_DIR/data/screenshots"

export INSTAHYRE_USER_DATA_DIR="$ROOT_DIR/data/browser-profile"
export STATE_PATH="$ROOT_DIR/data/state-local.json"
export SCREENSHOTS_DIR="$ROOT_DIR/data/screenshots"

if [[ "${RESUME_PATH:-}" == "" || "${RESUME_PATH:-}" == "/data/resume.pdf" ]]; then
  export RESUME_PATH="$ROOT_DIR/data/resume.pdf"
fi

if [[ "${HEADLESS:-}" == "" ]]; then
  export HEADLESS=false
fi

exec "$ROOT_DIR/.venv/bin/python" -u -m app.worker.simple_runner
