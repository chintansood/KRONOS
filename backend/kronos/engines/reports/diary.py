"""Automated case diary generator (draft, in the structure of a case diary under BNSS s.192 / CrPC s.172).

Entries are generated ONLY from things KRONOS has a record of — it never invents field activity:
  * investigation records with their own dates: incident information, FIR registration, statements recorded;
  * data received into KRONOS: records ingested per source, with SHA-256 / Merkle anchoring;
  * analytical findings produced by KRONOS for the case (flags, inconsistencies, identity candidates);
  * investigator actions inside KRONOS, from the evidence ledger: integrity checks, identity / prior-record
    reviews, case edits, evidence-request status changes, records inspected;
  * entries typed by the Investigating Officer (also written to the ledger).
Every line cites evidence IDs or ledger blocks. The diary is a DRAFT for the IO to verify, complete and sign.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ... import db
from ..intelligence import next_evidence
from ..multimodal import case_intel
from ..provenance import ledger

SECTIONS = ["Information received", "Places visited", "Statements recorded", "Steps taken / evidence collected",
            "Circumstances ascertained", "Investigator entries", "Next steps"]


def add_entry(case_id: str, text: str, entry_ts: str | None = None, place: str | None = None, author: str = "investigator",
              evidence_ids: list[str] | None = None) -> dict:
    ts = datetime.fromisoformat(entry_ts) if entry_ts else datetime.now()
    r = db.query_one("INSERT INTO case_diary_entries (case_id, entry_ts, author, place, text, evidence_ids) VALUES (%s,%s,%s,%s,%s,%s) "
                     "RETURNING id", (case_id, ts, author, place, text, evidence_ids or []))
    ledger.append("CASE_DIARY", None, None, author, {"caseId": case_id, "entryId": r["id"], "entryTs": ts.isoformat(),
                                                    "place": place, "text": text[:500]})
    return {"id": r["id"], "caseId": case_id, "entryTs": ts.isoformat(), "text": text}


def build(case_id: str) -> dict:
    I = case_intel.get(case_id)
    if not I:
        raise KeyError(case_id)
    o = I["overview"]
    days: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    def put(ts, section, text, refs=None):
        if ts is None:
            return
        ts = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        day = ts.strftime("%Y-%m-%d")
        days[day][section].append({"time": ts.strftime("%H:%M"), "text": text, "refs": [r for r in (refs or []) if r]})

    # 1) investigation records with their own dates
    if o.get("incident_ts"):
        put(o["incident_ts"], "Information received",
            f"Incident at {o.get('incident_location')} ({o.get('offence_category')}), as recorded in the FIR.", [])
    for r in db.query("SELECT evidence_id, ts, text_content, extra, location_name FROM events WHERE case_id=%s AND modality='FIR' "
                      "ORDER BY ts", (case_id,)):
        x = r["extra"] or {}
        rt = (x.get("record_type") or "FIR").replace("_", " ").title()
        if x.get("record_type") == "FIR":
            put(r["ts"], "Information received",
                f"FIR {x.get('fir_number')} registered at {x.get('police_station')} under {x.get('sections')}; complainant "
                f"{x.get('complainant_name') or 'not named (suo motu / police information)'}; accused named: "
                f"{', '.join(x.get('accused_person_ids') or []) or 'none'}.", [r["evidence_id"]])
            put(r["ts"], "Places visited", f"Scene of incident as recorded in the FIR: {r['location_name']}.", [r["evidence_id"]])
        else:
            first = (r["text_content"] or "").split(". ")[0][:220]
            put(r["ts"], "Statements recorded", f"{rt}: {first}.", [r["evidence_id"]])
    # 2) data received into KRONOS (per source file), with integrity anchoring
    per_file = db.query("SELECT r.file_name, r.run_id, count(*) n, min(r.ingested_at) at FROM raw_records r WHERE r.case_id=%s "
                        "GROUP BY 1,2 ORDER BY 4", (case_id,))
    anchors = {(b["metadata"]["run_id"], b["metadata"]["file"]): b for b in
               db.query("SELECT block_index, metadata FROM ledger_blocks WHERE event_type='ANCHOR'")}
    for f in per_file:
        a = anchors.get((f["run_id"], f["file_name"]))
        put(f["at"], "Steps taken / evidence collected",
            f"{f['n']} records from {f['file_name']} received into KRONOS for this case; SHA-256 hash of each record written to "
            f"the evidence ledger" + (f"; batch Merkle root anchored in block #{a['block_index']} and endorsed by the agency nodes "
                                      f"({a['metadata'].get('quorum')} quorum)" if a else "") + ".",
            [f"ledger block #{a['block_index']}"] if a else [])
    # 3) analytical findings (dated when KRONOS produced them)
    found_at = db.query_one("SELECT computed_at FROM analysis_cache WHERE cache_key=%s", (f"case_intel:{case_id}",))
    at = found_at["computed_at"] if found_at else (per_file[-1]["at"] if per_file else None)
    fin = I["financial"]
    if fin["flaggedCount"]:
        put(at, "Circumstances ascertained", f"KRONOS analysis flagged {fin['flaggedCount']} transaction(s) for review "
                                             f"(e.g. {', '.join(f['evidenceId'] for f in fin['flagged'][:3])}); indicators, not findings.",
            [f["evidenceId"] for f in fin["flagged"][:3]])
    for t in I["travelInconsistencies"][:3]:
        put(at, "Circumstances ascertained", f"Location inconsistency for {t['personId']}: {t['verdict'].replace('_', ' ').lower()} "
                                             f"({t['distanceKm']} km in {t['elapsedMinutes']} min).",
            [t["first"]["evidenceId"], t["second"]["evidenceId"]])
    for ob in I["crossSourceObservations"][:4]:
        put(at, "Circumstances ascertained", ob["observation"], [e for f in ob["facts"] for e in f["evidenceIds"]][:3])
    people = [p["personId"] for p in I["people"]]
    for c in db.query("SELECT candidate_id, person_a, person_b, band, score FROM identity_candidates WHERE band IN ('HIGH','MEDIUM') "
                      "AND (person_a = ANY(%s) OR person_b = ANY(%s))", (people, people)):
        put(at, "Circumstances ascertained", f"Possible identity link {c['person_a']} / {c['person_b']} ({c['band']}, score {c['score']}) "
                                             "identified for verification — not merged.", [c["candidate_id"]])
    # 4) investigator actions recorded on the ledger
    case_ev = {r["evidence_id"] for r in db.query("SELECT evidence_id FROM events WHERE case_id=%s", (case_id,))}
    acc = defaultdict(int)
    for b in db.query("SELECT block_index, ts, event_type, evidence_id, actor, metadata FROM ledger_blocks WHERE event_type IN "
                      "('ACCESS','VERIFY','IDENTITY_REVIEW','HISTORY_LINK_REVIEW','CASE_EDIT','CASE_DIARY') ORDER BY block_index"):
        m = b["metadata"] or {}
        if b["event_type"] == "ACCESS" and b["evidence_id"] in case_ev:
            acc[b["ts"].strftime("%Y-%m-%d")] += 1
        elif b["event_type"] == "VERIFY" and b["evidence_id"] in case_ev:
            put(b["ts"], "Steps taken / evidence collected", f"Integrity of {b['evidence_id']} verified ({m.get('type', 'hash check')}): "
                                                            f"{m.get('result')}.", [b["evidence_id"], f"ledger block #{b['block_index']}"])
        elif b["event_type"] == "CASE_EDIT" and m.get("caseId") == case_id:
            put(b["ts"], "Investigator entries", f"Case particulars {m.get('action', 'updated').lower()}d: "
                                                 f"{', '.join(k for k in (m.get('fields') or {}) if k != 'title') or 'title'}.",
                [f"ledger block #{b['block_index']}"])
        elif b["event_type"] in ("IDENTITY_REVIEW", "HISTORY_LINK_REVIEW"):
            ref = m.get("candidateId") or m.get("linkId") or ""
            if any(p in ref for p in people):
                put(b["ts"], "Investigator entries", f"{'Identity match' if b['event_type'] == 'IDENTITY_REVIEW' else 'Prior-record link'} "
                                                     f"{ref} marked {m.get('decision')} by {b['actor']}" + (f": {m['note']}" if m.get("note") else "."),
                    [f"ledger block #{b['block_index']}"])
    for day, n in acc.items():
        put(datetime.fromisoformat(day + "T23:59"), "Steps taken / evidence collected", f"{n} evidence record(s) inspected in KRONOS (access logged).", [])
    for r in db.query("SELECT request_id, status, actor, at FROM evidence_request_log WHERE case_id=%s ORDER BY at", (case_id,)):
        put(r["at"], "Investigator entries", f"Evidence request {r['request_id']} status set to {r['status']}.", [r["request_id"]])
    for r in db.query("SELECT * FROM case_diary_entries WHERE case_id=%s ORDER BY entry_ts", (case_id,)):
        put(r["entry_ts"], "Investigator entries", (f"[{r['place']}] " if r["place"] else "") + r["text"] + f" — {r['author']}",
            list(r["evidence_ids"] or []))
    # 5) next steps on the latest day
    ordered = sorted(days)
    if ordered:
        for rec in next_evidence.recommend(case_id)[:4]:
            days[ordered[-1]]["Next steps"].append({"time": "", "text": f"[{rec['priority']} · value {rec['valueScore']}] "
                                                                       f"{rec['verificationAction']} ({rec['status']})",
                                                    "refs": rec["basisEvidenceIds"][:2]})
    entries = []
    for n, day in enumerate(ordered, 1):
        secs = days[day]
        entries.append({"day": n, "date": day, "sections": [{"section": s_, "items": sorted(secs[s_], key=lambda x: x["time"])}
                                                            for s_ in SECTIONS if secs.get(s_)]})
    return {"caseId": case_id, "firNumber": o.get("fir_number"), "policeStation": o.get("police_station"),
            "investigatingOfficer": o.get("lead_investigator"), "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "entries": entries,
            "note": "DRAFT case diary generated by KRONOS only from recorded events and KRONOS activity. Field steps not "
                    "recorded in KRONOS do not appear — the Investigating Officer must verify, complete and sign each entry."}
