#!/usr/bin/env bash
# KRONOS — one-command setup (macOS or Linux; on Windows run it inside WSL2 Ubuntu).
# Creates the Python environment, the PostgreSQL database, pulls the local AI models, generates the dataset,
# runs every engine, loads the 40 pseudonymised real court cases and builds the website. Then start with ./run.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
DB="${KRONOS_DB:-kronos}"
say()  { printf "\n\033[1;33m▸ %s\033[0m\n" "$*"; }
fail() { printf "\n\033[1;31m✗ %s\033[0m\n" "$*"; exit 1; }
need() { command -v "$1" >/dev/null 2>&1; }

say "Checking prerequisites"
PY=""
for c in python3.13 python3.12 python3.11 python3.14 python3; do
  if need "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || fail "Python 3.11+ is required.  macOS: brew install python@3.12   ·   Ubuntu: sudo apt install python3.12 python3.12-venv"
need psql && need createdb || fail "PostgreSQL is required.  macOS: brew install postgresql@16 pgvector && brew services start postgresql@16   ·   Ubuntu: sudo apt install postgresql postgresql-16-pgvector && sudo -u postgres createuser -s \$USER"
need npm || fail "Node.js 18+ is required: https://nodejs.org"
HAS_AI=0; need ollama && HAS_AI=1
echo "  python: $($PY --version)   postgres: $(psql --version | awk '{print $3}')   node: $(node --version)   ollama: $([ $HAS_AI = 1 ] && echo yes || echo 'not installed (AI assistant will be off)')"

say "Python environment (backend/.venv)"
"$PY" -m venv backend/.venv
backend/.venv/bin/pip install -q --upgrade pip
if [ "$(uname -s)" = "Linux" ]; then   # CPU build of PyTorch: avoids a ~2 GB CUDA download
  backend/.venv/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu
fi
backend/.venv/bin/pip install -q -r backend/requirements.txt

say "Database '$DB' (PostgreSQL + pgvector)"
createdb "$DB" 2>/dev/null || true
psql -d "$DB" -qc "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null 2>&1 \
  || fail "pgvector is not available in PostgreSQL. macOS: brew install pgvector   ·   Ubuntu: sudo apt install postgresql-16-pgvector"

EMBED=""
if [ $HAS_AI = 1 ]; then
  say "Local AI models (Llama 3.1 8B + nomic-embed-text, ≈5 GB on first run)"
  ollama pull llama3.1:8b && ollama pull nomic-embed-text || { echo "  model download failed — continuing without the AI assistant"; EMBED="--no-embed"; }
else
  echo "  Ollama not found — install it from https://ollama.com and re-run to enable the AI assistant."
  EMBED="--no-embed"
fi

say "Generating the dataset and running every engine (≈3–6 min)"
(cd backend && KRONOS_DATABASE_URL="dbname=$DB" .venv/bin/python scripts/build_all.py --generate --public-records $EMBED)

say "Building the website"
(cd frontend && npm install --no-audit --no-fund --silent && npx vite build > /dev/null)

printf "\n\033[1;32m✓ KRONOS is ready.\033[0m  Start it with  ./run.sh  and open  http://localhost:8000\n"
