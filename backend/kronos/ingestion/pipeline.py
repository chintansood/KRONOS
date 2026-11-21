"""Full ingestion pipeline: CSVs -> raw_records + events -> persons/cases -> FIR/message NER
-> recorded roles -> provenance ledger."""
from __future__ import annotations

import csv
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .. import db
from ..config import settings
from ..engines.multimodal import text_ner
from ..engines.provenance import ledger
from .cdr_loader import CDRLoader
from .financial_loader import FinancialLoader
from .fir_loader import FIRLoader
from .history_loader import HistoryLoader
from .location_loader import LocationLoader
from .social_media_loader import SocialMediaLoader

LOADERS = [FIRLoader(), CDRLoader(), LocationLoader(), FinancialLoader(), SocialMediaLoader(), HistoryLoader()]
HISTORY_COLS = ["history_id", "source_record_id", "evidence_id", "record_type", "source_system", "full_name", "alias_names",
                "father_name", "birth_year", "address", "phone_at_record", "fir_reference", "offence_category", "sections",
                "police_station", "district", "record_date", "disposition", "modus_operandi", "source_reliability"]
EVENT_COLS = ["event_id", "source_record_id", "evidence_id", "case_id", "agency_id", "modality", "ts", "ts_quality",
              "person_id", "entity_id_1", "entity_id_2", "entity_type", "phone_number", "counterpart_phone",
              "account_number", "counterpart_account", "device_id", "sim_id", "latitude", "longitude", "accuracy_m",
              "location_name", "event_type", "event_description", "text_content", "amount", "duration_sec",
              "source_reliability", "confidence", "extra"]


def _log(msg):
    print(f"[ingest {datetime.now():%H:%M:%S}] {msg}", flush=True)


def reset_all():
    db.execute("""TRUNCATE events, raw_records, persons, cases, person_case_roles, text_entities, ingestion_issues,
                  ingestion_runs, analysis_cache, case_summaries, identity_candidates, identity_reviews, doc_chunks,
                  evidence_requests, ledger_blocks, assistant_log, criminal_history, history_links, history_reviews CASCADE""")


def ingest(source_dir: Path | None = None, reset: bool = True) -> dict:
    source_dir = Path(source_dir or settings.generated_dir)
    db.apply_schema()
    if reset:
        reset_all()
    run_id = f"RUN-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
    db.execute("INSERT INTO ingestion_runs (run_id, source_dir) VALUES (%s,%s)", (run_id, str(source_dir)))
    ledger.ensure_genesis()
    stats = {}
    case_agency = {}
    for loader in LOADERS:
        res = loader.load(source_dir)
        stats[res.modality] = res.stats
        _log(f"{res.file_name}: {res.stats}")
        db.execute_values("INSERT INTO raw_records (source_record_id, modality, case_id, file_name, row_number, raw, "
                          "content_sha256, quarantined, run_id) VALUES %s",
                          [(s, res.modality, c, res.file_name, n, db.Json(raw), sha, q, run_id)
                           for s, c, n, raw, sha, q in res.raw])
        if res.modality == "FIR":
            for e in res.events:
                if e.get("agency_id"):
                    case_agency[e["case_id"]] = e["agency_id"]
        if res.modality == "HISTORY":      # prior records live in their own table, not in the event timeline
            db.execute_values(f"INSERT INTO criminal_history ({','.join(HISTORY_COLS)}) VALUES %s",
                              [tuple(e.get(c) for c in HISTORY_COLS) for e in res.events])
        else:
            for e in res.events:
                e.setdefault("agency_id", None)
                e["agency_id"] = e["agency_id"] or case_agency.get(e["case_id"])
            db.execute_values(f"INSERT INTO events ({','.join(EVENT_COLS)}) VALUES %s",
                              [tuple(db.Json(e.get(c) or {}) if c == "extra" else e.get(c) for c in EVENT_COLS)
                               for e in res.events])
        db.execute_values("INSERT INTO ingestion_issues (run_id, modality, file_name, row_number, source_record_id, "
                          "severity, field, issue, raw_value) VALUES %s",
                          [(run_id, res.modality, res.file_name, n, s, x.severity, x.field, x.issue, x.raw_value)
                           for n, s, x in res.issues])
        # provenance: one INGEST block per original row (hash only, never raw content)
        ev_by_src = {e["source_record_id"]: e["evidence_id"] for e in res.events}
        ledger.append_many([("INGEST", ev_by_src.get(s) or (raw.get("evidence_id") or None), sha, "ingestion",
                             {"source_record_id": s, "file": res.file_name, "row": n, "run_id": run_id,
                              "quarantined": q}) for s, c, n, raw, sha, q in res.raw])
        ledger.anchor_batch(run_id, res.file_name)        # Merkle root of this file, signed by the agency nodes
    db.execute("UPDATE events SET agency_id = c.agency_id FROM (SELECT case_id, max(agency_id) agency_id FROM events "
               "WHERE modality='FIR' GROUP BY case_id) c WHERE events.case_id=c.case_id AND events.agency_id IS NULL")
    _log("building person registry")
    build_persons()
    _log("building case registry")
    build_cases(source_dir)
    _log("extracting entities and recorded roles from FIR text and messages")
    stats["ner"] = extract_entities_and_roles()
    db.execute("UPDATE ingestion_runs SET finished_at=now(), stats=%s WHERE run_id=%s", (db.Json(stats), run_id))
    _log("done")
    return {"run_id": run_id, **stats}


