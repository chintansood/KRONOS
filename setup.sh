#!/usr/bin/env bash
# KRONOS — one-command setup for macOS, Linux and Windows (inside WSL2 Ubuntu 24.04).
# Creates the Python environment and the PostgreSQL database, pulls the local AI models, generates the dataset,
# runs every engine, loads the 40 pseudonymised real court cases and builds the website. Then start with ./run.sh
# Prefer containers? See "Docker" in README.md (docker compose up --build).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
DB="${KRONOS_DB:-kronos}"
say()  { printf "\n\033[1;33m▸ %s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
fail() { printf "\n\033[1;31m✗ %s\033[0m\n" "$*"; exit 1; }
need() { command -v "$1" >/dev/null 2>&1; }
OS="$(uname -s)"; WSL=0; grep -qi microsoft /proc/version 2>/dev/null && WSL=1
# PostgreSQL from Homebrew is "keg-only" (not on PATH) and Postgres.app has its own folder: find them
for d in /opt/homebrew/opt/postgresql@{19,18,17,16}/bin /usr/local/opt/postgresql@{19,18,17,16}/bin /Applications/Postgres.app/Contents/Versions/latest/bin; do
  if ! command -v psql >/dev/null 2>&1 && [ -x "$d/psql" ]; then export PATH="$d:$PATH"; fi
done

say "Checking prerequisites"
if [ $WSL = 1 ] && [[ "$ROOT" == /mnt/* ]]; then
  fail "KRONOS is inside a Windows folder ($ROOT). Clone it inside WSL instead, e.g.  cd ~ && git clone https://github.com/chintansood/KRONOS.git"
fi
PY=""
for c in python3.13 python3.12 python3.11 python3.14 python3; do
  if need "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || fail "Python 3.11+ is required.  macOS: brew install python@3.12   ·   Ubuntu/WSL: sudo apt install python3.12 python3.12-venv"
"$PY" -c "import venv, ensurepip" 2>/dev/null || fail "Python's venv module is missing.  Ubuntu/WSL: sudo apt install python3.12-venv"
need psql && need createdb || fail "PostgreSQL is required.  macOS: brew install postgresql@18 pgvector && brew services start postgresql@18   ·   Ubuntu/WSL: sudo apt install postgresql postgresql-16-pgvector"
need node && need npm || fail "Node.js 18+ is required.  macOS: brew install node   ·   Ubuntu/WSL: sudo apt install nodejs npm"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 18 ] || fail "Node.js 18+ is required (found $(node --version)).  See https://nodejs.org"

# PostgreSQL must be running and must accept this user (Linux/WSL: start the service and create the role if needed)
if ! pg_isready -q 2>/dev/null && ! psql -d postgres -Atqc "select 1" >/dev/null 2>&1; then
  if [ "$OS" = "Linux" ]; then
    echo "  starting PostgreSQL (sudo may ask for your password)…"
    sudo service postgresql start >/dev/null 2>&1 || sudo systemctl start postgresql >/dev/null 2>&1 || true
    sleep 2
  fi
fi
if ! psql -d postgres -Atqc "select 1" >/dev/null 2>&1; then
  if [ "$OS" = "Linux" ]; then
    echo "  creating a PostgreSQL role for '$USER' (sudo may ask for your password)…"
    sudo -u postgres createuser -s "$USER" 2>/dev/null || true
  fi
fi
psql -d postgres -Atqc "select 1" >/dev/null 2>&1 \
  || fail "Cannot connect to PostgreSQL as '$USER'.  macOS: brew services start postgresql@18   ·   Ubuntu/WSL: sudo service postgresql start && sudo -u postgres createuser -s \$USER"
ok "PostgreSQL $(psql -d postgres -Atqc 'show server_version' | cut -d' ' -f1) is running"

# Ollama (optional): make sure the server is up
HAS_AI=0
if need ollama; then
  if ! ollama list >/dev/null 2>&1; then
    echo "  starting the Ollama server…"
    (nohup ollama serve >/tmp/kronos-ollama.log 2>&1 &) ; for i in $(seq 1 20); do ollama list >/dev/null 2>&1 && break; sleep 1; done
  fi
  ollama list >/dev/null 2>&1 && HAS_AI=1
fi
echo "  python: $($PY --version)   node: $(node --version)   ollama: $([ $HAS_AI = 1 ] && echo running || echo 'not available (the AI assistant will be off; everything else works)')"

say "Python environment (backend/.venv)"
"$PY" -m venv backend/.venv
backend/.venv/bin/pip install -q --upgrade pip
if [ "$OS" = "Linux" ]; then   # CPU build of PyTorch: avoids a ~2 GB CUDA download
  backend/.venv/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu
fi
backend/.venv/bin/pip install -q -r backend/requirements.txt
ok "Python packages installed"

say "Database '$DB' (PostgreSQL + pgvector)"
createdb "$DB" 2>/dev/null || true
psql -d "$DB" -qc "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null 2>&1 \
  || fail "pgvector is not available in PostgreSQL.  macOS: brew install postgresql@18 pgvector (Homebrew's pgvector supports PostgreSQL 18+)   ·   Ubuntu/WSL 24.04: sudo apt install postgresql-16-pgvector"
ok "database ready"

EMBED=""
if [ $HAS_AI = 1 ]; then
  say "Local AI models (Llama 3.1 8B + nomic-embed-text, ≈5 GB on first run)"
  ollama pull llama3.1:8b && ollama pull nomic-embed-text || { echo "  model download failed — continuing without the AI assistant"; EMBED="--no-embed"; }
else
  echo "  Ollama not found — install it from https://ollama.com (Linux/WSL: curl -fsSL https://ollama.com/install.sh | sh) and re-run to enable the AI assistant."
  EMBED="--no-embed"
fi

say "Generating the dataset and running every engine (≈3–8 min)"
(cd backend && KRONOS_DATABASE_URL="dbname=$DB" .venv/bin/python scripts/build_all.py --generate --public-records $EMBED)

say "Building the website"
(cd frontend && npm install --no-audit --no-fund --silent && npx vite build > /dev/null)

printf "\n\033[1;32m✓ KRONOS is ready.\033[0m  Start it with  ./run.sh  and open  http://localhost:8000"
[ $WSL = 1 ] && printf "  (in your Windows browser)"
printf "\n"
