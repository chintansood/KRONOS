"""KRONOS REST API (FastAPI). Run: uvicorn kronos.api.main:app --port 8000"""
from __future__ import annotations

import json
import re
from datetime import datetime

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from .. import db
from ..config import settings
from ..engines.federated import fedavg
from ..engines.graph import analytics, gnn
from ..engines.identity import history, resolver
from ..engines.intelligence import hypothesis, next_evidence, priority
from ..engines.llm import assistant, ollama
from ..engines.multimodal import case_intel, financial, summarizer
from ..engines.provenance import ledger
from ..engines.store import data_version, events
from ..engines.temporal import timeline, travel
from . import serializers as S

class CleanJSONResponse(JSONResponse):
    """JSON response that converts pandas/numpy NaN, inf and scalar types into valid JSON."""
    def render(self, content) -> bytes:
        return json.dumps(db.clean(content), default=str, ensure_ascii=False).encode("utf-8")


app = FastAPI(title="KRONOS Investigation Intelligence API", version="1.0.0", default_response_class=CleanJSONResponse,
              description="Backend for the KRONOS investigator interface. All analytical outputs are investigative "
                          "aids with evidence references — not findings of guilt.")
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins) + ["*"], allow_methods=["*"], allow_headers=["*"])


def _404(what):
    raise HTTPException(404, f"{what} not found")


def _bust_ui_cache():
    db.execute("DELETE FROM analysis_cache WHERE cache_key LIKE 'ui_%' OR cache_key LIKE 'case_intel:%'")


# ------------------------------------------------------------------ health & stats
@app.get("/api/health")
def health():
    r = db.query_one("SELECT (SELECT count(*) FROM events) events, (SELECT count(*) FROM cases) cases, "
                     "(SELECT count(*) FROM persons) persons, (SELECT count(*) FROM ledger_blocks) ledger_blocks, "
                     "(SELECT count(*) FROM doc_chunks WHERE embedding IS NOT NULL) embedded_chunks")
    return {"status": "ok", "dataVersion": data_version(), "llm": {"model": ollama.model_name(), "backend": settings.llm_backend, "available": ollama.available()}, **r}


@app.get("/api/stats")
def stats():
    df = events()
    cs = S.cases()
    return {"cases": len(cs), "activeCases": sum(c["status"] == "ACTIVE" for c in cs), "persons": len(S.persons()),
            "records": int(len(df)), "recordsByModality": df.modality.value_counts().to_dict(),
            "flaggedTransactions": len(financial.analysis()["flagged"]),
            "travelInconsistencies": len(travel.detect_all()),
            "identityCandidates": db.query_one("SELECT count(*) n FROM identity_candidates WHERE band IN ('HIGH','MEDIUM')")["n"],
            "ingestionIssues": db.query("SELECT severity, count(*) n FROM ingestion_issues GROUP BY 1")}


@app.get("/api/ingestion/report")
def ingestion_report():
    run = db.query_one("SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT 1")
    issues = db.query("SELECT modality, field, issue, severity, count(*) n FROM ingestion_issues GROUP BY 1,2,3,4 ORDER BY n DESC")
    return {"run": run, "issues": issues}


# ------------------------------------------------------------------ cases
@app.get("/api/cases")
def list_cases():
    return S.cases()


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    c = next((c for c in S.cases() if c["id"] == case_id.upper()), None)
    return c or _404("case")


class CaseIn(BaseModel):
    id: str | None = None
    title: str
    offenceCategory: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    firNumber: str | None = None
    policeStation: str | None = None
    district: str | None = None
    leadInvestigator: str | None = None


