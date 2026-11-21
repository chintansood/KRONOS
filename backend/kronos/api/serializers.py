"""Convert backend records into the exact shapes of the frontend's TypeScript interfaces
(kronos-app/src/types/investigation.ts)."""
from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

from .. import db
from ..engines.graph.analytics import metrics, person_projection
from ..engines.multimodal import financial
from ..engines.store import cached, events

MOD_UI = {"SOCIAL": "COMMUNICATION"}
ROLE_UI = {"PRINCIPAL_ACCUSED": "PRIMARY_SUSPECT", "ACCUSED": "CO_ACCUSED", "ASSOCIATE": "ASSOCIATE",
           "COMPLAINANT": "COMPLAINANT", "VICTIM": "COMPLAINANT"}
ROLE_RANK = {"PRINCIPAL_ACCUSED": 7, "ACCUSED": 6, "ASSOCIATE": 5, "COMPLAINANT": 4, "VICTIM": 3, "WITNESS": 2,
             "MENTIONED": 1, "RECORD_SUBJECT": 0}


def d(ts, with_time=False):
    if ts is None or (isinstance(ts, float)) or pd.isna(ts):
        return ""
    ts = pd.Timestamp(ts)
    return ts.strftime("%d %b %Y %H:%M") if with_time else ts.strftime("%d %b %Y")


def _case_rows():
    df = events()
    agg = df.groupby("case_id").agg(n=("evidence_id", "size"), last=("ts", "max"))
    vol = df[df.modality == "FINANCIAL"].groupby("case_id").amount.sum()
    ev_first = df.sort_values("ts").groupby("case_id").evidence_id.apply(lambda s: list(s[:40]))
    return agg, vol, ev_first


def cases() -> list[dict]:
    def compute():
        agg, vol, ev_first = _case_rows()
        roles = defaultdict(list)
        for r in db.query("SELECT person_id, case_id, role FROM person_case_roles"):
            roles[r["case_id"]].append(r)
        summ = {r["case_id"]: r["summary_json"]["conciseSummary"] for r in db.query("SELECT case_id, summary_json FROM case_summaries")}
        fl = Counter(f["caseId"] for f in financial.analysis()["flagged"])
        out = []
        for c in db.query("SELECT * FROM cases ORDER BY case_id"):
            cid = c["case_id"]
            rs = roles.get(cid, [])
            pids = sorted({r["person_id"] for r in rs}, key=lambda p: -max(ROLE_RANK[r["role"]] for r in rs if r["person_id"] == p))
            accused = [p for p in pids if any(r["role"] in ("PRINCIPAL_ACCUSED", "ACCUSED") for r in rs if r["person_id"] == p)]
            delay = round((c["registration_ts"] - c["incident_ts"]).total_seconds() / 3600, 1) if c["registration_ts"] and c["incident_ts"] else 0
            n_flag = fl.get(cid, 0)
            pr = c["priority"] if c["is_custom"] else ("CRITICAL" if n_flag >= 12 else "HIGH" if n_flag >= 5 or len(accused) >= 3
                                                       else "MEDIUM" if n_flag or len(accused) >= 2 else "LOW")
            last = agg["last"].get(cid) if cid in agg.index else None
            out.append({
                "id": cid, "title": c["title"], "offenceCategory": c["offence_category"] or "Unclassified",
                "description": c["description"] or summ.get(cid) or "", "status": c["status"] or "ACTIVE", "priority": pr,
                "firNumber": c["fir_number"] or "", "policeStation": c["police_station"] or "", "district": c["district"] or "",
                "incidentDate": d(c["incident_ts"], True), "registrationDate": d(c["registration_ts"], True),
                "incidentIso": c["incident_ts"].strftime("%Y-%m-%dT%H:%M") if c["incident_ts"] else None,
                "reportingDelayHours": delay, "totalFinancialVolume": round(float(vol.get(cid, 0) or 0), 2),
                "peopleCount": len(pids), "evidenceCount": int(agg["n"].get(cid, 0)) if cid in agg.index else 0,
                "lastActivity": pd.Timestamp(last).strftime("%Y-%m-%d %H:%M") if last is not None and not pd.isna(last) else "",
                "leadInvestigator": c["lead_investigator"] or "", "personIds": pids, "primarySuspectIds": accused,
                "evidenceIds": ev_first.get(cid, []), "isCustom": bool(c["is_custom"]),
                "origin": c.get("origin") or "SYNTHETIC", "source": c.get("source"),
                "agencyId": c["agency_id"], "incidentLocation": c["incident_location"], "flaggedFindings": n_flag,
                "priorityBasis": f"{n_flag} flagged financial findings, {len(accused)} recorded accused (administrative triage, not a guilt assessment)",
            })
        return out
    return cached("ui_cases:v3", compute)


