"""KRONOS container start-up.

1. wait for PostgreSQL and enable pgvector;
2. make sure the local AI models are in the Ollama service (downloaded once, kept in a volume);
3. on the first start only: generate the dataset, run every engine, load the real court cases, build the search index;
4. serve the website + API on port 8000.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psycopg2

DSN = os.environ.get("KRONOS_DATABASE_URL", "dbname=kronos")
OLLAMA = os.environ.get("KRONOS_OLLAMA_URL", "").rstrip("/")
MODELS = [os.environ.get("KRONOS_LLM_MODEL", "llama3.1:8b"), os.environ.get("KRONOS_EMBED_MODEL", "nomic-embed-text")]
MARK = Path("/app/backend/data/.kronos_built")


def log(msg):
    print(f"[kronos] {msg}", flush=True)


def wait_db():
    for _ in range(150):
        try:
            c = psycopg2.connect(DSN)
            c.autocommit = True
            c.cursor().execute("CREATE EXTENSION IF NOT EXISTS vector")
            c.close()
            return
        except Exception:
            time.sleep(2)
    sys.exit("PostgreSQL did not become ready")


def ollama_up(timeout=90) -> bool:
    if not OLLAMA:
        return False
    for _ in range(timeout // 3):
        try:
            urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5).read()
            return True
        except Exception:
            time.sleep(3)
    return False


def pull_models():
    have = {m["name"] for m in json.loads(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=10).read())["models"]}
    for m in MODELS:
        if m in have or f"{m}:latest" in have:
            continue
        log(f"downloading AI model {m} (once; kept in the 'ollama' volume)…")
        req = urllib.request.Request(OLLAMA + "/api/pull", data=json.dumps({"name": m}).encode(), headers={"Content-Type": "application/json"})
        last = -10
        with urllib.request.urlopen(req, timeout=7200) as r:
            for line in r:
                st = json.loads(line)
                if st.get("error"):
                    raise RuntimeError(st["error"])
                if st.get("total"):
                    pct = int(100 * st.get("completed", 0) / st["total"])
                    if pct >= last + 10:
                        log(f"  {m}: {pct}%"); last = pct
        log(f"  {m}: ready")


def main():
    log("waiting for PostgreSQL…")
    wait_db()
    ai = ollama_up()
    if ai:
        try:
            pull_models()
        except Exception as e:     # the site still works without the assistant
            log(f"AI models unavailable ({e}); the assistant will be off")
            ai = False
    else:
        log("Ollama not reachable — the AI assistant will be off; everything else works")
    if not MARK.exists():
        log("first start: generating the dataset and running every engine (5–15 min)…")
        args = [sys.executable, "scripts/build_all.py", "--generate", "--public-records"] + ([] if ai else ["--no-embed"])
        subprocess.run(args, check=True, cwd="/app/backend")
        MARK.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
    log("KRONOS is running → http://localhost:8000")
    os.execvp(sys.executable, [sys.executable, "-m", "uvicorn", "kronos.api.main:app", "--host", "0.0.0.0", "--port", "8000",
                               "--log-level", "warning"])


if __name__ == "__main__":
    main()
