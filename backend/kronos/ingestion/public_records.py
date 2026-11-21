"""Ingest the pseudonymised real court records (data/public_records) next to the synthetic world.

They go through the same FIR loader, raw-record hashing, issue log and provenance ledger as every other source, plus one
SOURCE_DOCUMENT ledger block per original court order (SHA-256 of the PDF as downloaded, with URL and licence).
Real-case people are flagged origin='PUBLIC_RECORD' and are excluded from identity resolution, criminal-history
fuzzy linking and the NER gazetteer, so no real person can be matched to a synthetic record. Antecedents listed in an
order are linked to that order's petitioner only, with status STATED_IN_SOURCE.
"""
from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime
from pathlib import Path

from .. import db
from ..config import settings
from ..engines.provenance import ledger
from .fir_loader import FIRLoader
from .history_loader import HistoryLoader
from .pipeline import EVENT_COLS, HISTORY_COLS, extract_entities_and_roles


class PublicFIRLoader(FIRLoader):
    file_name = "PUBLIC_FIR.csv"


class PublicHistoryLoader(HistoryLoader):
    file_name = "PUBLIC_HISTORY.csv"


def clear():
    db.execute("DELETE FROM history_links WHERE status='STATED_IN_SOURCE'")
    db.execute("DELETE FROM criminal_history WHERE source_system='COURT_ORDER'")
    db.execute("DELETE FROM events WHERE evidence_id LIKE 'EVD-PUB%%'")
    db.execute("DELETE FROM raw_records WHERE source_record_id LIKE 'SRC-PUB%%' OR source_record_id LIKE 'SRC-HPUB%%'")
    db.execute("DELETE FROM person_case_roles WHERE case_id IN (SELECT case_id FROM cases WHERE origin='PUBLIC_RECORD')")
    db.execute("DELETE FROM case_summaries WHERE case_id IN (SELECT case_id FROM cases WHERE origin='PUBLIC_RECORD')")
    db.execute("DELETE FROM doc_chunks WHERE case_id IN (SELECT case_id FROM cases WHERE origin='PUBLIC_RECORD') "
               "OR chunk_id IN (SELECT 'PER-' || person_id FROM persons WHERE origin='PUBLIC_RECORD')")
    db.execute("DELETE FROM persons WHERE origin='PUBLIC_RECORD'")
    db.execute("DELETE FROM cases WHERE origin='PUBLIC_RECORD'")


