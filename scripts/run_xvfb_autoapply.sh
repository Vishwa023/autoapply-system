#!/usr/bin/env sh
set -eu

DISPLAY_NUM="${DISPLAY:-:99}"
Xvfb "$DISPLAY_NUM" -screen 0 1280x1024x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!

cleanup() {
  kill "$XVFB_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

export DISPLAY="$DISPLAY_NUM"
exec python -u -m app.worker.simple_runner