def build_persons():
    """Aggregate a person registry from every place a person id appears. Identifiers are
    attributed only where the source row explicitly ties them to that person id."""
    P = defaultdict(lambda: dict(names=set(), phones=set(), devices=set(), sims=set(), accounts=set(),
                                 first=None, last=None, subject=False))

    def touch(p, ts):
        if ts:
            p["first"] = ts if not p["first"] or ts < p["first"] else p["first"]
            p["last"] = ts if not p["last"] or ts > p["last"] else p["last"]

    rows = db.query("SELECT modality, person_id, entity_id_2, phone_number, counterpart_phone, device_id, sim_id, "
                    "account_number, counterpart_account, ts, extra FROM events")
    for r in rows:
        x, m = r["extra"] or {}, r["modality"]
        if r["person_id"]:
            p = P[r["person_id"]]; p["subject"] = True; touch(p, r["ts"])
            if r["phone_number"]: p["phones"].add(r["phone_number"])
            if r["device_id"] and m in ("CDR", "LOCATION", "SOCIAL"): p["devices"].add(r["device_id"])
            if r["sim_id"]: p["sims"].add(r["sim_id"])
            if m == "FINANCIAL" and r["account_number"]: p["accounts"].add(r["account_number"])
            n = x.get("caller_name") if m == "CDR" else x.get("sender_name") if m in ("FINANCIAL", "SOCIAL") else \
                x.get("complainant_name") if m == "FIR" else None
            if n: p["names"].add(n)
        e2 = r["entity_id_2"]
        if e2 and e2.startswith("P"):
            q = P[e2]; touch(q, r["ts"])
            if r["counterpart_phone"] and m in ("CDR", "SOCIAL"): q["phones"].add(r["counterpart_phone"])
            if m == "FINANCIAL" and r["counterpart_account"]: q["accounts"].add(r["counterpart_account"])
            n = x.get("receiver_name")
            if n: q["names"].add(n)
    db.execute("TRUNCATE persons")
    db.execute_values("INSERT INTO persons (person_id, display_name, names, phones, devices, sims, accounts, first_seen, "
                      "last_seen, is_subject) VALUES %s",
                      [(pid, sorted(p["names"])[0] if p["names"] else pid, sorted(p["names"]), sorted(p["phones"]),
                        sorted(p["devices"]), sorted(p["sims"]), sorted(p["accounts"]), p["first"], p["last"], p["subject"])
                       for pid, p in P.items()])


