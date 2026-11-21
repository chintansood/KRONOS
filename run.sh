#!/usr/bin/env bash
# Start KRONOS after ./setup.sh — website + API on one address.
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT/backend"
DB="${KRONOS_DB:-kronos}"
[ -d .venv ] && [ -d "$ROOT/frontend/dist" ] || { echo "Run ./setup.sh first."; exit 1; }
PORT="${KRONOS_PORT:-8000}"; echo "KRONOS → http://localhost:$PORT   (Ctrl+C to stop)"
KRONOS_DATABASE_URL="dbname=$DB" KRONOS_STATIC_DIR="$ROOT/frontend/dist" \
  exec .venv/bin/python -m uvicorn kronos.api.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