@app.post("/api/cases")
@app.put("/api/cases/{case_id}")
def upsert_case(body: CaseIn, case_id: str | None = None):
    cid = (case_id or body.id or "").upper()
    exists = cid and db.query_one("SELECT case_id FROM cases WHERE case_id=%s", (cid,))
    if exists:
        db.execute("""UPDATE cases SET title=%s, offence_category=COALESCE(%s, offence_category), description=COALESCE(%s, description),
                      status=COALESCE(%s, status), priority=COALESCE(%s, priority), fir_number=COALESCE(%s, fir_number),
                      police_station=COALESCE(%s, police_station), district=COALESCE(%s, district),
                      lead_investigator=COALESCE(%s, lead_investigator), updated_at=now() WHERE case_id=%s""",
                   (body.title, body.offenceCategory, body.description, body.status, body.priority, body.firNumber,
                    body.policeStation, body.district, body.leadInvestigator, cid))
    else:
        n = db.query_one("SELECT count(*) n FROM cases")["n"]
        cid = cid or f"CASE{n + 1:03d}"
        while db.query_one("SELECT 1 FROM cases WHERE case_id=%s", (cid,)):
            n += 1; cid = f"CASE{n + 1:03d}"
        db.execute("""INSERT INTO cases (case_id, title, offence_category, description, status, priority, fir_number, police_station,
                      district, lead_investigator, is_custom, registration_ts) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,now())""",
                   (cid, body.title, body.offenceCategory, body.description, body.status or "ACTIVE", body.priority or "MEDIUM",
                    body.firNumber, body.policeStation, body.district, body.leadInvestigator))
    ledger.append("CASE_EDIT", None, None, "investigator", {"caseId": cid, "fields": body.model_dump(exclude_none=True),
                                                            "action": "UPDATE" if exists else "CREATE"})
    _bust_ui_cache()
    return get_case(cid)


@app.get("/api/cases/{case_id}/evidence")
def case_evidence(case_id: str, modality: str | None = None, limit: int = 2000):
    df = events()
    sel = df[df.case_id == case_id.upper()]
    if modality:
        m = {"COMMUNICATION": "SOCIAL"}.get(modality.upper(), modality.upper())
        sel = sel[sel.modality == m]
    sel = sel.sort_values("ts", na_position="last").head(limit)
    return [S.evidence(r) for r in sel.to_dict("records")]


@app.get("/api/cases/{case_id}/intelligence")
async def case_intelligence(case_id: str):
    r = await run_in_threadpool(case_intel.get, case_id.upper())
    return r or _404("case")


@app.get("/api/cases/{case_id}/summary")
async def case_summary(case_id: str, regenerate: bool = False, llm: bool = False):
    try:
        s = await run_in_threadpool(summarizer.generate_case_summary, case_id.upper(), llm, regenerate)
    except KeyError:
        _404("case")
    return {**s, "stale": summarizer.is_stale(case_id.upper())}


@app.get("/api/cases/{case_id}/summary.txt", response_class=PlainTextResponse)
def case_summary_txt(case_id: str):
    summarizer.generate_case_summary(case_id.upper())
    r = db.query_one("SELECT summary_txt FROM case_summaries WHERE case_id=%s", (case_id.upper(),))
    return r["summary_txt"] if r else _404("summary")


@app.get("/api/cases/{case_id}/report")
async def case_report_json(case_id: str, lang: str = "en", llm: bool = False):
    from ..engines.reports import case_report
    try:
        return await run_in_threadpool(case_report.build, case_id.upper(), lang, llm)
    except KeyError:
        _404("case")


@app.get("/api/cases/{case_id}/report.html", response_class=HTMLResponse)
async def case_report_html(case_id: str, lang: str = "en", llm: bool = False):
    from ..engines.reports import case_report
    try:
        R = await run_in_threadpool(case_report.build, case_id.upper(), lang, llm)
    except KeyError:
        _404("case")
    return HTMLResponse(case_report.render_html(R))


@app.get("/api/cases/{case_id}/diary")
async def case_diary(case_id: str):
    from ..engines.reports import diary
    try:
        return await run_in_threadpool(diary.build, case_id.upper())
    except KeyError:
        _404("case")


