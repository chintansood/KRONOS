"""Case-level intelligence synthesis — combines the five independently analysed sources into
one evidence-referenced picture of what appears unusual, important or connected in a case."""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from ... import db
from ..store import cached, data_version, events
from ..temporal import travel
from . import communications, financial, location

ROLE_RANK = {"PRINCIPAL_ACCUSED": 7, "ACCUSED": 6, "COMPLAINANT": 5, "VICTIM": 4, "WITNESS": 3, "ASSOCIATE": 2,
             "MENTIONED": 1, "RECORD_SUBJECT": 0}


def case_row(case_id: str) -> dict | None:
    return db.query_one("SELECT * FROM cases WHERE case_id=%s", (case_id,))


def people(case_id: str) -> list[dict]:
    rows = db.query("SELECT r.person_id, r.role, r.method, r.confidence, r.evidence_id, p.display_name, p.phones, "
                    "p.accounts, p.devices FROM person_case_roles r LEFT JOIN persons p USING (person_id) "
                    "WHERE r.case_id=%s", (case_id,))
    by = {}
    for r in rows:
        p = by.setdefault(r["person_id"], {"personId": r["person_id"], "name": r["display_name"], "roles": [],
                                           "evidenceIds": [], "phones": r["phones"], "accounts": r["accounts"],
                                           "devices": r["devices"]})
        if r["role"] not in [x["role"] for x in p["roles"]]:
            p["roles"].append({"role": r["role"], "method": r["method"], "confidence": r["confidence"]})
        if r["evidence_id"] and r["evidence_id"] not in p["evidenceIds"]:
            p["evidenceIds"].append(r["evidence_id"])
    for p in by.values():
        p["roles"].sort(key=lambda x: -ROLE_RANK.get(x["role"], 0))
        p["primaryRole"] = p["roles"][0]["role"]
    return sorted(by.values(), key=lambda p: (-ROLE_RANK.get(p["primaryRole"], 0), p["personId"]))


