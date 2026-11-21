"""Evidence retrieval engine — context-aware natural-language search over every evidence record.

A query such as  "cash deposits above 40,000 in March"  or  "calls between Raju and Monu at night"
is interpreted into explicit, inspectable filters (record type, amount range, dates, time of day, persons,
places, phones / accounts / devices, 'flagged only'), then combined with full-text and semantic matching.
Context = the case / person currently open and entities from the conversation: results inside the current
context are boosted (not hard-filtered unless the query says so). Every result states why it matched.
"""
from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta

from ... import db
from ..multimodal.financial import flagged_ids
from ..temporal import travel
from ..temporal.timeline import bursts
from . import retrieval

MOD_WORDS = [
    (r"\b(calls?|called|calling|cdrs?|phone calls?|rang)\b", "CDR"),
    (r"\b(messages?|chats?|whatsapp|telegram|instagram|texts?|messaged)\b", "SOCIAL"),
    (r"\b(sms)\b", "CDR"),
    (r"\b(transactions?|transfers?|payments?|paid|deposits?|withdrawals?|upi|rtgs|neft|imps|money|funds?|amounts?|₹|rs\.?)\b", "FINANCIAL"),
    (r"\b(locations?|visited|visits?|seen at|tower|gps|pings?|where|present)\b", "LOCATION"),
    (r"\b(firs?|complaints?|statements?|witness)\b", "FIR"),
]
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m} | {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
UNITS = {"k": 1_000, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "crore": 10_000_000, "cr": 10_000_000}
NUM = r"(?:₹|rs\.?|inr)?\s?([\d][\d,]*(?:\.\d+)?)\s?(k|thousand|lakhs?|lac|crore|cr)?\b"
STOP = {"show", "find", "list", "all", "the", "a", "an", "of", "in", "on", "at", "to", "from", "by", "with", "and", "or", "for",
        "me", "records", "record", "evidence", "any", "which", "what", "where", "when", "who", "between", "above", "below",
        "over", "under", "more", "less", "than", "this", "that", "person", "case", "during", "after", "before", "night",
        "morning", "evening", "afternoon", "flagged", "suspicious", "unusual", "anomalous", "his", "her", "their", "did", "does"}


def _amount(m) -> float:
    return float(m.group(1).replace(",", "")) * UNITS.get((m.group(2) or "").lower(), 1)


def _year_default() -> int:
    r = db.query_one("SELECT max(ts) t FROM events")
    return r["t"].year if r and r["t"] else datetime.now().year


def parse(q: str) -> dict:
    ql = q.lower()
    f: dict = {"modalities": [], "terms": [], "explain": []}
    for rx, mod in MOD_WORDS:
        if re.search(rx, ql) and mod not in f["modalities"]:
            f["modalities"].append(mod)
    if f["modalities"]:
        f["explain"].append("record type: " + ", ".join(f["modalities"]))
    m = re.search(r"between\s+" + NUM + r"\s+and\s+" + NUM, ql)
    if m:
        lo = float(m.group(1).replace(",", "")) * UNITS.get((m.group(2) or "").lower(), 1)
        hi = float(m.group(3).replace(",", "")) * UNITS.get((m.group(4) or "").lower(), 1)
        f["amount_min"], f["amount_max"] = min(lo, hi), max(lo, hi)
    else:
        m = re.search(r"(?:above|over|more than|greater than|exceeding|at least|>=?)\s*" + NUM, ql)
        if m:
            f["amount_min"] = _amount(m)
        m = re.search(r"(?:below|under|less than|up to|upto|<=?)\s*" + NUM, ql)
        if m:
            f["amount_max"] = _amount(m)
    if "amount_min" in f or "amount_max" in f:
        f["explain"].append(f"amount {'≥ ₹' + format(f['amount_min'], ',.0f') if 'amount_min' in f else ''}"
                            f"{' and ' if 'amount_min' in f and 'amount_max' in f else ''}"
                            f"{'≤ ₹' + format(f['amount_max'], ',.0f') if 'amount_max' in f else ''}")
        if "FINANCIAL" not in f["modalities"]:
            f["modalities"].append("FINANCIAL")
    yr = int(m.group(0)) if (m := re.search(r"\b20\d\d\b", ql)) else _year_default()
    dates = re.findall(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d\d)\b", ql)
    if dates:
        ds = sorted(datetime(int(y), int(mo), int(d)) for d, mo, y in dates)
        f["date_from"], f["date_to"] = ds[0], ds[-1] + timedelta(days=1)
    else:
        mons = [(MONTHS[w], w) for w in re.findall(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b", ql)
                if not (w == "may" and not re.search(r"\bmay\s+20\d\d|\bin may\b|\bof may\b|\bmay\s+\d", ql))]
        if mons:
            first, last = min(x[0] for x in mons), max(x[0] for x in mons)
            day = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:" + "|".join(MONTHS) + r")\b", ql)
            if day and len(mons) == 1:
                f["date_from"] = datetime(yr, first, int(day.group(1)))
                f["date_to"] = f["date_from"] + timedelta(days=1)
            else:
                f["date_from"] = datetime(yr, first, 1)
                f["date_to"] = datetime(yr + (last == 12), last % 12 + 1, 1)
    if "date_from" in f:
        f["explain"].append(f"dates {f['date_from']:%d %b %Y} – {(f['date_to'] - timedelta(days=1)):%d %b %Y}")
    for word, rng in (("night", (22, 5)), ("morning", (5, 12)), ("afternoon", (12, 17)), ("evening", (17, 22))):
        if re.search(rf"\b{word}\b", ql):
            f["hours"] = rng
            f["explain"].append(f"time of day: {word} ({rng[0]:02d}:00–{rng[1]:02d}:00)")
            break
    if re.search(r"\b(flagged|suspicious|unusual|anomal\w*|irregular)\b", ql):
        f["flagged"] = True
        f["explain"].append("flagged records only")
    f["case_ids"] = sorted(set(re.findall(r"\bCASE\d{3}\b", q.upper())))
    f["person_ids"] = sorted(set(re.findall(r"\bP\d{5}\b", q.upper())))
    f["evidence_ids"] = sorted(set(re.findall(r"\bEVD-[A-Z]+\d+\b", q.upper())))
    f["phones"] = sorted({"+91-" + re.sub(r"\D", "", p)[-10:] for p in re.findall(r"(?:\+91[-\s]?)?\b[6-9]\d{9}\b", q)})
    f["accounts"] = sorted(set(re.findall(r"\b[A-Z]{4}-\d{11}\b", q.upper())))
    f["devices"] = sorted(set(re.findall(r"\bIMEI-\d{15}\b", q.upper())))
    # names and places from the data's own gazetteers
    names = {}
    for r in db.query("SELECT person_id, names FROM persons"):
        for n in r["names"] or []:
            if len(n) > 3:
                names.setdefault(n.lower(), set()).add(r["person_id"])
    for n in sorted(names, key=len, reverse=True):
        if re.search(rf"\b{re.escape(n)}\b", ql):
            f["person_ids"] = sorted(set(f["person_ids"]) | names[n])
            f["explain"].append(f"person '{n.title()}' → {', '.join(sorted(names[n]))}")
            ql = re.sub(rf"\b{re.escape(n)}\b", " ", ql)
    places = [r["location_name"] for r in db.query("SELECT DISTINCT location_name FROM events WHERE location_name IS NOT NULL AND location_name <> ''")]
    f["places"] = []
    for pl in places:
        head = pl.split(",")[0].lower()
        if len(head) > 4 and head in ql:
            f["places"].append(pl)
    if f["places"]:
        f["explain"].append("place: " + "; ".join(f["places"][:3]))
    for k, lab in (("case_ids", "case"), ("phones", "phone"), ("accounts", "account"), ("devices", "device"), ("evidence_ids", "evidence")):
        if f[k]:
            f["explain"].append(f"{lab}: {', '.join(f[k])}")
    words = re.findall(r"[a-z][a-z0-9]{2,}", ql)
    f["terms"] = [w for w in words if w not in STOP and not any(re.search(rx, w) for rx, _ in MOD_WORDS) and w not in MONTHS]
    return f


def search(q: str, case_id: str | None = None, person_id: str | None = None, limit: int = 40,
           context_ids: list[str] | None = None) -> dict:
    f = parse(q)
    where, params = ["TRUE"], []
    if f["modalities"]:
        where.append("modality = ANY(%s)"); params.append(f["modalities"])
    if "amount_min" in f:
        where.append("amount >= %s"); params.append(f["amount_min"])
    if "amount_max" in f:
        where.append("amount <= %s"); params.append(f["amount_max"])
    if "date_from" in f:
        where.append("ts >= %s AND ts < %s"); params += [f["date_from"], f["date_to"]]
    if "hours" in f:
        a, b = f["hours"]
        where.append("(extract(hour from ts) >= %s OR extract(hour from ts) < %s)" if a > b else
                     "(extract(hour from ts) >= %s AND extract(hour from ts) < %s)"); params += [a, b]
    explicit_cases = f["case_ids"]
    if explicit_cases:
        where.append("case_id = ANY(%s)"); params.append(explicit_cases)
    pids = f["person_ids"]
    if pids:
        if len(pids) >= 2 and f["modalities"] and set(f["modalities"]) <= {"CDR", "SOCIAL", "FINANCIAL"}:
            where.append("(person_id = ANY(%s) AND entity_id_2 = ANY(%s))"); params += [pids, pids]
            f["explain"].append("between the named persons")
        else:
            where.append("(person_id = ANY(%s) OR entity_id_2 = ANY(%s))"); params += [pids, pids]
    for k, col in (("phones", ["phone_number", "counterpart_phone"]), ("accounts", ["account_number", "counterpart_account"]),
                   ("devices", ["device_id"])):
        if f[k]:
            where.append("(" + " OR ".join(f"{c} = ANY(%s)" for c in col) + ")"); params += [f[k]] * len(col)
    if f["places"]:
        where.append("location_name = ANY(%s)"); params.append(f["places"])
    if f["evidence_ids"]:
        where.append("evidence_id = ANY(%s)"); params.append(f["evidence_ids"])
    flagged = set()
    if f.get("flagged"):
        flagged = set(flagged_ids())
        for b in bursts():
            flagged |= set(b["evidenceIds"])
        for t in travel.detect_all():
            flagged |= {t["first"]["evidenceId"], t["second"]["evidenceId"]}
        where.append("evidence_id = ANY(%s)"); params.append(sorted(flagged))
    terms = " | ".join(f["terms"][:8])
    rank_sql = "ts_rank(tsv, to_tsquery('english', %s))" if terms else "0"
    rank_params = [terms] if terms else []
    sql = (f"SELECT evidence_id, source_record_id, case_id, modality, ts, person_id, entity_id_2, event_description, "
           f"location_name, latitude, longitude, source_reliability, amount, extra, {rank_sql} AS rank FROM events "
           f"WHERE {' AND '.join(where)}"
           + (" AND tsv @@ to_tsquery('english', %s)" if terms and not (len(where) > 1) else "")
           + " ORDER BY rank DESC, ts LIMIT 400")
    rows = db.query(sql, rank_params + params + ([terms] if terms and not (len(where) > 1) else []))
    # semantic matches (messages, FIR text, findings, summaries) from the vector index
    sem = retrieval.search(q, case_id=explicit_cases[0] if explicit_cases else None, person_id=pids[0] if len(pids) == 1 else None, k=12)
    sem_ids = [e for r in sem for e in r["evidence_ids"]]
    if sem_ids and len(where) == 1:
        rows += db.query("SELECT evidence_id, source_record_id, case_id, modality, ts, person_id, entity_id_2, event_description, "
                         "location_name, latitude, longitude, source_reliability, amount, extra, 0 AS rank FROM events "
                         "WHERE evidence_id = ANY(%s)", (sem_ids,))
    ctx_ids = set(context_ids or [])
    scored, seen = [], set()
    for i, r in enumerate(rows):
        if r["evidence_id"] in seen:
            continue
        seen.add(r["evidence_id"])
        s, why = 1.0 / (10 + i), list(f["explain"])
        if r["evidence_id"] in sem_ids:
            s += 0.15; why.append("semantically similar text")
        if terms and r["rank"]:
            s += min(0.3, float(r["rank"])); why.append("keyword match: " + ", ".join(f["terms"][:4]))
        if case_id and r["case_id"] == case_id:
            s += 0.2; why.append(f"in the open case {case_id}")
        if person_id and person_id in (r["person_id"], r["entity_id_2"]):
            s += 0.2; why.append(f"involves the open person {person_id}")
        if ctx_ids & {r["person_id"], r["entity_id_2"], r["case_id"]}:
            s += 0.1; why.append("mentioned earlier in the conversation")
        if r["evidence_id"] in flagged:
            why.append("flagged by KRONOS analytics")
        scored.append((s, r, why))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, r, why in scored[:limit]:
        out.append({"evidenceId": r["evidence_id"], "sourceRecordId": r["source_record_id"], "caseId": r["case_id"],
                    "modality": "COMMUNICATION" if r["modality"] == "SOCIAL" else r["modality"],
                    "timestamp": r["ts"].strftime("%d %b %Y %H:%M") if r["ts"] else "timestamp unavailable",
                    "iso": r["ts"].strftime("%Y-%m-%dT%H:%M") if r["ts"] else None, "description": r["event_description"],
                    "locationName": r["location_name"] or "", "relatedPersonIds": [p for p in (r["person_id"], r["entity_id_2"]) if p],
                    "sourceReliability": r["source_reliability"], "amount": float(r["amount"]) if r["amount"] is not None else None,
                    "score": round(s, 3), "whyMatched": list(dict.fromkeys(why))})
    return {"query": q, "interpretation": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in f.items()
                                           if k not in ("terms",) and v not in ([], None)} | {"keywords": f["terms"]},
            "context": {"caseId": case_id, "personId": person_id}, "total": len(scored), "results": out}
