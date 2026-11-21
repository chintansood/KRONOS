"""New-case intake: an investigator registers a case (FIR particulars, people, identifiers, statement) and KRONOS
processes it exactly like every other source.

    validate → intake checks (people already on record, identifiers seen in other cases, duplicate FIR, delay)
    → raw record + canonical SHA-256 → normalised FIR event (same FIR loader as bulk ingestion)
    → provenance ledger block + Merkle anchor → recorded roles (structured, confidence 0.97) + NER over the statement
    → identity candidates for the new people (never merged automatically) → prior-record linkage (context only)
    → case summary → retrieval index for the assistant.

Linking a person to an existing record happens only when the investigator chooses it at the review step. Every
submission is saved to data/intake/<CASE>.json so a full rebuild replays it with the same case and person IDs.
Categories whose victims/accused have statutory identity protection (sexual offences, POCSO, juveniles, kidnapping,
matrimonial cruelty, SC/ST atrocities) are not accepted in this workspace.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .. import db
from ..config import settings
from ..engines.provenance import ledger
from . import normalizer as N
from .base_loader import canonical_hash
from .fir_loader import FIRLoader
from .pipeline import EVENT_COLS

INTAKE_DIR = Path(settings.generated_dir).parent / "intake"
AGENCIES = {"AGY-PB": "Punjab Police", "AGY-HR": "Haryana Police", "AGY-DL": "Delhi Police", "AGY-CHD": "Chandigarh Police"}
EXTRA_CATEGORIES = {
    "Theft": "BNS 303(2)", "Robbery": "BNS 309(4)", "Snatching": "BNS 304(2)", "Cheating": "BNS 318(4)",
    "Criminal Breach of Trust": "BNS 316(2)", "Cyber Fraud (Phishing / OTP)": "BNS 318(4), 319(2); IT Act 66C, 66D",
    "Forgery": "BNS 336(3), 340(2)", "Hurt / Assault": "BNS 115(2), 351(2)", "Arms Act": "Arms Act 25(1)(a)",
    "Excise Act (Illicit Liquor)": "Punjab Excise Act 61(1)(14)", "Gambling": "Public Gambling Act 13",
}
RESTRICTED = re.compile(r"sexual|rape|molest|outrag\w* (the )?modesty|pocso|child|minor|juvenile|kidnap|abduct|traffick|"
                        r"dowry|matrimon|cruelty by husband|498-?a|sc/?st|atrocit|\bbns 6[3-9]\b|\bbns 7[0-9]\b|\bipc 376", re.I)
RESTRICTED_NOTE = ("Sexual offences, POCSO, juvenile, kidnapping/trafficking, matrimonial-cruelty and SC/ST-atrocity cases carry "
                   "statutory identity protection and are handled in a restricted module, not in this workspace.")
RANKS = ["Inspector", "Sub-Inspector", "Assistant Sub-Inspector", "Deputy Superintendent of Police", "Head Constable"]
ROLES_OTHER = {"VICTIM", "WITNESS"}
_lock = threading.Lock()


class IntakeError(ValueError):
    def __init__(self, errors: list[dict]):
        super().__init__("; ".join(e["message"] for e in errors))
        self.errors = errors


# ------------------------------------------------------------------------------------------------ options for the form
def _station_code(station: str) -> str:
    known = db.query_one("SELECT fir_number FROM cases WHERE police_station=%s AND fir_number LIKE 'FIR/%%' LIMIT 1", (station,))
    if known:
        return known["fir_number"].split("/")[1]
    return re.sub(r"[^A-Z]", "", re.sub(r"^PS\s+", "", station.upper()))[:12] or "PS"


def _withdrawn() -> list[dict]:
    """Case and FIR numbers of withdrawn intake cases. Like cancelled FIR numbers they are never issued again,
    so an evidence ID on the ledger always refers to one record only."""
    return [r["metadata"] for r in db.query("SELECT DISTINCT ON (metadata->>'caseId') metadata FROM ledger_blocks "
                                            "WHERE event_type='WITHDRAWN' AND metadata ? 'caseId'")]


def next_fir_number(station: str, year: int | None = None) -> str:
    code, year = _station_code(station), year or datetime.now().year
    taken = [r["fir_number"] for r in db.query("SELECT fir_number FROM cases WHERE fir_number LIKE %s", (f"FIR/{code}/{year}/%",))]
    taken += [w.get("firNumber") or "" for w in _withdrawn() if (w.get("firNumber") or "").startswith(f"FIR/{code}/{year}/")]
    nums = [int(f.rsplit("/", 1)[1]) for f in taken if f.rsplit("/", 1)[1].isdigit()]
    return f"FIR/{code}/{year}/{(max(nums) + 1 if nums else 1):04d}"


def next_case_id(reserved: set[str] = frozenset()) -> str:
    used = {r["case_id"] for r in db.query("SELECT case_id FROM cases")} | set(reserved)
    used |= {p.stem for p in INTAKE_DIR.glob("CASE*.json")} | {w["caseId"] for w in _withdrawn()}
    used |= {f"CASE{r['e'][8:11]}" for r in db.query("SELECT DISTINCT evidence_id e FROM ledger_blocks WHERE evidence_id LIKE 'EVD-FIRN%%'")}
    for n in range(41, 900):
        cid = f"CASE{n:03d}"
        if cid not in used:
            return cid
    raise RuntimeError("no free case number")


def _next_person_ids(k: int, reserved: set[str] = frozenset()) -> list[str]:
    used = {r["person_id"] for r in db.query("SELECT person_id FROM persons")} | set(reserved)
    for f in INTAKE_DIR.glob("CASE*.json"):
        used |= set(json.loads(f.read_text()).get("personIds", {}).values())
    start = max([int(p[1:]) for p in used if re.fullmatch(r"P\d{5}", p) and int(p[1:]) < 90000] or [0]) + 1
    return [f"P{n:05d}" for n in range(start, start + k)]


def options() -> dict:
    stations = db.query("SELECT DISTINCT police_station, district, agency_id FROM cases WHERE police_station IS NOT NULL "
                        "AND coalesce(origin,'SYNTHETIC') <> 'PUBLIC_RECORD' ORDER BY 1")
    cats = db.query("SELECT offence_category c, count(*) n FROM cases WHERE coalesce(origin,'SYNTHETIC') <> 'PUBLIC_RECORD' "
                    "AND offence_category IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
    secs = {}
    for r in db.query("SELECT extra->>'offence_category' c, extra->>'sections' s, count(*) n FROM events WHERE modality='FIR' "
                      "AND extra->>'sections' <> '' GROUP BY 1, 2 ORDER BY 3 DESC"):
        secs.setdefault(r["c"], r["s"])
    categories = [{"name": c["c"], "sections": secs.get(c["c"], ""), "cases": c["n"]} for c in cats if not RESTRICTED.search(c["c"])]
    categories += [{"name": k, "sections": v, "cases": 0} for k, v in EXTRA_CATEGORIES.items() if k not in {c["name"] for c in categories}]
    places = db.query("SELECT location_name name, round(avg(latitude)::numeric, 5)::float lat, round(avg(longitude)::numeric, 5)::float lon, "
                      "count(*) n FROM events WHERE location_name IS NOT NULL AND latitude IS NOT NULL AND modality IN ('LOCATION','FIR') "
                      "GROUP BY 1 ORDER BY 4 DESC LIMIT 400")
    districts = {}
    for s in stations:
        districts.setdefault(s["district"], s["agency_id"])
    return {
        "agencies": [{"id": k, "name": v} for k, v in AGENCIES.items()],
        "stations": [{"name": s["police_station"], "district": s["district"], "agencyId": s["agency_id"],
                      "nextFir": next_fir_number(s["police_station"])} for s in stations],
        "districts": [{"name": k, "agencyId": v} for k, v in sorted(districts.items())],
        "categories": categories, "restrictedNote": RESTRICTED_NOTE,
        "places": [{"name": p["name"], "lat": p["lat"], "lon": p["lon"]} for p in places],
        "ranks": RANKS, "informationTypes": ["Written complaint", "Oral statement", "e-FIR (online)", "Suo motu (police)"],
        "nextCaseId": next_case_id(),
    }


# ------------------------------------------------------------------------------------------------ validation + checks
def _s(v) -> str:
    return str(v).strip() if v is not None else ""


def _dt(v) -> datetime | None:
    v = _s(v)
    for f in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(v, f)
        except ValueError:
            pass
    return None


def _people(p: dict) -> list[tuple[str, dict]]:
    """(reference, entry) for every named person in the submission."""
    out = [("complainant", p.get("complainant") or {})]
    out += [(f"accused.{i}", a) for i, a in enumerate(p.get("accused") or []) if not a.get("unknown") and _s(a.get("name"))]
    out += [(f"others.{i}", o) for i, o in enumerate(p.get("others") or []) if _s(o.get("name"))]
    return out


def _list(v) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[,;\n]+", v)
    return [x.strip() for x in (v or []) if x and str(x).strip()]


def validate(p: dict) -> tuple[list[dict], list[dict]]:
    errs, warns = [], []
    E = lambda f, m: errs.append({"field": f, "message": m})
    W = lambda f, m: warns.append({"field": f, "message": m})
    r, o, oc, c = p.get("registration") or {}, p.get("offence") or {}, p.get("occurrence") or {}, p.get("complainant") or {}
    for f, v, label in (("registration.policeStation", r.get("policeStation"), "Police station"), ("registration.district", r.get("district"), "District"),
                        ("registration.firNumber", r.get("firNumber"), "FIR number"), ("offence.category", o.get("category"), "Offence category"),
                        ("offence.title", o.get("title"), "Case title"), ("occurrence.place", oc.get("place"), "Place of occurrence"),
                        ("complainant.name", c.get("name"), "Complainant / informant name")):
        if not _s(v):
            E(f, f"{label} is required")
    if _s(r.get("agencyId")) not in AGENCIES:
        E("registration.agencyId", "Choose the state police unit")
    reg, inc, inc_to = _dt(r.get("registeredAt")), _dt(oc.get("from")), _dt(oc.get("to")) if _s(oc.get("to")) else None
    if not reg:
        E("registration.registeredAt", "Registration date and time are required (YYYY-MM-DD HH:MM)")
    if not inc:
        E("occurrence.from", "Date and time of occurrence are required (YYYY-MM-DD HH:MM)")
    # "now" is the investigator's clock (the browser sends it): the server may run in another timezone (Docker/WSL use UTC)
    now = datetime.now()
    cn = _dt(p.get("clientNow"))
    if cn and abs((cn - now).total_seconds()) < 27 * 3600:
        now = cn
    if reg and reg > now + timedelta(minutes=5):
        E("registration.registeredAt", "Registration time is in the future")
    if inc and reg and inc > reg:
        E("occurrence.from", "The occurrence cannot be after the FIR was registered")
    if inc and inc_to and inc_to < inc:
        E("occurrence.to", "'Occurred until' is before 'occurred from'")
    if inc and reg and (reg - inc).total_seconds() > 24 * 3600 and not _s(oc.get("delayReason")):
        W("occurrence.delayReason", f"Reported {round((reg - inc).total_seconds() / 3600)} h after the occurrence — record the reason for the delay (FIR item 8)")
    if RESTRICTED.search(_s(o.get("category"))) or RESTRICTED.search(_s(o.get("sections"))):
        E("offence.category", RESTRICTED_NOTE)
    if not _s(o.get("sections")):
        W("offence.sections", "No Acts & Sections recorded — add them before the FIR is forwarded to court")
    if _s(r.get("firNumber")) and db.query_one("SELECT case_id FROM cases WHERE fir_number=%s", (_s(r.get("firNumber")),)):
        E("registration.firNumber", f"FIR number {_s(r.get('firNumber'))} is already registered")
    elif _s(r.get("firNumber")) and any(w.get("firNumber") == _s(r.get("firNumber")) for w in _withdrawn()):
        E("registration.firNumber", f"FIR number {_s(r.get('firNumber'))} belonged to a withdrawn case and cannot be reused")
    acc = p.get("accused") or []
    if not acc:
        E("accused", "Add at least one accused — use 'unknown person(s)' if not yet identified")
    if sum(1 for a in acc if not a.get("unknown") and _s(a.get("name"))) == 0 and not any(a.get("unknown") for a in acc):
        E("accused", "Each accused needs a name, or mark them as unknown")
    for ref, e in _people(p):
        ph = _s(e.get("phone"))
        if ph and not N.phone(ph):
            E(f"{ref}.phone", f"'{ph}' is not a valid 10-digit mobile number")
        if e.get("linkTo") and not db.query_one("SELECT 1 FROM persons WHERE person_id=%s AND coalesce(origin,'SYNTHETIC') <> 'PUBLIC_RECORD'", (e["linkTo"],)):
            E(f"{ref}.linkTo", f"{e['linkTo']} is not a linkable person record")
    if len(_s(p.get("narrative"))) < 40:
        E("narrative", "The FIR contents (complainant's statement) are required — at least a few sentences")
    oc_lat, oc_lon = oc.get("lat"), oc.get("lon")
    if (oc_lat not in (None, "") or oc_lon not in (None, "")):
        la, ok1 = N.to_float(oc_lat, -90, 90); lo, ok2 = N.to_float(oc_lon, -180, 180)
        if not (ok1 and ok2) or la is None or lo is None:
            E("occurrence.lat", "Coordinates must be valid latitude / longitude")
    return errs, warns


def check(p: dict) -> dict:
    """Everything the investigator should see before registering: problems, people already on record, identifiers
    already seen in other cases. Nothing is linked here — the investigator decides."""
    from ..engines.identity.resolver import name_similarity
    errs, warns = validate(p)
    persons = db.query("SELECT person_id, display_name, names, phones, accounts FROM persons WHERE coalesce(origin,'SYNTHETIC') <> 'PUBLIC_RECORD'")
    roles = {}
    for r in db.query("SELECT person_id, case_id, role FROM person_case_roles WHERE role <> 'RECORD_SUBJECT'"):
        roles.setdefault(r["person_id"], []).append(f"{r['role'].lower().replace('_', ' ')} in {r['case_id']}")
    matches = []
    for ref, e in _people(p):
        name, ph = _s(e.get("name")), N.phone(e.get("phone"))
        accts = {N.account(a) for a in _list(e.get("accounts"))}
        cands = []
        for q in persons:
            basis, score = [], 0.0
            if ph and ph in (q["phones"] or []):
                basis.append(f"same mobile number {ph}"); score += 0.6
            shared_acc = accts & set(q["accounts"] or [])
            if shared_acc:
                basis.append(f"same account {sorted(shared_acc)[0]}"); score += 0.6
            if name:
                ns, _ = max((name_similarity(name, n) for n in (q["names"] or [q["display_name"]])), key=lambda t: t[0])
                alias = _s(e.get("alias"))
                if alias:
                    ns = max(ns, max(name_similarity(alias, n)[0] for n in (q["names"] or [q["display_name"]])))
                if ns >= 0.85:
                    basis.append(f"name similarity {ns:.2f}"); score += 0.35 * ns
            if basis and (score >= 0.6 or len(basis) > 1 or any("name similarity 1.00" in b for b in basis)):
                cands.append({"personId": q["person_id"], "name": q["display_name"], "basis": basis, "score": round(min(score, 1.0), 2),
                              "recordedRoles": roles.get(q["person_id"], [])[:4],
                              "note": "same identifier — likely the same person; confirm before linking" if score >= 0.6 else
                                      "name only — may be a different person with the same name"})
        cands.sort(key=lambda x: -x["score"])
        if cands:
            matches.append({"ref": ref, "entered": name or ph, "candidates": cands[:3]})
    hits = []
    idents = [("PHONE", N.phone(e.get("phone"))) for _, e in _people(p) if N.phone(e.get("phone"))]
    pr = p.get("property") or {}
    idents += [("ACCOUNT", N.account(a)) for a in _list(pr.get("accounts"))] + [("VEHICLE", v.upper()) for v in _list(pr.get("vehicles"))]
    idents += [("DEVICE", d) for d in _list(pr.get("devices"))]
    for kind, v in dict.fromkeys(idents):
        if kind == "PHONE":
            rows = db.query("SELECT case_id, count(*) n FROM events WHERE phone_number=%s OR counterpart_phone=%s GROUP BY 1 ORDER BY 2 DESC", (v, v))
        elif kind == "ACCOUNT":
            rows = db.query("SELECT case_id, count(*) n FROM events WHERE account_number=%s OR counterpart_account=%s GROUP BY 1 ORDER BY 2 DESC", (v, v))
        elif kind == "DEVICE":
            rows = db.query("SELECT case_id, count(*) n FROM events WHERE device_id=%s OR sim_id=%s GROUP BY 1 ORDER BY 2 DESC", (v, v))
        else:
            rows = db.query("SELECT case_id, count(*) n FROM text_entities WHERE entity_type='VEHICLE' AND normalized=%s GROUP BY 1", (v,))
        if rows:
            hits.append({"kind": kind, "value": v, "cases": [{"caseId": r["case_id"], "records": r["n"]} for r in rows[:5]],
                         "records": sum(r["n"] for r in rows)})
    reg, inc = _dt((p.get("registration") or {}).get("registeredAt")), _dt((p.get("occurrence") or {}).get("from"))
    return {"ok": not errs, "errors": errs, "warnings": warns, "matches": matches, "identifierHits": hits,
            "delayHours": round((reg - inc).total_seconds() / 3600, 1) if reg and inc else None,
            "caseIdPreview": next_case_id(),
            "note": "Matches are suggestions. A person is linked to an existing record only if you choose it; otherwise a new "
                    "record is created and KRONOS raises an identity candidate for review."}


# ------------------------------------------------------------------------------------------------ the FIR text
def _particular(e: dict, with_phone=True) -> str:
    s = _s(e.get("name"))
    if _s(e.get("alias")):
        s += f" @ {_s(e['alias'])}"
    if _s(e.get("relative")):
        s += f" {(_s(e.get('relation')) or 'S/o')} {_s(e['relative'])}"
    if _s(e.get("address")):
        s += f", R/o {_s(e['address'])}"
    if with_phone and N.phone(e.get("phone")):
        s += f" (mobile {N.phone(e['phone'])})"
    return s


def compose_text(p: dict) -> str:
    """The statement as entered, followed by the particulars in the standard FIR form (this is what NER reads)."""
    text = _s(p.get("narrative"))
    c = p.get("complainant") or {}
    parts = [f"Complainant/informant: {_particular(c)}" + (f", age {_s(c.get('age'))}" if _s(c.get("age")) else "") +
             (f", occupation {_s(c.get('occupation'))}" if _s(c.get("occupation")) else "") + "."]
    known = [a for a in (p.get("accused") or []) if not a.get("unknown") and _s(a.get("name"))]
    unknown = [a for a in (p.get("accused") or []) if a.get("unknown")]
    if known:
        parts.append("Particulars of accused: " + "; ".join(f"{i + 1}) {_particular(a)}" for i, a in enumerate(known)) + ".")
    if unknown:
        parts.append(f"Unknown accused: {len(unknown)} person(s)" + "".join(f"; {_s(a.get('description'))}" for a in unknown if _s(a.get("description"))) + ".")
    for o in p.get("others") or []:
        if _s(o.get("name")):
            parts.append(f"{'Victim' if o.get('role') == 'VICTIM' else 'Witness'}: {_particular(o)}.")
    pr = p.get("property") or {}
    if _s(pr.get("description")) or _s(pr.get("value")):
        parts.append(f"Property involved: {_s(pr.get('description')) or 'not specified'}" +
                     (f", value approximately Rs {_s(pr.get('value'))}" if _s(pr.get("value")) else "") + ".")
    for label, key in (("Accounts / UPI involved", "accounts"), ("Vehicles involved", "vehicles"), ("Devices involved", "devices")):
        if _list(pr.get(key)):
            parts.append(f"{label}: {', '.join(_list(pr.get(key)))}.")
    return text.rstrip() + "\n\n" + " ".join(parts)


# ------------------------------------------------------------------------------------------------ registration
def register(p: dict, actor: str | None = None, case_id: str | None = None, person_ids: dict | None = None,
             save: bool = True, warm: bool = True) -> dict:
    errs, warns = validate(p)
    if errs:
        raise IntakeError(errs)
    t0 = datetime.now()
    hits = check(p)["identifierHits"] if case_id is None else (p.get("_intakeHits") or [])
    with _lock:
        cid = case_id or next_case_id()
        num = int(cid[4:])
        people = _people(p)
        person_ids = dict(person_ids or {})
        new_refs = [ref for ref, e in people if not e.get("linkTo") and ref not in person_ids]
        for ref, pid in zip(new_refs, _next_person_ids(len(new_refs), set(person_ids.values()))):
            person_ids[ref] = pid
        for ref, e in people:
            if e.get("linkTo"):
                person_ids[ref] = e["linkTo"]
        r, o, oc, c, pr = (p.get(k) or {} for k in ("registration", "offence", "occurrence", "complainant", "property"))
        reg, inc = _dt(r["registeredAt"]), _dt(oc["from"])
        officer = p.get("officer") or {}
        actor = actor or _s(officer.get("name")) or "investigator"
        text = compose_text(p)
        accused_pids = [person_ids[ref] for ref, e in people if ref.startswith("accused.")]
        # principal accused first
        acc_entries = [(person_ids[f"accused.{i}"], a) for i, a in enumerate(p.get("accused") or []) if f"accused.{i}" in person_ids]
        acc_entries.sort(key=lambda t: 0 if (t[1].get("role") or "PRINCIPAL_ACCUSED") == "PRINCIPAL_ACCUSED" else 1)
        accused_pids = [pid for pid, _ in acc_entries]
        la, _ = N.to_float(oc.get("lat"), -90, 90); lo, _ = N.to_float(oc.get("lon"), -180, 180)
        if la is None or lo is None:     # a known place gives coordinates for the travel and location engines
            known = db.query_one("SELECT avg(latitude) la, avg(longitude) lo FROM events WHERE location_name=%s AND latitude IS NOT NULL", (_s(oc["place"]),))
            la, lo = (known["la"], known["lo"]) if known and known["la"] is not None else (None, None)
        src, evd = f"SRC-FIRN{num:03d}001", f"EVD-FIRN{num:03d}001"
        row = {"fir_number": _s(r["firNumber"]), "record_id": f"FIRN{num:03d}001", "case_id": cid, "record_type": "FIR",
               "agency_id": r["agencyId"], "police_station": _s(r["policeStation"]), "district": _s(r["district"]),
               "registration_date": reg.strftime("%Y-%m-%d"), "registration_time": reg.strftime("%H:%M"),
               "incident_datetime": inc.strftime("%d-%m-%Y %H:%M"), "offence_category": _s(o["category"]), "sections": _s(o.get("sections")),
               "complainant_person_id": person_ids["complainant"], "complainant_name": _s(c["name"]),
               "accused_person_ids": ";".join(accused_pids), "incident_location": _s(oc["place"]),
               "incident_lat": "" if la is None else f"{la:.5f}", "incident_lon": "" if lo is None else f"{lo:.5f}",
               "narrative": text, "source_reliability": "HIGH", "evidence_id": evd, "source_record_id": src}
        sha = canonical_hash(row)
        ev, issues = FIRLoader().to_event(row)
        ev["extra"].update({"intake": True, "information_type": _s(r.get("informationType")) or "Written complaint",
                            "occurred_until": _s(oc.get("to")) or None, "delay_reason": _s(oc.get("delayReason")) or None,
                            "unknown_accused": sum(1 for a in (p.get("accused") or []) if a.get("unknown")),
                            "property": pr, "officer": officer, "registered_by": actor})
        run_id = f"RUN-INT-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
        # --- persons: new records for new people. People linked to an existing record are not modified — the
        #     identifiers the investigator entered for them live in this FIR (and its entities), so a withdrawal
        #     leaves existing records exactly as they were.
        for ref, e in people:
            if e.get("linkTo"):
                continue
            pid = person_ids[ref]
            names = [x for x in (_s(e.get("name")), _s(e.get("alias"))) if x]
            phones = [N.phone(e.get("phone"))] if N.phone(e.get("phone")) else []
            accts = [N.account(a) for a in _list(e.get("accounts"))]
            db.execute("INSERT INTO persons (person_id, display_name, names, phones, devices, sims, accounts, first_seen, last_seen, "
                       "is_subject, origin) VALUES (%s,%s,%s,%s,'{}','{}',%s,%s,%s,%s,'INTAKE') ON CONFLICT (person_id) DO UPDATE SET "
                       "display_name=EXCLUDED.display_name, names=EXCLUDED.names, phones=EXCLUDED.phones, accounts=EXCLUDED.accounts",
                       (pid, names[0], names, phones, accts, inc, reg, ref == "complainant"))
        # --- raw record, event, issues, ledger
        db.execute("INSERT INTO ingestion_runs (run_id, source_dir, stats) VALUES (%s,%s,%s)",
                   (run_id, "INTAKE", db.Json({"caseId": cid, "registeredBy": actor})))
        db.execute("INSERT INTO raw_records (source_record_id, modality, case_id, file_name, row_number, raw, content_sha256, quarantined, run_id) "
                   "VALUES (%s,'FIR',%s,'INTAKE',1,%s,%s,FALSE,%s)", (src, cid, db.Json(row), sha, run_id))
        db.execute_values(f"INSERT INTO events ({','.join(EVENT_COLS)}) VALUES %s",
                          [tuple(db.Json(ev.get(k) or {}) if k == "extra" else ev.get(k) for k in EVENT_COLS)])
        if issues:
            db.execute_values("INSERT INTO ingestion_issues (run_id, modality, file_name, row_number, source_record_id, severity, field, issue, raw_value) "
                              "VALUES %s", [(run_id, "FIR", "INTAKE", 1, src, x.severity, x.field, x.issue, x.raw_value) for x in issues])
        ledger.append_many([("INGEST", evd, sha, actor, {"source_record_id": src, "file": "INTAKE", "row": 1, "run_id": run_id,
                                                          "quarantined": False, "caseId": cid, "channel": "case intake"})])
        anchor = ledger.anchor_batch(run_id, "INTAKE")
        db.execute("INSERT INTO cases (case_id, title, offence_category, description, status, priority, fir_number, police_station, district, "
                   "agency_id, incident_ts, registration_ts, incident_location, incident_lat, incident_lon, lead_investigator, is_custom, origin, source) "
                   "VALUES (%s,%s,%s,%s,'ACTIVE',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,'INTAKE',%s) ON CONFLICT (case_id) DO NOTHING",
                   (cid, _s(o["title"]), _s(o["category"]), None, (_s(o.get("priority")) or "MEDIUM").upper(), _s(r["firNumber"]),
                    _s(r["policeStation"]), _s(r["district"]), r["agencyId"], inc, reg, _s(oc["place"]), la, lo,
                    _s(officer.get("leadInvestigator")) or " ".join(x for x in (_s(officer.get("rank")), _s(officer.get("name"))) if x) or "Investigating Officer",
                    db.Json({"registeredBy": actor, "registeredVia": p.get("channel") or "form", "informationType": _s(r.get("informationType")),
                             "sections": _s(o.get("sections")), "runId": run_id, "intakeHits": hits,
                             "unknownAccused": [_s(a.get("description")) for a in (p.get("accused") or []) if a.get("unknown")],
                             "delayReason": _s(oc.get("delayReason")) or None, "occurredUntil": _s(oc.get("to")) or None,
                             "property": pr, "officer": officer})))
        # --- recorded roles: structured fields first (as police record them), then NER over the statement
        roles = [(person_ids["complainant"], "COMPLAINANT")]
        if c.get("isVictim"):
            roles.append((person_ids["complainant"], "VICTIM"))
        roles += [(pid, "PRINCIPAL_ACCUSED" if i == 0 and (a.get("role") or "PRINCIPAL_ACCUSED") == "PRINCIPAL_ACCUSED" else "ACCUSED")
                  for i, (pid, a) in enumerate(acc_entries)]
        roles += [(person_ids[f"others.{i}"], o2.get("role") if o2.get("role") in ROLES_OTHER else "WITNESS")
                  for i, o2 in enumerate(p.get("others") or []) if f"others.{i}" in person_ids]
        db.execute_values("INSERT INTO person_case_roles (person_id, case_id, role, source_record_id, evidence_id, method, confidence) "
                          "VALUES %s ON CONFLICT DO NOTHING", [(pid, cid, role, src, evd, "FIR_STRUCTURED", 0.97) for pid, role in roles])
        ner = _ner(cid, src, evd, text, {person_ids[ref]: e for ref, e in people}, {pid for pid, _ in roles})
    # --- engines that need the whole picture (outside the lock: read-only over shared data)
    new_pids = sorted({person_ids[ref] for ref, e in people if not e.get("linkTo")})
    ident = _identity(new_pids)
    from ..engines.multimodal import summarizer
    summarizer.generate_case_summary(cid)
    from ..engines.llm import retrieval
    try:
        idx = retrieval.index_cases([cid], embed=True)
    except Exception as e:                     # the case is registered even if the embedding model is offline
        idx = {"warning": str(e)}
    record = {"caseId": cid, "registeredAt": datetime.now().isoformat(timespec="seconds"), "registeredBy": actor,
              "personIds": person_ids, "payload": {**p, "_intakeHits": hits}}
    if save:
        INTAKE_DIR.mkdir(parents=True, exist_ok=True)
        (INTAKE_DIR / f"{cid}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False, default=str))
    if warm:
        _warm_async()
    return {"caseId": cid, "evidenceId": evd, "sourceRecordId": src, "sha256": sha, "runId": run_id,
            "ledger": {"anchor": anchor.get("merkleRoot") if isinstance(anchor, dict) else None, "blocks": 2},
            "persons": [{"ref": ref, "personId": person_ids[ref], "name": _s(e.get("name")), "linked": bool(e.get("linkTo"))} for ref, e in people],
            "roles": [{"personId": pid, "role": role} for pid, role in roles], "entities": ner, **ident, "index": idx,
            "identifierHits": hits,
            "warnings": warns, "seconds": round((datetime.now() - t0).total_seconds(), 1)}


def _ner(cid, src, evd, text, entries: dict, structured: set) -> dict:
    from ..engines.multimodal import text_ner
    gaz = text_ner.build_gazetteer()
    for pid in entries:
        gaz.person_cases.setdefault(pid, set()).add(cid)
    ents = text_ner.extract(text, gaz, cid, with_roles=True)
    # the investigator told us who is who: names (and aliases) entered on the form link with certainty
    by_name = {}
    for pid, e in entries.items():
        for n in (_s(e.get("name")), _s(e.get("alias"))):
            if n:
                by_name[n.lower()] = pid
    last = None
    for e in sorted(ents, key=lambda x: x.start):
        if e.type in ("PERSON", "ALIAS"):
            if e.text.lower() in by_name:
                e.linked_person_id, e.confidence = by_name[e.text.lower()], 0.97
            last = e.linked_person_id
        elif e.type in ("FATHER_NAME", "ADDRESS"):
            e.linked_person_id = last
    db.execute_values("INSERT INTO text_entities (source_record_id, evidence_id, case_id, modality, entity_text, entity_type, role, span_start, "
                      "span_end, normalized, linked_person_id, confidence) VALUES %s",
                      [(src, evd, cid, "FIR", e.text, e.type, e.role, e.start, e.end, e.normalized, e.linked_person_id, e.confidence) for e in ents]) if ents else None
    extra = [(pid, cid, role, src, evd, "FIR_NER", conf) for pid, (role, conf) in text_ner.person_roles(ents).items() if pid not in structured]
    if extra:      # people already on record whom the statement mentions (e.g. a known associate)
        db.execute_values("INSERT INTO person_case_roles (person_id, case_id, role, source_record_id, evidence_id, method, confidence) "
                          "VALUES %s ON CONFLICT DO NOTHING", extra)
    kinds = {}
    for e in ents:
        kinds[e.type] = kinds.get(e.type, 0) + 1
    return {"total": len(ents), "byType": kinds, "mentionedOnRecord": [x[0] for x in extra]}


def _identity(new_pids: list[str]) -> dict:
    if not new_pids:
        return {"identityCandidates": [], "priorRecordLinks": 0}
    from ..engines.identity import history, resolver
    ctx = resolver.Ctx()
    cands = resolver.candidates_for(new_pids, ctx)
    hl = history.link_all(only=set(new_pids), ctx=ctx)
    return {"identityCandidates": [{"candidateId": c["candidateId"], "other": c["personB"] if c["personA"] in new_pids else c["personA"],
                                    "band": c["band"], "score": c["score"]} for c in cands if c["band"] != "INSUFFICIENT_EVIDENCE"],
            "priorRecordLinks": hl.get("candidateLinks", 0)}


def _warm_async():
    """Recompute the shared analytics for the new data version in the background, so the next page loads are fast."""
    def run():
        try:
            from ..api import serializers
            from ..engines.graph import analytics
            from ..engines.multimodal import financial
            financial.analysis(); serializers.cases(); serializers.persons(); analytics.metrics(); analytics.cross_case()
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


# ------------------------------------------------------------------------------------------------ withdraw / replay
def withdraw(case_id: str, reason: str = "", actor: str = "investigator") -> dict:
    c = db.query_one("SELECT * FROM cases WHERE case_id=%s", (case_id,))
    if not c or not c["is_custom"]:
        raise IntakeError([{"field": "caseId", "message": "Only cases registered through intake can be withdrawn"}])
    rec_file = INTAKE_DIR / f"{case_id}.json"
    rec = json.loads(rec_file.read_text()) if rec_file.exists() else {}
    srcs = [r["source_record_id"] for r in db.query("SELECT source_record_id FROM raw_records WHERE case_id=%s", (case_id,))]
    evds = [r["evidence_id"] for r in db.query("SELECT evidence_id FROM events WHERE case_id=%s", (case_id,))]
    # people this intake created: intake-origin records with a role in this case (or listed in the saved submission)
    own = [r["person_id"] for r in db.query("SELECT person_id FROM persons WHERE origin='INTAKE' AND (person_id = ANY(%s) OR person_id IN "
                                             "(SELECT person_id FROM person_case_roles WHERE case_id=%s))",
                                             (list((rec.get("personIds") or {}).values()), case_id))]
    # people created by this intake stay if another case now refers to them
    keep = {r["person_id"] for r in db.query("SELECT DISTINCT person_id FROM person_case_roles WHERE person_id = ANY(%s) AND case_id <> %s", (own, case_id))}
    drop = [p for p in own if p not in keep]
    db.execute("DELETE FROM text_entities WHERE case_id=%s", (case_id,))
    db.execute("DELETE FROM person_case_roles WHERE case_id=%s", (case_id,))
    db.execute("DELETE FROM case_summaries WHERE case_id=%s", (case_id,))
    db.execute("DELETE FROM doc_chunks WHERE case_id=%s OR chunk_id = ANY(%s)", (case_id, [f"PER-{p}" for p in drop]))
    db.execute("DELETE FROM evidence_requests WHERE case_id=%s", (case_id,))
    db.execute("DELETE FROM events WHERE case_id=%s", (case_id,))
    db.execute("DELETE FROM ingestion_issues WHERE source_record_id = ANY(%s)", (srcs,))
    db.execute("DELETE FROM raw_records WHERE case_id=%s", (case_id,))
    if drop:
        db.execute("DELETE FROM identity_candidates WHERE person_a = ANY(%s) OR person_b = ANY(%s)", (drop, drop))
        db.execute("DELETE FROM history_links WHERE person_id = ANY(%s)", (drop,))
        db.execute("DELETE FROM persons WHERE person_id = ANY(%s)", (drop,))
    db.execute("DELETE FROM cases WHERE case_id=%s", (case_id,))
    # the ledger is append-only: the withdrawal itself is recorded, the original blocks remain verifiable
    ledger.append_many([("WITHDRAWN", e, None, actor, {"caseId": case_id, "firNumber": c["fir_number"],
                                                        "reason": reason or "withdrawn by investigator"}) for e in evds])
    if rec_file.exists():
        (INTAKE_DIR / "withdrawn").mkdir(parents=True, exist_ok=True)
        rec_file.rename(INTAKE_DIR / "withdrawn" / f"{case_id}-{datetime.now():%Y%m%d%H%M%S}.json")
    _warm_async()
    return {"caseId": case_id, "withdrawn": True, "personsRemoved": drop, "ledgerBlocks": len(evds)}


def replay_all() -> dict:
    """After a full rebuild: register every saved intake again with the same case and person IDs."""
    done = []
    for f in sorted(INTAKE_DIR.glob("CASE*.json")):
        rec = json.loads(f.read_text())
        if db.query_one("SELECT 1 FROM cases WHERE case_id=%s", (rec["caseId"],)):
            continue
        register(rec["payload"], actor=rec.get("registeredBy"), case_id=rec["caseId"], person_ids=rec.get("personIds"), save=False, warm=False)
        done.append(rec["caseId"])
    return {"replayed": done}
