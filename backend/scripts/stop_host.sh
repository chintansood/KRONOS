#!/bin/zsh
# Stop public hosting: closes the tunnel and restarts the API in normal local mode (no access gate, no static site).
cd "$(dirname "$0")/.."
pkill -f "cloudflared tunnel --url" 2>/dev/null && echo "tunnel closed"
pkill -f "caffeinate -is -w" 2>/dev/null
pkill -f "uvicorn kronos.api.main:app" 2>/dev/null; sleep 1
nohup .venv/bin/python -m uvicorn kronos.api.main:app --port 8000 --log-level warning > /tmp/kronos_api.log 2>&1 &
echo "API back in local mode on :8000 (use the dev site at http://localhost:5173)"
rm -f data/host_url
