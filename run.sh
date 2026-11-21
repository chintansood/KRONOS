#!/usr/bin/env bash
# Start KRONOS after ./setup.sh — website + API on one address (macOS, Linux, Windows via WSL2).
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT/backend"
DB="${KRONOS_DB:-kronos}"
[ -d .venv ] && [ -d "$ROOT/frontend/dist" ] || { echo "Run ./setup.sh first."; exit 1; }
# PostgreSQL from Homebrew is "keg-only" (not on PATH) and Postgres.app has its own folder: find them
for d in /opt/homebrew/opt/postgresql@{19,18,17,16}/bin /usr/local/opt/postgresql@{19,18,17,16}/bin /Applications/Postgres.app/Contents/Versions/latest/bin; do
  if ! command -v psql >/dev/null 2>&1 && [ -x "$d/psql" ]; then export PATH="$d:$PATH"; fi
done
# after a reboot (Linux/WSL) the database and the AI server may not be running yet
if ! psql -d "$DB" -Atqc "select 1" >/dev/null 2>&1 && [ "$(uname -s)" = "Linux" ]; then
  echo "starting PostgreSQL (sudo may ask for your password)…"; sudo service postgresql start >/dev/null 2>&1 || sudo systemctl start postgresql >/dev/null 2>&1 || true; sleep 2
fi
psql -d "$DB" -Atqc "select 1" >/dev/null 2>&1 || { echo "PostgreSQL is not running (macOS: brew services start postgresql@18 · Linux/WSL: sudo service postgresql start)."; exit 1; }
if command -v ollama >/dev/null 2>&1 && ! ollama list >/dev/null 2>&1; then
  (nohup ollama serve >/tmp/kronos-ollama.log 2>&1 &); sleep 2
fi
PORT="${KRONOS_PORT:-8000}"; echo "KRONOS → http://localhost:$PORT   (Ctrl+C to stop)"
KRONOS_DATABASE_URL="dbname=$DB" KRONOS_STATIC_DIR="$ROOT/frontend/dist" \
  exec .venv/bin/python -m uvicorn kronos.api.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
