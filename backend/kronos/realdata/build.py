"""Build the KRONOS public-records dataset from real High Court criminal-petition orders.

  python -I scripts/fetch_public_records.py --target 40

Output (data/public_records/), in the same schemas as the synthetic dataset:
  PUBLIC_FIR.csv            FIR_EXTRACT records (real FIR no./date/sections/police station; pseudonymised narrative)
  PUBLIC_HISTORY.csv        criminal antecedents listed in the order (real FIR references; pseudonymised person)
  PUBLIC_PERSONS.json       pseudonymised parties (role labels, scoped to one case)
  PUBLIC_CASE_REGISTER.csv  case titles
  sources.json              provenance per case: court, case number, CNR, decision date, URL, licence, SHA-256, fetch time
  report.json               how many orders were fetched, unreadable, unparsed, excluded (by reason) and included
Only pseudonymised text leaves data/external (which holds the original PDFs/text locally and is git-ignored).
"""
from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter
from pathlib import Path

import httpx

from . import extract as X
from . import fetch as F
from .pseudonymize import Pseudonymizer

FIR_COLS = ["fir_number", "record_id", "case_id", "record_type", "agency_id", "police_station", "district", "registration_date",
            "registration_time", "incident_datetime", "offence_category", "sections", "complainant_person_id", "complainant_name",
            "accused_person_ids", "incident_location", "incident_lat", "incident_lon", "narrative", "source_reliability",
            "evidence_id", "source_record_id"]
HIST_COLS = ["record_id", "source_record_id", "evidence_id", "record_type", "source_system", "full_name", "alias_names", "father_name",
             "birth_year", "address", "phone_at_record", "fir_reference", "offence_category", "sections", "police_station", "district",
             "record_date", "disposition", "modus_operandi", "source_reliability"]
PETITION = {"REGULAR_BAIL": "regular bail", "ANTICIPATORY_BAIL": "anticipatory bail", "QUASHING": "quashing of the FIR",
            "BAIL_CANCELLATION": "cancellation of bail", "SUSPENSION_OF_SENTENCE": "suspension of sentence", "OTHER": "relief"}


def _agency(district: str | None, title: str) -> str:
    st = X.STATE_OF.get(district or "", "")
    if st.startswith("Chandigarh") or re.search(r"CHANDIGARH", title or ""):
        return "AGY-CHD"
    if st == "Haryana" or "HARYANA" in (title or "").upper():
        return "AGY-HR"
    return "AGY-PB"


