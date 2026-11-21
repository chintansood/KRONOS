"""CDR + social-media communication analysis for a case.

Frequent communication is reported as a pattern, never as evidence of criminal activity;
messages are marked 'important' only for objective reasons (they reference identifiers,
amounts or places tied to the case, or fall in the incident window between named persons)
— never because of isolated keywords.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

from ... import db
from ..store import events
from ..temporal.timeline import bursts


def _names():
    return {r["person_id"]: r["display_name"] for r in db.query("SELECT person_id, display_name FROM persons")}


def analyse_case(case_id: str, incident_ts=None, named: set | None = None) -> dict:
    df = events()
    c = df[(df.case_id == case_id) & df.modality.isin(["CDR", "SOCIAL"]) & df.ts.notna()]
    names = _names()
    named = named or set()
    # ---- pair statistics -------------------------------------------------------------
    pairs = defaultdict(lambda: {"calls": 0, "sms": 0, "messages": 0, "durationSec": 0, "first": None, "last": None,
                                 "evidenceIds": []})
    for r in c.itertuples():
        if not isinstance(r.entity_id_2, str):
            continue
        k = tuple(sorted((r.person_id, r.entity_id_2)))
        p = pairs[k]
        if r.modality == "CDR":
            p["sms" if r.event_type == "SMS" else "calls"] += 1
            p["durationSec"] += int(r.duration_sec or 0) if pd.notna(r.duration_sec) else 0
        else:
            p["messages"] += 1
        p["first"] = min(p["first"] or r.ts, r.ts); p["last"] = max(p["last"] or r.ts, r.ts)
        if len(p["evidenceIds"]) < 12:
            p["evidenceIds"].append(r.evidence_id)
    allc = df[df.modality.isin(["CDR", "SOCIAL"]) & df.entity_id_2.notna()]
    pair_cases = defaultdict(set)
    for a, b, cid in zip(allc.person_id, allc.entity_id_2, allc.case_id):
        pair_cases[tuple(sorted((a, b)))].add(cid)
    pair_list = []
    for (a, b), p in pairs.items():
        total = p["calls"] + p["sms"] + p["messages"]
        pair_list.append({"persons": [a, b], "names": [names.get(a, a), names.get(b, b)], "total": total, **p,
                          "first": p["first"].strftime("%Y-%m-%d %H:%M"), "last": p["last"].strftime("%Y-%m-%d %H:%M"),
                          "bothNamedInFIR": a in named and b in named,
                          "otherCases": sorted(pair_cases[(a, b)] - {case_id})})
    pair_list.sort(key=lambda x: (-x["bothNamedInFIR"], -x["total"]))
    # ---- around the incident -------------------------------------------------------------
    around = None
    if incident_ts is not None:
        inc = pd.Timestamp(incident_ts)
        w = c[(c.ts >= inc - pd.Timedelta(hours=48)) & (c.ts <= inc + pd.Timedelta(hours=48))]
        span_days = max(1.0, (c.ts.max() - c.ts.min()).total_seconds() / 86400) if len(c) else 1.0
        baseline = len(c) / span_days * 4  # expected count in a 96 h window
        rel = w[w.person_id.isin(named) & w.entity_id_2.isin(named)]
        around = {"window": "±48 h of recorded incident time", "count": int(len(w)), "expectedFromBaseline": round(baseline, 1),
                  "betweenNamedPersons": int(len(rel)),
                  "before": int((w.ts < inc).sum()), "after": int((w.ts >= inc).sum()),
                  "namedPersonEvidence": list(rel.sort_values("ts").evidence_id[:15])}
    # ---- bursts ----------------------------------------------------------------------------
    case_bursts = [b for b in bursts() if case_id in b["caseIds"]]
    # ---- night-time share per person --------------------------------------------------------
    night = []
    for pid, g in c.groupby("person_id"):
        if len(g) >= 10:
            share = float(((g.ts.dt.hour >= 23) | (g.ts.dt.hour < 5)).mean())
            if share >= 0.2:
                night.append({"personId": pid, "share": round(share, 2), "records": int(len(g))})
    # ---- important messages (objective reasons only) -----------------------------------------
    ents = db.query("SELECT evidence_id, entity_type, normalized FROM text_entities WHERE case_id=%s AND modality='SOCIAL'",
                    (case_id,))
    by_ev = defaultdict(list)
    for e in ents:
        by_ev[e["evidence_id"]].append(e)
    case_accounts = set(df[(df.case_id == case_id) & (df.modality == "FINANCIAL")].counterpart_account.dropna()) | \
        set(df[(df.case_id == case_id) & (df.modality == "FINANCIAL")].account_number.dropna())
    important = []
    msgs = c[c.modality == "SOCIAL"]
    inc = pd.Timestamp(incident_ts) if incident_ts is not None else None
    for r in msgs.itertuples():
        reasons = []
        for e in by_ev.get(r.evidence_id, []):
            if e["entity_type"] == "ACCOUNT":
                reasons.append(f"references account {e['normalized']}" + (" (seen in this case's transactions)"
                                                                          if e["normalized"] in case_accounts else ""))
            elif e["entity_type"] == "AMOUNT":
                reasons.append(f"references an amount (₹{e['normalized']})")
            elif e["entity_type"] == "PHONE":
                reasons.append(f"references phone {e['normalized']}")
        if inc is not None and r.person_id in named and r.entity_id_2 in named and abs((r.ts - inc).total_seconds()) <= 72 * 3600:
            reasons.append("exchanged between FIR-named persons within 72 h of the incident")
        if reasons:
            important.append({"evidenceId": r.evidence_id, "timestamp": r.ts.strftime("%Y-%m-%d %H:%M"),
                              "from": r.person_id, "to": r.entity_id_2, "text": r.text_content, "reasons": reasons,
                              "reliability": r.source_reliability})
    # ---- repeated identifiers across records ---------------------------------------------------
    rep = Counter((e["entity_type"], e["normalized"]) for e in ents if e["entity_type"] in ("ACCOUNT", "PHONE"))
    repeated = [{"type": t, "value": v, "mentions": n} for (t, v), n in rep.most_common() if n >= 2]
    daily = c.groupby(c.ts.dt.date).size()
    return {"pairs": pair_list[:25], "pairCount": len(pair_list), "aroundIncident": around, "bursts": case_bursts,
            "nightActivity": night, "importantMessages": important[:40], "repeatedIdentifiers": repeated[:20],
            "dailyVolume": {str(k): int(v) for k, v in daily.items()},
            "note": "Communication frequency describes a relationship pattern; it does not indicate criminal activity."}