@app.get("/api/cases/{case_id}/diary.html", response_class=HTMLResponse)
async def case_diary_html(case_id: str, lang: str = "en"):
    from ..engines.reports import case_report, diary
    try:
        D = await run_in_threadpool(diary.build, case_id.upper())
    except KeyError:
        _404("case")
    return HTMLResponse(await run_in_threadpool(case_report.render_diary_html, D, lang))


class DiaryIn(BaseModel):
    text: str
    entryTs: str | None = None
    place: str | None = None
    author: str = "investigator"
    evidenceIds: list[str] = []


@app.post("/api/cases/{case_id}/diary/entries")
def case_diary_add(case_id: str, body: DiaryIn):
    from ..engines.reports import diary
    if not body.text.strip():
        raise HTTPException(400, "entry text is required")
    return diary.add_entry(case_id.upper(), body.text.strip(), body.entryTs, body.place, body.author, body.evidenceIds)


@app.get("/api/cases/{case_id}/financial")
def case_financial(case_id: str):
    I = case_intel.get(case_id.upper())
    return I["financial"] if I else _404("case")


@app.get("/api/cases/{case_id}/priority")
def case_priority(case_id: str):
    return priority.assess(case_id.upper()) or _404("case")


@app.get("/api/cases/{case_id}/hypotheses")
def case_hypotheses(case_id: str, personId: str | None = None):
    return hypothesis.analyse(case_id.upper(), personId) or _404("case")


@app.get("/api/cases/{case_id}/next-evidence")
def case_next_evidence(case_id: str):
    return next_evidence.recommend(case_id.upper())


class StatusIn(BaseModel):
    status: str


@app.patch("/api/cases/{case_id}/next-evidence/{request_id}")
def update_next_evidence(case_id: str, request_id: str, body: StatusIn):
    try:
        return next_evidence.set_status(case_id.upper(), request_id, body.status)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ persons
@app.get("/api/persons")
def list_persons():
    return S.persons()


@app.get("/api/persons/{person_id}")
def get_person(person_id: str):
    p = next((p for p in S.persons() if p["id"] == person_id.upper()), None)
    return p or _404("person")


@app.get("/api/persons/{person_id}/timeline")
def person_timeline(person_id: str, caseId: str | None = None, start: str | None = None, end: str | None = None,
                    modality: str | None = None, limit: int = 600):
    return timeline.timeline(person_id.upper(), caseId, start, end, modality, limit)


@app.get("/api/temporal/highlights")
def temporal_highlights(limit: int = 8):
    """Who to look at first in the temporal engine: people with travel-feasibility flags, and the most active subjects."""
    def compute():
        names = {r["person_id"]: r["display_name"] for r in db.query("SELECT person_id, display_name FROM persons")}
        by: dict[str, list[str]] = {}
        for f in travel.detect_all():
            by.setdefault(f["personId"], []).append(f["verdict"])
        flagged = sorted(({"personId": p, "name": names.get(p, p), "flags": len(v), "impossible": v.count("IMPOSSIBLE"),
                           "air": v.count("REQUIRES_AIR_TRAVEL"), "simultaneous": v.count("SIMULTANEOUS")} for p, v in by.items()),
                         key=lambda x: (-x["impossible"], -x["simultaneous"], -x["flags"]))
        active = [{"personId": r["person_id"], "name": names.get(r["person_id"], r["person_id"]), "records": r["n"]}
                  for r in db.query("SELECT person_id, count(*) n FROM events WHERE person_id IS NOT NULL AND modality <> 'FIR' "
                                    "GROUP BY 1 ORDER BY 2 DESC LIMIT 40")]
        return {"travel": flagged, "active": active}
    from ..engines.store import cached
    out = cached("temporal_highlights:v1", compute)
    return {"travel": out["travel"][:limit], "active": out["active"][:limit]}


@app.get("/api/persons/{person_id}/routine")
def person_routine(person_id: str, date: str | None = None):
    return timeline.routine(person_id.upper(), date)