def ingest_public_records(source_dir: Path | None = None, embed: bool = True, index: bool = True) -> dict:
    d = Path(source_dir or settings.public_records_dir)
    if not (d / "PUBLIC_FIR.csv").exists():
        return {"skipped": f"no public records in {d}"}
    db.apply_schema()
    clear()
    sources = json.loads((d / "sources.json").read_text())
    run_id = f"RUN-PUB-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
    db.execute("INSERT INTO ingestion_runs (run_id, source_dir) VALUES (%s,%s)", (run_id, str(d)))
    stats = {}
    for loader in (PublicFIRLoader(), PublicHistoryLoader()):
        res = loader.load(d)
        stats[res.file_name] = res.stats
        db.execute_values("INSERT INTO raw_records (source_record_id, modality, case_id, file_name, row_number, raw, content_sha256, "
                          "quarantined, run_id) VALUES %s ON CONFLICT DO NOTHING",
                          [(s, res.modality, c, res.file_name, n, db.Json(raw), sha, q, run_id) for s, c, n, raw, sha, q in res.raw])
        if res.modality == "HISTORY":
            if res.events:
                db.execute_values(f"INSERT INTO criminal_history ({','.join(HISTORY_COLS)}) VALUES %s ON CONFLICT DO NOTHING",
                                  [tuple(e.get(c) for c in HISTORY_COLS) for e in res.events])
        elif res.events:
            db.execute_values(f"INSERT INTO events ({','.join(EVENT_COLS)}) VALUES %s",
                              [tuple(db.Json(e.get(c) or {}) if c == "extra" else e.get(c) for c in EVENT_COLS) for e in res.events])
        db.execute_values("INSERT INTO ingestion_issues (run_id, modality, file_name, row_number, source_record_id, severity, field, "
                          "issue, raw_value) VALUES %s", [(run_id, res.modality, res.file_name, n, s, x.severity, x.field, x.issue,
                                                           x.raw_value) for n, s, x in res.issues]) if res.issues else None
        ev = {e["source_record_id"]: e["evidence_id"] for e in res.events}
        ledger.append_many([("INGEST", ev.get(s) or raw.get("evidence_id"), sha, "ingestion",
                             {"source_record_id": s, "file": res.file_name, "row": n, "run_id": run_id, "quarantined": q})
                            for s, c, n, raw, sha, q in res.raw])
        ledger.anchor_batch(run_id, res.file_name)
    # the original documents: hash of the PDF exactly as downloaded, with where/when/licence
    ledger.append_many([("SOURCE_DOCUMENT", s["evidenceId"], s["sha256"], "public-records-fetcher",
                         {"url": s["url"], "cnr": s["cnr"], "court": s["court"], "caseNumber": s["caseNumber"],
                          "fetchedAt": s["fetchedAt"], "license": s["license"]}) for s in sources.values()])
    persons = json.loads((d / "PUBLIC_PERSONS.json").read_text())
    db.execute_values("INSERT INTO persons (person_id, display_name, names, is_subject, origin) VALUES %s ON CONFLICT (person_id) DO UPDATE "
                      "SET display_name=EXCLUDED.display_name, names=EXCLUDED.names, origin=EXCLUDED.origin",
                      [(p["person_id"], p["display_name"], [p["display_name"]], False, "PUBLIC_RECORD") for p in persons])
    with open(d / "PUBLIC_CASE_REGISTER.csv", newline="", encoding="utf-8") as fh:
        reg = {r["case_id"]: r for r in csv.DictReader(fh)}
    firs = db.query("SELECT case_id, ts, extra, location_name, agency_id FROM events WHERE evidence_id LIKE 'EVD-PUB%%'")
    rows = []
    for f in firs:
        x, r = f["extra"], reg.get(f["case_id"], {})
        inc = datetime.fromisoformat(x["incident_ts"]) if x.get("incident_ts") else None
        rows.append((f["case_id"], r.get("title"), x.get("offence_category"), x.get("fir_number"), x.get("police_station"), x.get("district"),
                     f["agency_id"] or r.get("agency_id"), inc, f["ts"], f["location_name"], "—", "PUBLIC_RECORD",
                     db.Json(sources.get(f["case_id"], {})), "CLOSED" if (sources.get(f["case_id"], {}).get("disposal") or "") else "ACTIVE"))
    db.execute_values("INSERT INTO cases (case_id, title, offence_category, fir_number, police_station, district, agency_id, incident_ts, "
                      "registration_ts, incident_location, lead_investigator, origin, source, status) VALUES %s ON CONFLICT (case_id) DO UPDATE "
                      "SET title=EXCLUDED.title, origin=EXCLUDED.origin, source=EXCLUDED.source", rows)
    # antecedents stated in the order belong to that order's petitioner — a fixed link, not a fuzzy match
    links = []
    with open(d / "PUBLIC_HISTORY.csv", newline="", encoding="utf-8") as fh:
        for h in csv.DictReader(fh):
            links.append((f"HL-{h['record_id']}-{h['_person_id']}", h["record_id"], h["_person_id"], 1.0, "HIGH", db.Json({}),
                          db.Json([f"listed as the petitioner's criminal antecedent in the court order for {h['_case_id']}"]),
                          db.Json([]), "STATED_IN_SOURCE"))
    if links:
        db.execute_values("INSERT INTO history_links (link_id, history_id, person_id, score, band, features, reasons, contradicting, status) "
                          "VALUES %s ON CONFLICT (link_id) DO NOTHING", links)
    stats["ner"] = extract_entities_and_roles()      # recorded roles from the structured accused / complainant fields
    from ..engines.multimodal import summarizer      # (the events cache refreshes itself: raw_records changed)
    cases = sorted(reg)
    for c in cases:
        summarizer.generate_case_summary(c)
    from ..engines.llm import retrieval
    stats["index"] = retrieval.index_cases(cases, embed=embed) if index else "deferred to the full index build"
    db.execute("UPDATE ingestion_runs SET finished_at=now(), stats=%s WHERE run_id=%s", (db.Json(stats), run_id))
    return {"run_id": run_id, "cases": len(cases), "persons": len(persons), "antecedentLinks": len(links), **stats}
