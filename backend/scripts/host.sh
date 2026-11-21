#!/bin/zsh
# Host KRONOS publicly from this Mac.
#   1. builds the website (kronos-app → dist)
#   2. runs the API, which also serves the website, behind an access code
#   3. opens a free Cloudflare quick tunnel → public https link
#   4. keeps the Mac awake while the API runs
# Stop with: scripts/stop_host.sh      The Mac must stay on, plugged in and online.
set -e
cd "$(dirname "$0")/.."
BACK="$PWD"; APP="${KRONOS_APP_DIR:-$BACK/../kronos-app}"; [ -d "$APP" ] || APP="$BACK/../frontend"   # working folders or the GitHub monorepo

# access code: KRONOS_ACCESS_CODE, else the saved one, else a new random one
CODE="${KRONOS_ACCESS_CODE:-$(cat data/host_access_code 2>/dev/null || true)}"
if [ -z "$CODE" ]; then
  CODE=$(python3 -c "import secrets; w=['TIME','EVIDENCE','ORBIT','LEDGER','RIVER','DIAL','TRACE','CIPHER','SIGNAL','ATLAS']; print(secrets.choice(w)+'-'+str(secrets.randbelow(9000)+1000))")
fi
echo "$CODE" > data/host_access_code; chmod 600 data/host_access_code

echo "▸ building the website…"
(cd "$APP" && npx vite build > "$BACK/data/host_build.log" 2>&1) || { echo "build failed — see data/host_build.log"; exit 1; }

echo "▸ starting the API + website on 127.0.0.1:8000…"
pkill -f "uvicorn kronos.api.main:app" 2>/dev/null || true
sleep 1
KRONOS_STATIC_DIR="$APP/dist" KRONOS_ACCESS_CODE="$CODE" nohup .venv/bin/python -m uvicorn kronos.api.main:app \
  --host 127.0.0.1 --port 8000 --proxy-headers --log-level warning > data/host_api.log 2>&1 &
API_PID=$!
for i in {1..40}; do curl -s -o /dev/null http://127.0.0.1:8000/__login && break; sleep 1; done
curl -s -o /dev/null http://127.0.0.1:8000/__login || { echo "API did not start — see data/host_api.log"; exit 1; }

echo "▸ opening the Cloudflare tunnel…"
pkill -f "cloudflared tunnel --url" 2>/dev/null || true
nohup cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate > data/host_tunnel.log 2>&1 &
URL=""
for i in {1..60}; do URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' data/host_tunnel.log | head -1); [ -n "$URL" ] && break; sleep 1; done
[ -n "$URL" ] || { echo "tunnel did not start — see data/host_tunnel.log"; exit 1; }
echo "$URL" > data/host_url

pkill -f "caffeinate -is -w" 2>/dev/null || true
nohup caffeinate -is -w $API_PID > /dev/null 2>&1 &

echo ""
echo "  KRONOS is live:  $URL"
echo "  Access code:     $CODE"
echo ""
echo "  Local:  http://localhost:8000   ·   stop: scripts/stop_host.sh"
