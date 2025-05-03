#!/usr/bin/env sh
set -e

# read env vars or fall back to defaults
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-25892}"
WORKERS="${WORKERS:-4}"

exec python -m uvicorn main:app \
     --host "$HOST" \
     --port "$PORT" \
     --workers "$WORKERS"