#!/bin/zsh
# Build the clean GitHub monorepo  ../../kronos-github  =  frontend/ (kronos-app) + backend/ (kronos-backend) + root files.
# Excludes are applied while copying, so private or heavy files never reach the release folder at all.
set -e
cd "$(dirname "$0")/../.."                     # the folder holding kronos-app and kronos-backend
OUT=kronos-github
mkdir -p "$OUT"
COMMON=(--exclude .git --exclude .DS_Store --exclude __pycache__ --exclude .pytest_cache --exclude .env)
rsync -a --delete "${COMMON[@]}" --exclude node_modules --exclude dist --exclude .vite kronos-app/ "$OUT/frontend/"
rsync -a --delete "${COMMON[@]}" --exclude .venv --exclude .venv-ft --exclude release \
  --exclude data/external --exclude data/keys --exclude 'data/host_*' --exclude data/generated --exclude data/summaries \
  --exclude data/models --exclude data/train_world --exclude 'data/finetune/adapters*' --exclude 'data/finetune/*.safetensors' \
  --exclude 'data/finetune/*.log' --exclude 'data/finetune/*.raw.json' --exclude data/finetune/examples_with_meta.jsonl \
  kronos-backend/ "$OUT/backend/"
cp kronos-backend/release/README.md "$OUT/README.md"
cp kronos-backend/release/setup.sh kronos-backend/release/run.sh "$OUT/"
cp kronos-backend/release/gitignore "$OUT/.gitignore"
chmod +x "$OUT/setup.sh" "$OUT/run.sh"
echo "release folder: $PWD/$OUT  ($(du -sh "$OUT" | cut -f1))"