def persons() -> list[dict]:
    def compute():
        df = events()
        roles = defaultdict(list)
        for r in db.query("SELECT person_id, case_id, role FROM person_case_roles"):
            roles[r["person_id"]].append(r)
        P = person_projection()
        loc = df[(df.modality == "LOCATION") & df.location_name.notna()]
        places = loc.groupby("person_id").location_name.agg(lambda s: list(s.value_counts().index[:4]))
        aliases = defaultdict(set)
        for r in db.query("SELECT person_a, person_b, band, status FROM identity_candidates WHERE band IN ('HIGH','MEDIUM') AND status <> 'REJECTED'"):
            aliases[r["person_a"]].add(r["person_b"]); aliases[r["person_b"]].add(r["person_a"])
        names = {p["person_id"]: p for p in db.query("SELECT * FROM persons")}
        out = []
        for pid, rs in roles.items():
            p = names.get(pid)
            if not p:
                continue
            best = max(rs, key=lambda r: ROLE_RANK[r["role"]])["role"]
            cs = sorted({r["case_id"] for r in rs})
            prim = sorted({r["case_id"] for r in rs if r["role"] in ("PRINCIPAL_ACCUSED", "ACCUSED")})
            nb = sorted(P[pid], key=lambda n: -P[pid][n]["weight"])[:6] if pid in P else []
            other_names = [n for n in p["names"] if n != p["display_name"]]
            alias = ", ".join(other_names + [names[a]["display_name"] + f" ({a}?)" for a in aliases.get(pid, []) if a in names][:2]) or None
            role_txt = "; ".join(f"{r['role'].lower().replace('_', ' ')} in {r['case_id']}" for r in sorted(rs, key=lambda r: r["case_id"]))
            out.append({
                "id": pid, "name": p["display_name"], "alias": alias, "role": ROLE_UI.get(best, "PERSON_OF_INTEREST"),
                "contactNumbers": p["phones"], "associatedDevices": p["devices"], "bankAccounts": p["accounts"],
                "firstAppearance": d(p["first_seen"]), "latestActivity": d(p["last_seen"]),
                "firstSeen": p["first_seen"].strftime("%Y-%m-%d") if p["first_seen"] else None,
                "lastSeen": p["last_seen"].strftime("%Y-%m-%d") if p["last_seen"] else None,
                "casesMentionedCount": len(cs), "primarySuspectCasesCount": len(prim), "caseIds": cs, "primaryCaseIds": prim,
                "casesMentioned": cs, "primarySuspectCases": prim, "associatedPersonIds": nb,
                "knownLocations": places.get(pid, []), "recordedRoles": [{"caseId": r["case_id"], "role": r["role"]} for r in rs],
                "identityCandidateIds": sorted(aliases.get(pid, [])),
                "notes": f"Recorded as {role_txt}. Recorded roles are not findings of guilt.",
            })
        out.sort(key=lambda x: (-x["primarySuspectCasesCount"], -x["casesMentionedCount"], x["id"]))
        return out
    return cached("ui_persons:v2", compute)


def evidence(row, raw: dict | None = None, ledger_info: dict | None = None) -> dict:
    x = row.get("extra") or {}
    rel = [p for p in (row.get("person_id"), row.get("entity_id_2")) if isinstance(p, str) and p.startswith("P")]
    rel += [p for p in x.get("accused_person_ids", []) if p not in rel]
    meta = {}
    for k in ("event_type", "phone_number", "counterpart_phone", "device_id", "account_number", "counterpart_account",
              "amount", "duration_sec", "accuracy_m"):
        v = row.get(k)
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            meta[k] = float(v) if hasattr(v, "is_finite") else v
    if isinstance(row.get("text_content"), str) and row["text_content"]:
        meta["text"] = row["text_content"]
    if raw:
        meta["originalRecord"] = raw
    if ledger_info:
        meta.update(ledger_info)
    ts = row.get("ts")
    lat, lon = row.get("latitude"), row.get("longitude")
    return {"evidenceId": row["evidence_id"], "sourceRecordId": row["source_record_id"], "caseId": row["case_id"],
            "modality": MOD_UI.get(row["modality"], row["modality"]),
            "timestamp": pd.Timestamp(ts).strftime("%d %b %Y %H:%M") if ts is not None and not pd.isna(ts) else "timestamp unavailable",
            "iso": pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M") if ts is not None and not pd.isna(ts) else None,
            "locationName": row.get("location_name") or "", "latitude": None if lat is None or pd.isna(lat) else float(lat),
            "longitude": None if lon is None or pd.isna(lon) else float(lon), "sourceReliability": row.get("source_reliability") or "MEDIUM",
            "description": row.get("event_description") or "", "relatedPersonIds": rel, "metadata": meta}
