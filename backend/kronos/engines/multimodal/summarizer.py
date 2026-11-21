"""Automatic case summarisation.

generate_case_summary(case_id) fetches the case's records (via the case-intelligence
synthesis), and produces a structured JSON summary plus a readable TXT summary. Every
statement carries evidence IDs. A data hash over the underlying records detects when the
summary is stale and must be regenerated. An optional narrative paragraph is written by the
local LLM strictly from the structured summary (never from outside knowledge).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from ... import db
from ...config import settings
from ..llm import ollama
from . import case_intel


def data_hash(case_id: str) -> str:
    rows = db.query("SELECT source_record_id, content_sha256 FROM raw_records WHERE case_id=%s ORDER BY 1", (case_id,))
    c = db.query_one("SELECT updated_at FROM cases WHERE case_id=%s", (case_id,))
    h = hashlib.sha256()
    for r in rows:
        h.update(f"{r['source_record_id']}:{r['content_sha256']};".encode())
    h.update(str(c["updated_at"] if c else "").encode())
    return h.hexdigest()


def _money(x):
    return f"₹{x:,.0f}"


def build_summary(case_id: str) -> dict:
    I = case_intel.build(case_id)
    if not I:
        raise KeyError(case_id)
    o = I["overview"]
    ppl = I["people"]
    roles = {}
    for p in ppl:
        roles.setdefault(p["primaryRole"], []).append(p)
    fin, comm, loc = I["financial"], I["communication"], I["location"]
    acc = roles.get("PRINCIPAL_ACCUSED", []) + roles.get("ACCUSED", [])
    inc_ts = (o.get('incident_ts') or '')[:16].replace('T', ' ')
    where = ", ".join(x for x in (o.get('police_station'), o.get('district')) if x) or "a police station not stated"
    incident = (f"Incident recorded on {inc_ts}" if inc_ts else "Incident date not stated in the source") + \
        (f" at {o.get('incident_location')}" if o.get('incident_location') else "")
    concise = (f"{case_id} ({o.get('fir_number')}) — {o.get('offence_category')} registered at {where}. "
               f"{incident}. FIR records {len(acc)} accused "
               f"({', '.join(p['name'] + ' ' + p['personId'] for p in acc) or 'none named'}) and "
               f"{len([p for p in ppl if p['primaryRole'] != 'RECORD_SUBJECT'])} named persons in total. "
               f"{sum(I['recordCounts'].values())} records across {len(I['recordCounts'])} sources; "
               f"{fin['flaggedCount']} transactions flagged for review.")
    obs = [{"text": x["observation"], "evidenceIds": [e for f in x["facts"] for e in f["evidenceIds"]][:6],
            "independentSources": x["independentSources"]} for x in I["crossSourceObservations"]]
    narrative = [concise]
    if fin["passThroughChains"]:
        ch = fin["passThroughChains"][0]
        narrative.append(f"Money-flow records show funds received and forwarded within minutes (e.g. {ch['in']} → {ch['out']}, "
                         f"{ch['minutes']} min), a pattern that can indicate layering and requires verification.")
    if fin["structuring"]:
        s = fin["structuring"][0]
        narrative.append(f"{s['count']} transfers from {s['sender']} to {s['receiver']} each fell just below "
                         f"{_money(settings.fin_structuring_threshold)} (total {_money(s['total'])}).")
    if fin["fanIn"]:
        f = fin["fanIn"][0]
        narrative.append(f"Account {f['account']} received funds from {len(f['senders'])} different individuals within 14 days.")
    if comm["bursts"]:
        b = comm["bursts"][0]
        narrative.append(f"Communication between {b['persons'][0]} and {b['persons'][1]} spiked to {b['count']} contacts "
                         f"within 3 hours on {b['start'][:10]}.")
    if loc["namedPersonsElsewhere"]:
        e = loc["namedPersonsElsewhere"][0]
        narrative.append(f"Note: {e['personId']} has a record {e['distanceKm']} km from the incident location "
                         f"{abs(e['minutesFromIncident'])} min {'before' if e['minutesFromIncident'] < 0 else 'after'} the "
                         f"incident ({e['evidenceId']}), which may be exculpatory and needs verification.")
    s = {
        "caseId": case_id, "generatedAt": datetime.now().isoformat(timespec="seconds"), "dataHash": data_hash(case_id),
        "conciseSummary": concise,
        "detailedNarrative": " ".join(narrative),
        "chronology": I["keyEvents"],
        "people": [{"personId": p["personId"], "name": p["name"], "recordedRole": p["primaryRole"],
                    "roleSource": p["roles"][0]["method"], "evidenceIds": p["evidenceIds"][:4]} for p in ppl],
        "organisations": I["organisations"],
        "financialSummary": {"totalVolume": fin["totalVolume"], "transactions": fin["transactions"],
                             "flagged": [{"evidenceId": f["evidenceId"], "amount": f["amount"], "timestamp": f["timestamp"],
                                          "methods": f["methods"], "reasons": f["reasons"],
                                          "alternativeExplanation": f.get("alternativeExplanation")} for f in fin["flagged"][:15]],
                             "structuring": fin["structuring"], "fanIn": fin["fanIn"],
                             "passThroughChains": fin["passThroughChains"][:10]},
        "communicationSummary": {"pairs": comm["pairs"][:10], "aroundIncident": comm["aroundIncident"],
                                 "bursts": comm["bursts"], "importantMessages": comm["importantMessages"][:12]},
        "locationSummary": {"nearIncident": loc["nearIncident"][:12], "namedPersonsElsewhere": loc["namedPersonsElsewhere"][:8],
                            "sharedPlacesAcrossCases": loc["sharedPlacesAcrossCases"][:8],
                            "coPresence": [c for c in loc["coPresence"] if c["communicationsWithin48h"]][:8]},
        "suspiciousObservations": obs,
        "travelInconsistencies": [{"personId": t["personId"], "verdict": t["verdict"], "first": t["first"]["evidenceId"],
                                   "second": t["second"]["evidenceId"], "distanceKm": t["distanceKm"],
                                   "elapsedMinutes": t["elapsedMinutes"]} for t in I["travelInconsistencies"]],
        "importantEvidence": sorted({e for x in obs for e in x["evidenceIds"]} |
                                    {e for k in I["keyEvents"] for e in k["evidenceIds"]})[:40],
        "missingInformation": I["missingInformation"],
        "uncertainties": I["uncertainties"],
        "recordCounts": I["recordCounts"], "sourceReliability": I["sourceReliability"],
        "disclaimer": I["disclaimer"],
    }
    return s


def render_txt(s: dict) -> str:
    L = ["=" * 78, f"KRONOS CASE SUMMARY — {s['caseId']}", f"Generated {s['generatedAt']}  |  data hash {s['dataHash'][:16]}",
         "=" * 78, "", "1. CONCISE SUMMARY", s["conciseSummary"], "", "2. NARRATIVE", s.get("llmNarrative") or s["detailedNarrative"],
         "", "3. CHRONOLOGY"]
    L += [f"  {e['timestamp']}  {e['event']}  [{', '.join(e['evidenceIds'][:3])}]" for e in s["chronology"]]
    L += ["", "4. PEOPLE (recorded roles — not findings of guilt)"]
    L += [f"  {p['personId']}  {p['name']:<28} {p['recordedRole']:<18} via {p['roleSource']}  [{', '.join(p['evidenceIds'])}]"
          for p in s["people"]]
    fs = s["financialSummary"]
    L += ["", "5. FINANCIAL ACTIVITY", f"  {fs['transactions']} transactions, total ₹{fs['totalVolume']:,.0f}; {len(fs['flagged'])} flagged"]
    L += [f"  - {f['evidenceId']} ₹{f['amount']:,.0f} {f['timestamp']}: {'; '.join(f['reasons'][:2])}"
          + (f" (alt.: {f['alternativeExplanation']})" if f.get("alternativeExplanation") else "") for f in fs["flagged"]]
    cs = s["communicationSummary"]
    L += ["", "6. COMMUNICATION"]
    L += [f"  - {p['names'][0]} ↔ {p['names'][1]}: {p['total']} contacts ({p['first']} – {p['last']})" for p in cs["pairs"][:8]]
    if cs["aroundIncident"]:
        a = cs["aroundIncident"]
        L.append(f"  Around incident: {a['count']} contacts (baseline ≈{a['expectedFromBaseline']}), {a['betweenNamedPersons']} between named persons")
    L += [f"  * {m['evidenceId']} {m['timestamp']}: \"{m['text'][:90]}\" — {'; '.join(m['reasons'])}" for m in cs["importantMessages"][:6]]
    ls = s["locationSummary"]
    L += ["", "7. LOCATION"]
    L += [f"  - near incident: {x['personId']} {x['distanceKm']} km, {x['minutesFromIncident']} min ({x['evidenceId']})" for x in ls["nearIncident"][:8]]
    L += [f"  - elsewhere: {x['personId']} at {x['location']} ({x['distanceKm']} km away, {x['evidenceId']})" for x in ls["namedPersonsElsewhere"][:5]]
    L += ["", "8. OBSERVATIONS REQUIRING VERIFICATION"]
    L += [f"  - {o['text']} [{', '.join(o['evidenceIds'][:4])}]" for o in s["suspiciousObservations"]]
    L += [f"  - Location inconsistency {t['personId']}: {t['verdict']} ({t['first']} → {t['second']}, {t['distanceKm']} km in {t['elapsedMinutes']} min)"
          for t in s["travelInconsistencies"]]
    L += ["", "9. MISSING INFORMATION"] + [f"  - {m['personId'] or ''} {m['gap']}" for m in s["missingInformation"]]
    L += ["", "10. UNCERTAINTIES"] + [f"  - {u}" for u in s["uncertainties"]]
    L += ["", s["disclaimer"]]
    return "\n".join(L)


LLM_SYSTEM = ("You are KRONOS, writing a neutral case narrative for police investigators. Use ONLY the JSON facts "
              "provided. Cite evidence IDs in square brackets after each fact, e.g. [EVD-CDR000123]. Do not speculate, "
              "do not assign guilt, use 'recorded as accused' wording, and mention key uncertainties. 150-220 words.")


def generate_case_summary(case_id: str, use_llm: bool = False, force: bool = False) -> dict:
    current = db.query_one("SELECT data_hash, summary_json, llm_narrative FROM case_summaries WHERE case_id=%s", (case_id,))
    h = data_hash(case_id)
    if current and current["data_hash"] == h and not force and (current["llm_narrative"] or not use_llm):
        return current["summary_json"]
    s = build_summary(case_id)
    narrative, model = None, None
    if use_llm:
        facts = {k: s[k] for k in ("conciseSummary", "chronology", "people", "suspiciousObservations", "missingInformation",
                                   "uncertainties")}
        facts["financial"] = {"flagged": s["financialSummary"]["flagged"][:6], "structuring": s["financialSummary"]["structuring"][:2]}
        try:
            narrative = ollama.chat([{"role": "system", "content": LLM_SYSTEM},
                                     {"role": "user", "content": json.dumps(facts, default=str)[:14000]}], max_tokens=420)
            model = ollama.model_name()
            s["llmNarrative"] = narrative
        except ollama.LLMUnavailable:
            s["llmNarrativeError"] = "local LLM unavailable; deterministic narrative used"
    txt = render_txt(s)
    db.execute("INSERT INTO case_summaries (case_id, data_hash, summary_json, summary_txt, llm_narrative, llm_model, generated_at) "
               "VALUES (%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (case_id) DO UPDATE SET data_hash=EXCLUDED.data_hash, "
               "summary_json=EXCLUDED.summary_json, summary_txt=EXCLUDED.summary_txt, llm_narrative=EXCLUDED.llm_narrative, "
               "llm_model=EXCLUDED.llm_model, generated_at=now()",
               (case_id, s["dataHash"], db.Json(s), txt, narrative, model))
    (settings.summaries_dir / f"{case_id}.json").write_text(json.dumps(s, indent=1, default=str))
    (settings.summaries_dir / f"{case_id}.txt").write_text(txt)
    return s


def is_stale(case_id: str) -> bool:
    cur = db.query_one("SELECT data_hash FROM case_summaries WHERE case_id=%s", (case_id,))
    return not cur or cur["data_hash"] != data_hash(case_id)
