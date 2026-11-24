"""End-to-end smoke test of a running KRONOS (standard library only).

    python3 ci/smoke.py http://localhost:8000 [--wait 1800] [--llm]

Checks every feature the interface relies on, against a fresh install: cases and people, the summary, hypotheses with
alternates, next-best-evidence, impossible travel, identity, the graph and GNN, the evidence ledger (verify, Merkle proof,
chain), search, federated learning, case intake (check → register → withdraw), the website files, and optionally the
local AI assistant. Exits 1 if anything fails.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "http://localhost:8000"
WAIT = int(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 120
LLM = "--llm" in sys.argv
results = []


def call(path, method="GET", body=None, timeout=120):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if r.headers.get("content-type", "").startswith("application/json") else raw.decode("utf-8", "replace")


def check(name, fn):
    t = time.time()
    try:
        note = fn()
        results.append((True, name, note or "", time.time() - t))
    except Exception as e:  # noqa: BLE001
        msg = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else str(e)[:300]
        results.append((False, name, msg, time.time() - t))
    ok, _, note, dt = results[-1]
    print(f"{'PASS' if ok else 'FAIL'}  {name:<46} {dt:6.1f}s  {note}", flush=True)
    if not ok and os.environ.get("GITHUB_ACTIONS"):      # failures become public annotations on the run
        print(f"::error title=API check failed: {name}::{str(note).replace(chr(10), ' ').replace('%', ' ')[:300]}", flush=True)


def need(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ------------------------------------------------------------------ wait for the server
t0 = time.time()
while True:
    try:
        H = call("/api/health", timeout=10)
        break
    except Exception:  # noqa: BLE001
        if time.time() - t0 > WAIT:
            print(f"FAIL  server did not answer at {BASE} within {WAIT}s"); sys.exit(1)
        time.sleep(5)
print(f"server up after {time.time() - t0:.0f}s · LLM available: {H.get('llm', {}).get('available')}\n")

S = {}
check("80 cases (40 synthetic + 40 court records)", lambda: (S.__setitem__("cases", call("/api/cases")),
      need(len(S["cases"]) >= 80, len(S["cases"])), need(any(c["origin"] == "PUBLIC_RECORD" for c in S["cases"]), "no court records"),
      f"{len(S['cases'])} cases")[-1])
check("persons", lambda: (S.__setitem__("p", call("/api/persons")), need(len(S["p"]) > 200, len(S["p"])), f"{len(S['p'])} persons")[-1])
check("case summary (CASE002)", lambda: (S.__setitem__("s", call("/api/cases/CASE002/summary")), need(S["s"].get("conciseSummary"), "empty"),
      S["s"]["conciseSummary"][:60])[-1])
check("hypotheses + alternate hypotheses", lambda: (S.__setitem__("h", call("/api/cases/CASE002/hypotheses", timeout=300)),
      need(any(h["alternateHypotheses"] for h in S["h"]["hypotheses"]), "no alternates"),
      ", ".join(f"{h['personId']}:{h['comparison']['favours']}" for h in S["h"]["hypotheses"]))[-1])
check("priority + next best evidence", lambda: (need(call("/api/cases/CASE002/priority")["ranking"], "no ranking"),
      S.__setitem__("n", call("/api/cases/CASE002/next-evidence")), need(S["n"], "no recommendations"), S["n"][0]["evidenceType"])[-1])
check("impossible travel (P00024)", lambda: (S.__setitem__("f", call("/api/persons/P00024/feasibility")),
      need(any("IMPOSSIBLE" in json.dumps(x) for x in (S["f"].get("flags") or [])), "no impossible move"), f"{len(S['f']['flags'])} flags")[-1])
check("identity candidates (P00023 ↔ P00024)", lambda: (S.__setitem__("i", call("/api/persons/P00023/identity-candidates")),
      need(any("P00024" in (c["personA"], c["personB"]) for c in S["i"]), "pair missing"), f"{len(S['i'])} candidate(s)")[-1])
check("criminal-history linkage", lambda: f"{len(call('/api/persons/P00023/history').get('priorRecords', []))} prior record link(s)")
check("graph subgraph + GNN", lambda: (need(call("/api/graph/subgraph?focus=P00023")["nodes"], "empty graph"),
      str(call("/api/graph/gnn", timeout=300).get("comparison", ""))[:70])[-1])
check("temporal highlights + timeline", lambda: (need(call("/api/temporal/highlights")["travel"], "none"),
      need(call("/api/persons/P00024/timeline"), "empty"), "ok")[-1])
check("evidence ledger: verify + Merkle proof", lambda: (S.__setitem__("ev", call("/api/cases/CASE002/evidence")),
      S.__setitem__("eid", (S["ev"][0].get("id") or S["ev"][0].get("evidenceId")) if isinstance(S["ev"], list) else S["ev"]["evidence"][0]["evidenceId"]),
      need(call(f"/api/evidence/{S['eid']}/verify", "POST", {})["result"] == "VERIFIED", "not verified"),
      need(call(f"/api/evidence/{S['eid']}/proof").get("valid", True), "proof invalid"), S["eid"])[-1])
check("ledger chain valid", lambda: (S.__setitem__("l", call("/api/ledger/verify", timeout=300)), need(S["l"]["valid"], S["l"]), f"{S['l']['blocks']} blocks")[-1])
check("natural-language evidence search", lambda: f"{call('/api/search/evidence?q=cash%20deposits%20above%2040000&caseId=CASE002').get('total', '?')} matches")
check("federated learning report", lambda: (need(call("/api/federated/report"), "empty"), "ok")[-1])
check("case report + diary (HTML)", lambda: (need("<html" in call("/api/cases/CASE002/report.html").lower(), "no report"),
      need("<html" in call("/api/cases/CASE002/diary.html").lower(), "no diary"), "ok")[-1])


def intake():
    o = call("/api/intake/options")
    st = next(s for s in o["stations"] if s["name"] == "PS Karol Bagh")
    p = {"registration": {"policeStation": st["name"], "district": st["district"], "agencyId": st["agencyId"],
                          "firNumber": call(f"/api/intake/next-fir?station=PS%20Karol%20Bagh&year=2025")["firNumber"],
                          "registeredAt": "2025-04-02T10:00"},
         "offence": {"category": "Cheating", "sections": "BNS 318(4)", "priority": "MEDIUM", "title": "CI smoke test — Karol Bagh"},
         "occurrence": {"from": "2025-04-01T18:00", "place": "Karol Bagh Market, Delhi"},
         "complainant": {"name": "Ci Smoke Complainant", "phone": "9000000099", "isVictim": True},
         "accused": [{"name": "Gurpreet Singh Dhillon", "phone": "+91-8137098593"}],
         "narrative": "The complainant stated that the accused took Rs 50,000 on the promise of a job and stopped responding thereafter.",
         "officer": {"name": "CI Officer", "rank": "Inspector"}, "clientNow": time.strftime("%Y-%m-%dT%H:%M")}
    c = call("/api/intake/check", "POST", p)
    need(c["ok"], c["errors"]); need(c["matches"], "existing accused not recognised"); need(c["identifierHits"], "no cross-case hits")
    r = call("/api/cases", "POST", p, timeout=300)
    w = call(f"/api/cases/{r['caseId']}?reason=ci", "DELETE")
    need(w["withdrawn"], w)
    return f"{r['caseId']} registered in {r['seconds']}s and withdrawn"


check("case intake: check → register → withdraw", intake)
check("website (index + scripts)", lambda: (S.__setitem__("ix", call("/")), [need(x in S["ix"], f"{x} missing from index.html") for x in
      ("kronos-live.js", "kronos-intake.js", "kronos-workspace.js", "kronos-responsive.js", "kronos-temporal.js")], need(call("/kronos-intake.js"), "script not served"), "ok")[-1])

if LLM:
    check("local AI: search with embeddings", lambda: f"{len(call('/api/search?q=who%20received%20money%20from%20the%20accused&caseId=CASE002').get('results', []))} hits")
    check("local AI: grounded answer (CPU may take minutes)", lambda: (S.__setitem__("a", call("/api/assistant/query", "POST",
          {"query": "Why may P00019 not have been involved in CASE002?", "caseId": "CASE002", "personId": "P00019"}, timeout=1500)),
          need(S["a"].get("text") and "EVD-" in S["a"]["text"], S["a"].get("text", "")[:200]),
          f"{S['a']['meta'].get('latencyMs', 0) / 1000:.0f}s, model {S['a']['meta'].get('model')}")[-1])

bad = [r for r in results if not r[0]]
print(f"\n{len(results) - len(bad)}/{len(results)} checks passed")
sys.exit(1 if bad else 0)