@app.get("/api/persons/{person_id}/travel")
def person_travel(person_id: str, maxGroundKmh: float | None = None, maxAirKmh: float | None = None):
    return travel.detect(person_id.upper(), max_ground=maxGroundKmh, max_air=maxAirKmh)


@app.get("/api/persons/{person_id}/feasibility")
def person_feasibility(person_id: str, maxGroundKmh: float | None = None, maxAirKmh: float | None = None):
    return travel.feasibility(person_id.upper(), max_ground=maxGroundKmh, max_air=maxAirKmh)


@app.get("/api/persons/{person_id}/history")
async def person_history(person_id: str):
    return await run_in_threadpool(history.person_history, person_id.upper())


@app.get("/api/persons/{person_id}/identity-candidates")
def person_identity(person_id: str):
    return resolver.list_candidates(person_id=person_id.upper())


@app.get("/api/persons/{person_id}/financial")
def person_financial(person_id: str):
    pid = person_id.upper()
    return {"accounts": financial.account_summary(person_id=pid),
            "flagged": [f for f in financial.analysis()["flagged"] if pid in (f["sender"], f["receiver"])]}


# ------------------------------------------------------------------ identity
@app.get("/api/identity/candidates")
def identity_candidates(band: str | None = None, status: str | None = None, limit: int = 100):
    return resolver.list_candidates(band=band, status=status, limit=limit)


class ReviewIn(BaseModel):
    decision: str
    reviewer: str = "investigator"
    note: str = ""


@app.post("/api/identity/candidates/{candidate_id}/review")
def identity_review(candidate_id: str, body: ReviewIn):
    try:
        out = resolver.review(candidate_id, body.decision, body.reviewer, body.note)
    except KeyError:
        _404("candidate")
    except ValueError as e:
        raise HTTPException(400, str(e))
    _bust_ui_cache()
    return out


@app.post("/api/history/links/{link_id}/review")
def history_review(link_id: str, body: ReviewIn):
    try:
        out = history.review(link_id, body.decision, body.reviewer, body.note)
    except KeyError:
        _404("history link")
    except ValueError as e:
        raise HTTPException(400, str(e))
    _bust_ui_cache()
    return out


# ------------------------------------------------------------------ graph
@app.get("/api/graph/subgraph")
def graph_subgraph(focus: str | None = None, depth: int = 2, limit: int = 90, includeLocations: bool = False):
    return analytics.subgraph(focus.upper() if focus and re.fullmatch(r"(p|case)\d+", focus, re.I) else focus, depth, limit, includeLocations)


@app.get("/api/graph/node/{node_id:path}")
def graph_node(node_id: str):
    return analytics.node_detail(node_id) or _404("node")


@app.get("/api/graph/path")
def graph_path(source: str, target: str, includeLocations: bool = False):
    return analytics.path(source, target, exclude_types=("CASE",) if includeLocations else ("LOCATION", "CASE"))


@app.get("/api/graph/metrics")
def graph_metrics():
    m = analytics.metrics()
    return {"communities": m["communities"], "method": m["method"],
            "topBetweenness": sorted(m["nodes"].values(), key=lambda x: -x["betweenness"])[:25]}


@app.get("/api/graph/cross-case")
def graph_cross_case(limit: int = 50):
    return analytics.cross_case()[:limit]


@app.get("/api/graph/hidden-links")
def graph_hidden_links():
    return analytics.hidden_links()


@app.get("/api/graph/gnn")
def graph_gnn():
    return gnn.report()