def _case_no(title: str) -> str:
    m = re.match(r"([A-Z-]+)/(\d+)/(\d{4})", title or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else (title or "")[:30]


def collect(target: int = 40, years=(2025, 2024), seed: int = 20251120, max_fetch: int = 260, per_category: int = 9,
            cache: Path = Path("data/external/hc_pdfs"), log=print) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    cand = []
    for y in years:
        df = F.metadata(y, "3_22")
        df = df[df.title.fillna("").str.match(r"CRM-M/\d+/\d{4} of .+ Vs (STATE OF (PUNJAB|HARYANA)|(THE )?STATE OF U\.?T\.? CHANDIGARH|U\.?T\.? CHANDIGARH)", na=False)]
        cand += df.to_dict("records")
    rng.shuffle(cand)
    stats, cats, docs = Counter(), Counter(), []
    client = httpx.Client(headers={"User-Agent": F.UA}, timeout=30)
    for row in cand:
        if len(docs) >= target or stats["fetched"] >= max_fetch:
            break
        res = F.fetch(F.pdf_url(row), cache, client)
        if not res.get("bytes"):
            stats["missing"] += 1
            continue
        stats["fetched"] += 1
        text, pages, readable = F.text_of(res["bytes"])
        if not readable:
            stats["unreadable_needs_ocr"] += 1
            continue
        ex = X.extract(text, row)
        fir = ex["fir"]
        if not (fir["firNo"] and fir["firDate"] and fir["sections"] and fir["policeStation"]):
            stats["no_fir_particulars"] += 1
            continue
        if ex["exclusionReasons"]:
            stats["excluded"] += 1
            for r in ex["exclusionReasons"]:
                stats[f"excluded: {r}"] += 1
            continue
        if cats[ex["category"]] >= per_category:
            stats["skipped_category_cap"] += 1
            continue
        cats[ex["category"]] += 1
        docs.append({"meta": row, "fetch": {k: v for k, v in res.items() if k != "bytes"}, "pages": pages, "ex": ex})
        log(f"  + {row['cnr']} {ex['category']} FIR {fir['firNo']}/{fir['firYear']} PS {fir['policeStation']}")
    stats["included"] = len(docs)
    stats["byCategory"] = dict(cats)
    return docs, dict(stats)


def to_dataset(docs: list[dict], out: Path, start_case: int = 901) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    docs = sorted(docs, key=lambda d: (str(d["meta"]["decision_date"]), d["meta"]["cnr"]))
    firs, hist, persons, reg, sources = [], [], [], [], {}
    pid_n, h_n = 90001, 1
    pseudo_stats = Counter()
    for k, d in enumerate(docs):
        cid = f"CASE{start_case + k}"
        m, ex, fir = d["meta"], d["ex"], d["ex"]["fir"]
        P = Pseudonymizer(cid)
        parties = P.add_parties(m["title"])
        protected = {fir["policeStation"], fir["district"], "High Court", "Punjab and Haryana"}
        facts, rep = P.apply(ex["facts"] or "", protected)
        for kk, v in rep.items():
            pseudo_stats[kk] += v if isinstance(v, int) else 0
        court = F.COURTS[m["court_code"]][0]
        case_no = _case_no(m["title"])
        decided = str(m["decision_date"])[:10]
        petitioners = [P.map[p.lower()] for p in parties if p.lower() in P.map] or ["[Accused A1]"]
        pet_txt = ", ".join(dict.fromkeys(petitioners))
        outcome = (m.get("disposal_nature") or "").title() or "not stated"
        ant = ex["antecedents"]
        ant_txt = {"NONE": "The order records that the petitioner has no criminal antecedents.",
                   "LISTED": f"The order lists {len(ant['items'])} other FIR(s) against the petitioner.",
                   "MENTIONED": "The order mentions criminal antecedents without listing them."}.get(ant["declared"], "")
        narrative = (f"[Public record · {court}, {case_no}, order dated {decided} · names pseudonymised] "
                     f"{'Facts as recorded in the order: ' + facts if facts else 'The order does not set out the facts of the FIR.'} "
                     f"Court proceedings: petition for {PETITION.get(ex['petitionType'], 'relief')} by {pet_txt}; outcome: {outcome}. {ant_txt}").strip()
        # persons: one per role label that appears in the record
        labels = list(dict.fromkeys(petitioners + re.findall(r"\[(?:Accused|Complainant|Victim|Witness) [A-Z]\d+\]", facts)))
        lab2pid = {}
        for lab in labels:
            lab2pid[lab] = f"P{pid_n}"
            persons.append({"person_id": f"P{pid_n}", "display_name": f"{lab.strip('[]')} · {cid}", "role_label": lab.strip("[]"),
                            "case_id": cid, "origin": "PUBLIC_RECORD"})
            pid_n += 1
        accused = [lab2pid[l] for l in labels if l.startswith("[Accused")]
        comp = next((l for l in labels if l.startswith("[Complainant")), None)
        n = k + 1
        inc = next((X.iso(x) for x in re.findall(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b", facts or "")
                    if X.iso(x) and X.iso(x) <= fir["firDate"]), None)
        secs = ", ".join(fir["sections"] + [f"{s} (added later)" for s in fir.get("sectionsAddedLater") or []])
        firs.append({"fir_number": f"FIR {fir['firNo']}/{fir['firYear']}, PS {fir['policeStation']}", "record_id": f"PUB{n:06d}",
                     "case_id": cid, "record_type": "FIR_EXTRACT", "agency_id": _agency(fir["district"], m["title"]),
                     "police_station": f"PS {fir['policeStation']}", "district": fir["district"] or "",
                     "registration_date": fir["firDate"], "registration_time": "", "incident_datetime": inc or "",
                     "offence_category": ex["category"], "sections": f"{secs} ({' / '.join(fir['acts']) or 'act not stated'})",
                     "complainant_person_id": lab2pid.get(comp, ""), "complainant_name": comp.strip("[]") if comp else "",
                     "accused_person_ids": ";".join(accused),
                     "incident_location": ", ".join(x for x in (fir["district"], X.STATE_OF.get(fir["district"] or "", "Punjab" if fir["district"] else "")) if x),
                     "incident_lat": "", "incident_lon": "", "narrative": narrative, "source_reliability": "HIGH",
                     "evidence_id": f"EVD-PUB{n:06d}", "source_record_id": f"SRC-PUB{n:06d}"})
        reg.append({"case_id": cid, "title": f"{ex['category']} — PS {fir['policeStation']}{', ' + fir['district'] if fir['district'] else ''} (real case, {case_no})",
                    "agency_id": _agency(fir["district"], m["title"]), "lead_investigator": "—"})
        a1 = lab2pid.get(petitioners[0])
        for it in ant["items"] if a1 else []:
            hist.append({"record_id": f"HISTPUB{h_n:05d}", "source_record_id": f"SRC-HPUB{h_n:05d}", "evidence_id": f"EVD-HPUB{h_n:05d}",
                         "record_type": "ANTECEDENT_LISTED_IN_ORDER", "source_system": "COURT_ORDER",
                         "full_name": f"{petitioners[0].strip('[]')} · {cid}", "alias_names": "", "father_name": "", "birth_year": "",
                         "address": "", "phone_at_record": "", "fir_reference": f"FIR {it['firNo']}{'/' + it['year'] if it['year'] else ''}, PS {it['policeStation']}",
                         "offence_category": X.category(X.sections_in(it["sections"]), X.acts_in(it["sections"])), "sections": it["sections"],
                         "police_station": f"PS {it['policeStation']}", "district": fir["district"] or "", "record_date": "",
                         "disposition": "NOT_STATED", "modus_operandi": "", "source_reliability": "HIGH", "_person_id": a1, "_case_id": cid})
            h_n += 1
        sources[cid] = {"court": court, "caseNumber": case_no, "cnr": m["cnr"], "decisionDate": decided, "disposal": m.get("disposal_nature"),
                        "petitionType": ex["petitionType"], "url": d["fetch"]["url"], "sha256": d["fetch"]["sha256"],
                        "fetchedAt": d["fetch"]["fetchedAt"], "license": F.LICENSE, "datasetUrl": F.DATASET_URL, "pages": d["pages"],
                        "firFormat": fir["format"], "evidenceMentioned": ex["evidenceMentioned"], "recoveries": ex["recoveries"],
                        "amountsRs": ex["amounts"], "custodySince": ex["custodySince"], "antecedents": ant["declared"],
                        "pseudonymisation": {kk: v for kk, v in rep.items()}, "evidenceId": f"EVD-PUB{n:06d}",
                        "personIds": list(lab2pid.values())}
    with open(out / "PUBLIC_FIR.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIR_COLS); w.writeheader(); w.writerows(firs)
    with open(out / "PUBLIC_HISTORY.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HIST_COLS + ["_person_id", "_case_id"]); w.writeheader(); w.writerows(hist)
    with open(out / "PUBLIC_CASE_REGISTER.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["case_id", "title", "agency_id", "lead_investigator"]); w.writeheader(); w.writerows(reg)
    (out / "PUBLIC_PERSONS.json").write_text(json.dumps(persons, indent=1))
    (out / "sources.json").write_text(json.dumps(sources, indent=1))
    return {"cases": len(firs), "persons": len(persons), "antecedentRecords": len(hist), "pseudonymisation": dict(pseudo_stats)}
