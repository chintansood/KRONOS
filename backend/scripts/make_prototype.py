"""Build the online prototype: the KRONOS website plus a read-only snapshot of its API, for static hosting (GitHub Pages).

    cd backend && .venv/bin/python scripts/make_prototype.py --out ../prototype [--base /KRONOS/]

No server is needed: the API is called in-process. Ledger writes are switched off while the snapshot is taken, so the
local evidence ledger is not changed. In the browser, public/kronos-static.js answers the website's API calls from the
snapshot, recomputes Merkle inclusion proofs and checks the agencies' Ed25519 signatures itself. The local AI and case
registration need the full install; the prototype says so where they are used.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACK))

from kronos.engines.provenance import ledger  # noqa: E402

ledger.append = lambda *a, **k: None            # read-only: verification and access logging must not write blocks
ledger.append_many = lambda *a, **k: 0

from fastapi.testclient import TestClient  # noqa: E402

import kronos.api.main as M  # noqa: E402
from kronos import db  # noqa: E402
from kronos.engines.temporal import timeline as T  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=str(BACK.parent / "prototype"))
ap.add_argument("--base", default="/KRONOS/", help="URL path the site is served from (GitHub Pages: /<repo>/)")
ap.add_argument("--app", default="", help="website folder (default: ../kronos-app or ../frontend)")
ap.add_argument("--repo", default="https://github.com/chintansood/KRONOS")
args = ap.parse_args()
APP = Path(args.app) if args.app else next(p for p in (BACK.parent / "kronos-app", BACK.parent / "frontend") if p.exists())
OUT = Path(args.out).resolve()
SNAP = OUT / "snapshot"
client = TestClient(M.app)
stats = Counter()


def key(path: str) -> str:
    """'/cases/CASE002/hypotheses?personId=P00019' → 'cases/CASE002/hypotheses__personId_P00019.json' (same rule as kronos-static.js)."""
    p, _, q = path.lstrip("/").partition("?")
    q = re.sub(r"[^A-Za-z0-9._-]", "_", q)
    return f"{p}{'__' + q if q else ''}.json"


def write(rel: str, data, kind="json"):
    f = SNAP / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    if kind == "json":
        f.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    else:
        f.write_text(data, encoding="utf-8")
    stats["files"] += 1
    stats["bytes"] += f.stat().st_size


def get(path: str):
    r = client.get("/api" + path)
    r.raise_for_status()
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


def save(path: str, transform=None):
    try:
        data = get(path)
    except Exception as e:  # noqa: BLE001
        stats["missing"] += 1
        print(f"  ! {path}: {str(e)[:120]}")
        return None
    write(key(path), transform(data) if transform else data)
    return data


t0 = time.time()
# ------------------------------------------------------------------ 1. the website, built for the hosting path
print(f"▸ building the website ({APP.name}) for {args.base}")
if OUT.exists():
    shutil.rmtree(OUT)
subprocess.run(["npx", "vite", "build", f"--base={args.base}", "--outDir", str(OUT), "--emptyOutDir"], cwd=APP, check=True,
               stdout=subprocess.DEVNULL)
idx = OUT / "index.html"
html = idx.read_text(encoding="utf-8")
live_tag = re.search(r'<script src="[^"]*kronos-live\.js"></script>', html)
assert live_tag, "kronos-live.js script tag not found in the built index.html"
built = time.strftime("%Y-%m-%d")
cfg = {"base": "snapshot/", "built": built, "repo": args.repo}
html = html.replace(live_tag.group(0), f'<script>window.KRONOS_STATIC={json.dumps(cfg)}</script>\n'
                    f'<script src="{args.base}kronos-static.js"></script>\n{live_tag.group(0)}', 1)
html = html.replace("<title>", '<meta name="description" content="KRONOS online prototype — a read-only snapshot of the AI-assisted digital investigation platform.">\n<title>', 1)
idx.write_text(html, encoding="utf-8")
(OUT / ".nojekyll").write_text("")
(OUT / "404.html").write_text(html, encoding="utf-8")          # any unknown path still opens the app

# ------------------------------------------------------------------ 2. lists and platform views
print("▸ snapshot: lists, ledger, federated learning, alerts")
health = get("/health")
health.setdefault("llm", {})["available"] = False
health["prototype"] = True
write(key("/health"), health)
cases = save("/cases")
persons = save("/persons")
for p in ["/temporal/highlights?limit=6", "/ledger/status", "/ledger/verify", "/federated/report", "/alerts", "/intake/options"]:
    save(p)

# ------------------------------------------------------------------ 3. every case workspace
print(f"▸ snapshot: {len(cases)} case workspaces")
ev_case = {}
for c in cases:
    cid = c["id"]
    evs = save(f"/cases/{cid}/evidence") or []
    for e in evs:
        ev_case.setdefault(e["evidenceId"], cid)
    for part in ("summary", "next-evidence", "hypotheses", "priority", "diary"):
        save(f"/cases/{cid}/{part}")
    for name, path in (("report.html", f"/cases/{cid}/report.html?lang=en"), ("diary.html", f"/cases/{cid}/diary.html?lang=en"),
                       ("summary.txt", f"/cases/{cid}/summary.txt")):
        try:
            write(f"cases/{cid}/{name}", get(path), kind="text")
        except Exception as e:  # noqa: BLE001
            print(f"  ! {path}: {str(e)[:120]}")

# evidence ID → case, in 100 small buckets (for exhibits opened from anywhere)
buckets: dict[str, dict] = {}
for eid, cid in ev_case.items():
    buckets.setdefault(eid[-2:], {})[eid] = cid
for b, m in buckets.items():
    write(f"evidence/index/{b}.json", m)

# ------------------------------------------------------------------ 4. every person: dossier, temporal engine, alternates
print(f"▸ snapshot: {len(persons)} dossiers and time rivers")
for p in persons:
    pid = p["id"]
    for part in ("timeline", "feasibility", "identity-candidates", "history"):
        save(f"/persons/{pid}/{part}")
    main = (p.get("primarySuspectCases") or [None])[0] or (p.get("casesMentioned") or [None])[0]
    if main:
        save(f"/cases/{main}/hypotheses?personId={pid}")
    first = T.routine(pid, None)
    days = {}
    for d in first.get("availableDates") or ([first["date"]] if first.get("date") else []):
        r = T.routine(pid, d)
        days[d] = {k: v for k, v in r.items() if k not in ("personId", "date", "availableDates")}
    write(f"persons/{pid}/routine.json", {"defaultDate": first.get("date"), "availableDates": first.get("availableDates") or list(days),
                                          "days": days, "empty": {k: v for k, v in first.items() if k not in ("personId", "date")} if not days else None})

# ------------------------------------------------------------------ 5. network graph around every person and case
print("▸ snapshot: network graphs")
for focus in [p["id"] for p in persons] + [c["id"] for c in cases]:
    save(f"/graph/subgraph?focus={focus}&depth=2&limit=80")

# ------------------------------------------------------------------ 6. evidence ledger: what the browser needs to prove inclusion itself
print("▸ snapshot: evidence ledger (record hashes, anchors, agency keys)")
status = get("/ledger/status")
ingest = {(b["run_id"], b["sid"]): (b["block_index"], b["ts"]) for b in db.query(
    "SELECT DISTINCT ON (metadata->>'run_id', metadata->>'source_record_id') metadata->>'run_id' AS run_id, "
    "metadata->>'source_record_id' AS sid, block_index, ts FROM ledger_blocks WHERE event_type='INGEST' "
    "ORDER BY metadata->>'run_id', metadata->>'source_record_id', block_index")}
batches = []
for n, a in enumerate(db.query("SELECT DISTINCT ON (metadata->>'run_id', metadata->>'file') block_index, ts, metadata FROM ledger_blocks "
                                "WHERE event_type='ANCHOR' ORDER BY metadata->>'run_id', metadata->>'file', block_index DESC")):
    meta = a["metadata"]
    rows = db.query("SELECT source_record_id, content_sha256 FROM raw_records WHERE run_id=%s AND file_name=%s "
                    "ORDER BY source_record_id", (meta["run_id"], meta["file"]))
    for r in rows:
        r["block_index"], r["ts"] = ingest.get((meta["run_id"], r["source_record_id"]), (None, None))
    if len(rows) != meta["records"]:
        continue                                                   # a withdrawn intake batch: its records are gone
    ids = [r["source_record_id"] for r in rows]
    prefix = re.match(r"^(.*?)(\d+)$", ids[0]).group(1)
    width = len(ids[0]) - len(prefix)
    contiguous = all(i == f"{prefix}{k + 1:0{width}d}" for k, i in enumerate(ids))
    t_first = min(r["ts"] for r in rows if r["ts"]) if any(r["ts"] for r in rows) else a["ts"]
    sig = ledger._verify_sigs(meta)
    batches.append({"n": n, "prefix": prefix, "file": meta["file"], "runId": meta["run_id"], "records": meta["records"],
                    "merkleRoot": meta["merkleRoot"], "anchorBlock": a["block_index"], "anchorTs": a["ts"].isoformat(),
                    "signatures": meta["signatures"], "sigOkAtSnapshot": sig, "t0": t_first.isoformat(), "contiguous": contiguous})
    write(f"provenance/{n}.json", {"leaves": [r["content_sha256"] for r in rows], "ids": None if contiguous else ids,
                                   "blocks": [r["block_index"] for r in rows],
                                   "ms": [int((r["ts"] - t_first).total_seconds() * 1000) if r["ts"] else None for r in rows]})
write("provenance/batches.json", {"batches": batches, "nodes": status["nodes"], "quorum": status["quorum"], "built": built})

print(f"\n✓ {OUT}  ·  {stats['files']} snapshot files, {stats['bytes'] / 1e6:.1f} MB  ·  {stats['missing']} missing  ·  "
      f"{time.time() - t0:.0f}s")