# ------------------------------------------------------------------ evidence & provenance
@app.get("/api/evidence/{evidence_id}")
def get_evidence(evidence_id: str, actor: str = "investigator"):
    row = db.query_one("SELECT e.*, r.raw, r.content_sha256 FROM events e JOIN raw_records r USING (source_record_id) WHERE e.evidence_id=%s",
                       (evidence_id.upper(),))
    if not row:
        _404("evidence")
    blk = db.query_one("SELECT block_index FROM ledger_blocks WHERE evidence_id=%s AND event_type='INGEST'", (row["evidence_id"],))
    ledger.append("ACCESS", row["evidence_id"], None, actor, {"via": "api"})
    return S.evidence(row, raw=row["raw"], ledger_info={"sha256AtIngestion": row["content_sha256"],
                                                         "ledgerBlock": blk["block_index"] if blk else None})


@app.post("/api/evidence/{evidence_id}/verify")
def verify_evidence(evidence_id: str, actor: str = "investigator"):
    return ledger.verify_evidence(evidence_id.upper(), actor)


@app.get("/api/evidence/{evidence_id}/proof")
def evidence_proof(evidence_id: str):
    return ledger.inclusion_proof(evidence_id.upper())


@app.get("/api/ledger/status")
def ledger_status():
    return ledger.status()


@app.get("/api/evidence/{evidence_id}/history")
def evidence_history(evidence_id: str):
    return ledger.history(evidence_id.upper())


@app.get("/api/ledger/verify")
def verify_ledger():
    return ledger.verify_chain()


# ------------------------------------------------------------------ alerts & search
@app.get("/api/alerts")
def alerts(limit: int = 30):
    out = []
    for f in travel.detect_all():
        if f["verdict"] in ("IMPOSSIBLE", "SIMULTANEOUS_DIFFERENT_PLACES"):
            out.append({"id": f"ALT-TRV-{f['second']['evidenceId']}", "type": "NEW_DEVICE", "title": "Location inconsistency (impossible travel)",
                        "description": f"{f['personId']}: {f['first']['location']} → {f['second']['location']}, {f['distanceKm']} km in "
                                       f"{f['elapsedMinutes']} min. Possible shared/cloned device or data error — verify.",
                        "ts": f["second"]["timestamp"], "severity": "CRITICAL", "targetType": "PERSON", "targetId": f["personId"]})
    for c in resolver.list_candidates(band="HIGH", status="PENDING", limit=10):
        out.append({"id": f"ALT-{c['candidateId']}", "type": "SIM_SWAP", "title": "Possible duplicate identity — review required",
                    "description": f"{c['nameA']} ({c['personA']}) and {c['nameB']} ({c['personB']}) may be the same person "
                                   f"(score {c['score']}). Not merged; awaiting investigator review.",
                    "ts": c["updatedAt"][:16].replace("T", " "), "severity": "WARNING", "targetType": "PERSON", "targetId": c["personA"]})
    for f in [f for f in financial.analysis()["flagged"] if len(f["methods"]) >= 2][:10]:
        out.append({"id": f"ALT-FIN-{f['evidenceId']}", "type": "FINANCIAL_SURGE", "title": f"Flagged transaction ₹{f['amount']:,.0f}",
                    "description": f"{f['caseId']}: {'; '.join(f['reasons'][:2])}", "ts": f["timestamp"], "severity": "WARNING",
                    "targetType": "EVIDENCE", "targetId": f["evidenceId"]})
    for b in timeline.colocations():
        if b["communicationsWithin48h"] >= 3 and len(out) < limit * 2:
            out.append({"id": f"ALT-COL-{b['evidenceIds'][0]}", "type": "RENDEZVOUS", "title": "Corroborated co-presence",
                        "description": f"{b['persons'][0]} and {b['persons'][1]} recorded together at {b['location']} "
                                       f"({b['communicationsWithin48h']} contacts within 48 h).",
                        "ts": b["timestamp"], "severity": "INFO", "targetType": "PERSON", "targetId": b["persons"][0]})
    out.sort(key=lambda a: a["ts"], reverse=True)
    return out[:limit]


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    ql = q.strip().lower()
    digits = re.sub(r"\D", "", q)
    persons = [p for p in S.persons() if ql in p["id"].lower() or ql in p["name"].lower() or (p["alias"] and ql in p["alias"].lower())
               or (len(digits) >= 5 and any(digits in re.sub(r"\D", "", x) for x in p["contactNumbers"]))
               or any(ql == a.lower() for a in p["bankAccounts"] + p["associatedDevices"])]
    cases = [c for c in S.cases() if ql in c["id"].lower() or ql in c["title"].lower() or ql in c["offenceCategory"].lower()
             or ql in (c["firNumber"] or "").lower() or ql in (c["district"] or "").lower()]
    ev = db.query("SELECT evidence_id FROM events WHERE evidence_id ILIKE %s LIMIT 5", (f"%{q.strip()}%",)) if len(ql) >= 6 else []
    return {"persons": persons[:15], "cases": cases[:15], "evidenceIds": [e["evidence_id"] for e in ev]}