def build_cases(source_dir: Path):
    register = {}
    reg_file = Path(source_dir) / "CASE_REGISTER.csv"
    if reg_file.exists():
        with open(reg_file, newline="", encoding="utf-8") as fh:
            register = {r["case_id"]: r for r in csv.DictReader(fh)}
    firs = db.query("SELECT DISTINCT ON (case_id) case_id, ts, extra, location_name, latitude, longitude, agency_id "
                    "FROM events WHERE modality='FIR' ORDER BY case_id, (extra->>'record_type'='FIR') DESC, ts")
    rows = []
    for f in firs:
        x = f["extra"]; reg = register.get(f["case_id"], {})
        inc = datetime.fromisoformat(x["incident_ts"]) if x.get("incident_ts") else None
        rows.append((f["case_id"], reg.get("title") or f"{x.get('offence_category')} — {x.get('district')}",
                     x.get("offence_category"), x.get("fir_number"), x.get("police_station"), x.get("district"),
                     f["agency_id"] or reg.get("agency_id"), inc, f["ts"], f["location_name"], f["latitude"],
                     f["longitude"], reg.get("lead_investigator") or "Investigating Officer"))
    db.execute("DELETE FROM cases WHERE NOT is_custom")
    db.execute_values("INSERT INTO cases (case_id, title, offence_category, fir_number, police_station, district, "
                      "agency_id, incident_ts, registration_ts, incident_location, incident_lat, incident_lon, "
                      "lead_investigator) VALUES %s ON CONFLICT (case_id) DO NOTHING", rows)
    # cases that have records but no FIR still get a registry row
    db.execute("INSERT INTO cases (case_id, title) SELECT DISTINCT case_id, 'Case ' || case_id FROM events "
               "ON CONFLICT DO NOTHING")


def extract_entities_and_roles() -> dict:
    gaz = text_ner.build_gazetteer()
    ent_rows, role_rows = [], []
    docs = db.query("SELECT source_record_id, evidence_id, case_id, modality, text_content, person_id, extra "
                    "FROM events WHERE text_content IS NOT NULL AND text_content <> ''")
    for d in docs:
        is_fir = d["modality"] == "FIR"
        ents = text_ner.extract(d["text_content"], gaz, d["case_id"], with_roles=is_fir)
        for e in ents:
            ent_rows.append((d["source_record_id"], d["evidence_id"], d["case_id"], d["modality"], e.text, e.type,
                             e.role if is_fir else None, e.start, e.end, e.normalized, e.linked_person_id, e.confidence))
        if not is_fir:
            continue
        x = d["extra"]
        # structured fields recorded by police (highest confidence)
        acc = x.get("accused_person_ids") or []
        if d["person_id"]:
            role_rows.append((d["person_id"], d["case_id"], "COMPLAINANT", d["source_record_id"], d["evidence_id"],
                              "FIR_STRUCTURED", 0.97))
        for i, a in enumerate(acc):
            r = "PRINCIPAL_ACCUSED" if i == 0 and x.get("record_type") == "FIR" else "ACCUSED"
            role_rows.append((a, d["case_id"], r, d["source_record_id"], d["evidence_id"], "FIR_STRUCTURED", 0.97))
        for pid, (role, conf) in text_ner.person_roles(ents).items():
            if pid in acc or pid == d["person_id"]:
                continue        # structured police fields take precedence over text-derived roles
            role_rows.append((pid, d["case_id"], role, d["source_record_id"], d["evidence_id"], "FIR_NER", conf))
    db.execute("TRUNCATE text_entities, person_case_roles")
    db.execute_values("INSERT INTO text_entities (source_record_id, evidence_id, case_id, modality, entity_text, "
                      "entity_type, role, span_start, span_end, normalized, linked_person_id, confidence) VALUES %s",
                      ent_rows)
    db.execute_values("INSERT INTO person_case_roles (person_id, case_id, role, source_record_id, evidence_id, method, "
                      "confidence) VALUES %s ON CONFLICT DO NOTHING", role_rows)
    # every person who is the subject of records obtained in a case (but not named in FIR text)
    db.execute("""INSERT INTO person_case_roles (person_id, case_id, role, method, confidence)
                  SELECT DISTINCT person_id, case_id, 'RECORD_SUBJECT', 'RECORD_SUBJECT', 1.0 FROM events e
                  WHERE person_id IS NOT NULL AND modality <> 'FIR' AND NOT EXISTS (
                      SELECT 1 FROM person_case_roles r WHERE r.person_id=e.person_id AND r.case_id=e.case_id)
                  ON CONFLICT DO NOTHING""")
    return {"documents": len(docs), "entities": len(ent_rows), "roles": len(role_rows)}