def build(case_id: str) -> dict:
    c = case_row(case_id)
    if not c:
        return {}
    df = events()
    ce = df[df.case_id == case_id]
    ppl = people(case_id)
    named = {p["personId"] for p in ppl if p["primaryRole"] != "RECORD_SUBJECT"}
    accused = {p["personId"] for p in ppl if p["primaryRole"] in ("PRINCIPAL_ACCUSED", "ACCUSED")}
    inc = c["incident_ts"]
    # ---------------- financial
    fa = financial.analysis()
    fin_flags = [f for f in fa["flagged"] if f["caseId"] == case_id]
    fin = ce[ce.modality == "FINANCIAL"]
    fin_findings = {
        "totalVolume": float(fin.amount.sum(skipna=True)), "transactions": int(len(fin)),
        "flagged": fin_flags[:40], "flaggedCount": len(fin_flags),
        "passThroughChains": [x for x in fa["chains"] if x["caseId"] == case_id][:20],
        "structuring": [x for x in fa["structuring"] if case_id in x["caseIds"]],
        "fanIn": [x for x in fa.get("fanIn", []) if case_id in x["caseIds"]],
        "accounts": financial.account_summary(case_id=case_id)[:15],
    }
    # organisations seen in case money flows
    orgs = defaultdict(lambda: {"in": 0.0, "out": 0.0, "n": 0})
    for r in fin.itertuples():
        x = r.extra or {}
        amt = float(r.amount) if pd.notna(r.amount) else 0.0
        if x.get("sender_org_id"):
            o = orgs[(x["sender_org_id"], x.get("sender_name"))]; o["out"] += amt; o["n"] += 1
        if x.get("receiver_org_id"):
            o = orgs[(x["receiver_org_id"], x.get("receiver_name"))]; o["in"] += amt; o["n"] += 1
    org_list = sorted([{"orgId": k[0], "name": k[1], "received": round(v["in"], 2), "paid": round(v["out"], 2),
                        "transactions": v["n"]} for k, v in orgs.items()], key=lambda o: -(o["received"] + o["paid"]))
    comm = communications.analyse_case(case_id, inc, named)
    loc = location.analyse_case(case_id, inc, c["incident_lat"], c["incident_lon"], named)
    # ---------------- travel anomalies for case persons in this case
    trav = []
    for pid in ce.person_id.dropna().unique():
        for f in travel.detect_for_frame(df, pid):
            if case_id in (f["first"]["caseId"], f["second"]["caseId"]):
                trav.append(f)
    # ---------------- cross-source observations per named person
    obs = []
    for p in ppl:
        pid = p["personId"]
        if pid not in named:
            continue
        facts = []
        nr = [x for x in loc["nearIncident"] if x["personId"] == pid]
        if nr:
            facts.append(("LOCATION", f"record within {min(x['distanceKm'] for x in nr)} km of the incident location "
                                      f"within 2 h of the incident", [x["evidenceId"] for x in nr[:3]]))
        el = [x for x in loc["namedPersonsElsewhere"] if x["personId"] == pid]
        if el:
            facts.append(("LOCATION_CONTRA", f"record(s) {el[0]['distanceKm']} km away from the incident location within "
                                             f"3 h of the incident ({el[0]['location']})", [x["evidenceId"] for x in el[:3]]))
        pc = [x for x in comm["pairs"] if pid in x["persons"] and x["bothNamedInFIR"]]
        if pc:
            facts.append(("COMMUNICATION", "in contact with " + ", ".join(
                f"{[q for q in x['persons'] if q != pid][0]} ({x['total']} contacts)" for x in pc[:3]),
                [e for x in pc[:2] for e in x["evidenceIds"][:2]]))
        ff = [f for f in fin_flags if pid in (f["sender"], f["receiver"])]
        if ff:
            facts.append(("FINANCIAL", f"party to {len(ff)} flagged transaction(s) "
                                       f"({', '.join(sorted({m for f in ff for m in f['methods']}))})",
                          [f["evidenceId"] for f in ff[:3]]))
        tv = [f for f in trav if f["personId"] == pid]
        if tv:
            facts.append(("TEMPORAL", f"{len(tv)} location inconsistency flag(s) ({tv[0]['verdict'].lower()})",
                          [tv[0]["first"]["evidenceId"], tv[0]["second"]["evidenceId"]]))
        if facts:
            sources = {f[0].replace("_CONTRA", "") for f in facts}
            obs.append({"personId": pid, "name": p["name"], "role": p["primaryRole"], "facts": [
                {"source": s, "text": t, "evidenceIds": e} for s, t, e in facts], "independentSources": len(sources),
                "observation": f"{p['name']} ({pid}), recorded as {p['primaryRole'].lower().replace('_', ' ')}: " +
                               "; ".join(t for _, t, _ in facts) + "."})
    obs.sort(key=lambda o: -o["independentSources"])
    # ---------------- uncertainties & missing information
    issues = db.query("SELECT field, issue, count(*) n FROM ingestion_issues i JOIN raw_records r USING (source_record_id) "
                      "WHERE r.case_id=%s GROUP BY 1,2 ORDER BY 3 DESC", (case_id,))
    unlinked = db.query("SELECT entity_text, count(*) n FROM text_entities WHERE case_id=%s AND entity_type='PERSON' "
                        "AND linked_person_id IS NULL GROUP BY 1", (case_id,))
    rel = ce.source_reliability.value_counts(normalize=True).round(3).to_dict()
    uncert = []
    for i in issues:
        uncert.append(f"{i['n']} record(s) with data-quality issue: {i['field']} — {i['issue']}")
    for u in unlinked:
        uncert.append(f"Name '{u['entity_text']}' in FIR text could not be linked to a unique person record")
    if rel.get("LOW", 0) > 0.1:
        uncert.append(f"{rel['LOW']:.0%} of case records have LOW source reliability")
    for p in ppl:
        for r in p["roles"]:
            if r["method"] == "FIR_NER" and (r["confidence"] or 0) < 0.85:
                uncert.append(f"Role of {p['personId']} ({r['role']}) derived from FIR text with confidence {r['confidence']}")
    missing = []
    inc_ts = pd.Timestamp(inc) if inc else None
    for pid in accused:
        pe = ce[(ce.person_id == pid)]
        if inc_ts is not None:
            near = pe[pe.latitude.notna() & (pe.ts >= inc_ts - pd.Timedelta(hours=6)) & (pe.ts <= inc_ts + pd.Timedelta(hours=6))]
            if near.empty:
                missing.append({"personId": pid, "gap": "no geolocated record within ±6 h of the incident"})
        if pe[pe.modality == "CDR"].empty:
            missing.append({"personId": pid, "gap": "no call detail records obtained"})
        if pe[pe.modality == "FINANCIAL"].empty and fin_findings["totalVolume"] > 0:
            missing.append({"personId": pid, "gap": "no bank transactions on record"})
    holders = {a for p in ppl for a in (p["accounts"] or [])}
    unknown_accts = [a["account"] for a in fin_findings["accounts"] if not a["holders"] and a["account"] not in holders]
    if unknown_accts:
        missing.append({"personId": None, "gap": f"holder unknown for account(s): {', '.join(unknown_accts[:5])}"})
    key_events = []
    if c["incident_ts"]:
        key_events.append({"timestamp": c["incident_ts"].strftime("%Y-%m-%d %H:%M"), "event": f"Incident recorded at {c['incident_location']}",
                           "evidenceIds": []})
    for r in ce[ce.modality == "FIR"].sort_values("ts").itertuples():
        key_events.append({"timestamp": r.ts.strftime("%Y-%m-%d %H:%M"), "event": r.event_description, "evidenceIds": [r.evidence_id]})
    for m in comm["bursts"][:5]:
        key_events.append({"timestamp": m["start"], "event": f"Communication burst {m['persons'][0]}–{m['persons'][1]} ({m['count']} contacts in 3 h)",
                           "evidenceIds": m["evidenceIds"][:3]})
    for cp in [x for x in loc["coPresence"] if x["communicationsWithin48h"]][:6]:
        key_events.append({"timestamp": cp["timestamp"], "event": f"{cp['persons'][0]} and {cp['persons'][1]} co-located at {cp['location']}",
                           "evidenceIds": cp["evidenceIds"]})
    for f in fin_flags[:6]:
        key_events.append({"timestamp": f["timestamp"], "event": f"Flagged {f['channel']} ₹{f['amount']:,.0f} {f['sender']} → {f['receiver']}",
                           "evidenceIds": [f["evidenceId"]]})
    key_events.sort(key=lambda e: e["timestamp"])
    anomalies = ([{"type": "FINANCIAL", "count": len(fin_flags)}] if fin_flags else []) + \
                ([{"type": "IMPOSSIBLE_TRAVEL", "count": len(trav)}] if trav else []) + \
                ([{"type": "COMMUNICATION_BURST", "count": len(comm["bursts"])}] if comm["bursts"] else [])
    return {
        "caseId": case_id,
        "overview": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in c.items()},
        "recordCounts": ce.modality.value_counts().to_dict(),
        "dateRange": [ce.ts.min().strftime("%Y-%m-%d"), ce.ts.max().strftime("%Y-%m-%d")] if ce.ts.notna().any() else None,
        "people": ppl, "organisations": org_list[:15], "keyEvents": key_events,
        "communication": comm, "financial": fin_findings, "location": loc,
        "travelInconsistencies": trav, "anomalies": anomalies, "crossSourceObservations": obs,
        "sourceReliability": rel, "uncertainties": uncert, "missingInformation": missing,
        "disclaimer": "Recorded roles and analytical flags are investigative aids, not findings of guilt.",
    }


def get(case_id: str) -> dict:
    return cached(f"case_intel:{case_id}", lambda: build(case_id))