# ------------------------------------------------------------------ assistant
class Turn(BaseModel):
    role: str
    text: str


class AskIn(BaseModel):
    query: str
    mode: str = "ASSISTANCE"
    caseId: str | None = None
    personId: str | None = None
    modality: str | None = None
    history: list[Turn] = []
    lang: str | None = None


@app.post("/api/assistant/query")
async def ask(body: AskIn):
    return await run_in_threadpool(assistant.answer, body.query, body.mode, body.caseId, body.personId, body.modality,
                                   [t.model_dump() for t in body.history][-8:], body.lang)


@app.get("/api/search/evidence")
async def evidence_search(q: str = Query(..., min_length=2), caseId: str | None = None, personId: str | None = None,
                          limit: int = 40, lang: str | None = None):
    from ..engines.llm import language, search as evsearch
    q_en = q
    if language.detect(q) != "en":
        try:
            q_en = await run_in_threadpool(language.to_english, q)
        except Exception:  # noqa: BLE001
            q_en = q
    out = await run_in_threadpool(evsearch.search, q_en, caseId, personId, limit)
    out["originalQuery"] = q
    return out


# ------------------------------------------------------------------ federated learning
@app.get("/api/federated/report")
def federated_report():
    return fedavg.report()


class FedIn(BaseModel):
    rounds: int = 25
    aggregator: str = "fedavg"
    poisonedAgency: str | None = None
    noiseStd: float = 0.0


@app.post("/api/federated/run")
async def federated_run(body: FedIn):
    gt_file = settings.generated_dir / "ground_truth.json"
    if not gt_file.exists():
        raise HTTPException(400, "synthetic ground truth not found — federated simulation requires generated data")
    gt = json.loads(gt_file.read_text())
    return await run_in_threadpool(fedavg.run, gt, body.rounds, body.aggregator, 5.0, body.noiseStd, body.poisonedAgency)



# ---------------------------------------------------------------------------- hosting: access code + built website
# Enabled only when KRONOS_ACCESS_CODE / KRONOS_STATIC_DIR are set (scripts/host.sh). Every path — website, API and
# the API docs — sits behind the access code; the cookie holds a hash of the code, never the code itself.
import asyncio as _asyncio
import hashlib as _hashlib
import hmac as _hmac
from pathlib import Path as _Path
from urllib.parse import parse_qs as _parse_qs, quote as _quote

from fastapi import Request as _Request
from fastapi.responses import RedirectResponse as _Redirect

_ACCESS_TOKEN = _hashlib.sha256(f"kronos-access:{settings.access_code}".encode()).hexdigest() if settings.access_code else None
_OPEN_PATHS = {"/__login", "/favicon.svg"}


def _safe_next(n: str | None) -> str:
    n = (n or "/").strip()
    return n if n.startswith("/") and not n.startswith("//") and "\\" not in n else "/"


_LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KRONOS — access</title><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:Inter,system-ui,sans-serif;color:#30251F;
  background:radial-gradient(ellipse at 50% 40%,#FBEBD3,#F2E2C8 60%,#EAD5B4)}
.card{width:min(380px,88vw);text-align:center;padding:40px 34px;background:rgba(252,248,241,.85);border:1px solid rgba(198,154,85,.4);border-radius:22px;
  box-shadow:0 1px 0 #fff inset,0 30px 60px -30px rgba(48,37,31,.45)}
h1{font-family:'Cormorant Garamond',Georgia,serif;font-weight:500;font-size:44px;letter-spacing:.1em;margin:0}
p{font-size:13px;color:#7d6a58;margin:8px 0 26px;letter-spacing:.04em}
input{width:100%;box-sizing:border-box;padding:13px 18px;border-radius:999px;border:1px solid rgba(198,154,85,.55);background:#fffdf8;font:inherit;
  font-size:15px;text-align:center;letter-spacing:.12em;outline:none}input:focus{border-color:#B96D50;box-shadow:0 0 0 4px rgba(185,109,80,.15)}
button{margin-top:14px;width:100%;padding:13px;border:0;border-radius:999px;color:#fff;font:600 12px Inter,sans-serif;letter-spacing:.18em;cursor:pointer;
  background:linear-gradient(135deg,#C47A5B,#A65A3F);box-shadow:0 14px 30px -14px rgba(166,90,63,.9)}button:hover{filter:brightness(1.06)}
.err{color:#a2452a;font-size:12.5px;margin-top:14px}.note{font-size:11px;color:#9a8670;margin-top:22px}
</style></head><body><form class="card" method="post" action="/__login">
<h1>KRONOS</h1><p>CONNECTING EVIDENCE · RECONSTRUCTING TRUTH</p>
<input type="hidden" name="next" value="__NEXT__">
<input name="code" type="password" placeholder="Access code" autocomplete="current-password" autofocus required>
<button type="submit">ENTER KRONOS →</button>__ERR__
<div class="note">Investigation prototype · synthetic and pseudonymised data · local AI</div></form></body></html>"""


@app.middleware("http")
async def _access_gate(request: _Request, call_next):
    if not _ACCESS_TOKEN or request.url.path in _OPEN_PATHS:
        return await call_next(request)
    if _hmac.compare_digest(request.cookies.get("kronos_access", ""), _ACCESS_TOKEN):
        return await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path in ("/docs", "/openapi.json", "/redoc"):
        return JSONResponse({"detail": "KRONOS access code required"}, status_code=401)
    return _Redirect(f"/__login?next={_quote(request.url.path)}", status_code=303)


@app.get("/__login", response_class=HTMLResponse, include_in_schema=False)
def _login_page(next: str = "/", error: int = 0):
    import html as _html
    return HTMLResponse(_LOGIN_HTML.replace("__NEXT__", _html.escape(_safe_next(next)))
                        .replace("__ERR__", '<div class="err">That code is not right — please try again.</div>' if error else ""))


@app.post("/__login", include_in_schema=False)
async def _login(request: _Request):
    form = _parse_qs((await request.body()).decode("utf-8", "replace"))
    code, nxt = (form.get("code") or [""])[0], _safe_next((form.get("next") or ["/"])[0])
    if not _ACCESS_TOKEN or not _hmac.compare_digest(
            _hashlib.sha256(f"kronos-access:{code}".encode()).hexdigest(), _ACCESS_TOKEN):
        await _asyncio.sleep(0.8)            # slow down guessing
        return _Redirect(f"/__login?error=1&next={_quote(nxt)}", status_code=303)
    resp = _Redirect(nxt, status_code=303)
    resp.set_cookie("kronos_access", _ACCESS_TOKEN, max_age=30 * 86400, httponly=True, samesite="lax",
                    secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https")
    return resp


if settings.static_dir and _Path(settings.static_dir).is_dir():
    from fastapi.staticfiles import StaticFiles as _StaticFiles
    app.mount("/", _StaticFiles(directory=settings.static_dir, html=True), name="site")   # after every /api route
