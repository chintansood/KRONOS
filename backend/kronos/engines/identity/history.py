"""Criminal-history linkage — linking prior records (from a separate records system, no KRONOS IDs)
to current person profiles, and surfacing network-associated cases.

Identity features : name / alias similarity (incl. nicknames), father's name (from FIR "S/o"
                    particulars), phone at the time of the record, address/city consistency.
Contradiction     : a different father's name on both sides (the standard identity triple used in
                    Indian crime records is name + father's name + address).
Policy            : links are candidates — never applied automatically; investigators confirm or reject.
                    Prior records are CONTEXT, NOT EVIDENCE of a current allegation; acquittals and
                    discharges are shown as such, and history is deliberately excluded from the
                    investigative-priority and hypothesis scores to avoid bias.
"""
from __future__ import annotations

from collections import defaultdict

from rapidfuzz import fuzz

from ... import db
from ..graph.analytics import cross_case, person_projection
from ..provenance import ledger
from .resolver import Ctx, _first_variants, _norm, name_similarity

W = {"name": 0.30, "alias": 0.15, "father": 0.30, "phone": 0.30, "address": 0.10}
FATHER_MISMATCH = 0.35


def _city(place: str | None) -> str | None:
    return place.split(",")[-1].strip() if place and "," in place else (place or None)


def _first_compatible(names_a, names_b) -> bool:
    """Same first name or a known nickname variant (e.g. Ram/Raju). Same father + address with a different first
    name is what a sibling looks like, so it must not produce a strong link."""
    for x in names_a:
        for y in names_b:
            tx, ty = _norm(x), _norm(y)
            if tx and ty and (_first_variants(tx[0]) & _first_variants(ty[0]) or fuzz.ratio(tx[0], ty[0]) >= 88):
                return True
    return False


def _band(score: float, f: dict) -> str:
    if not f.get("firstName", 1.0):
        return "LOW" if score >= 0.35 else "INSUFFICIENT_EVIDENCE"
    if score >= 0.75 and (f["father"] or f["phone"]) and f["name"] >= 0.8:
        return "HIGH"
    if score >= 0.55:
        return "MEDIUM"
    if score >= 0.35:
        return "LOW"
    return "INSUFFICIENT_EVIDENCE"


def link_all() -> dict:
    ctx = Ctx()
    hist = db.query("SELECT * FROM criminal_history WHERE coalesce(source_system, '') <> 'COURT_ORDER'")   # court-stated links are fixed
    night_place = {}
    for pid, c in ctx.places.items():
        night_place[pid] = c.most_common(1)[0][0] if c else None
    persons = ctx.persons
    rows = []
    for h in hist:
        hnames = [h["full_name"]] + list(h["alias_names"] or [])
        hcity = _city(h["address"])
        for pid, p in persons.items():
            pnames = p["names"] or [p["display_name"]]
            phone = bool(h["phone_at_record"] and h["phone_at_record"] in (p["phones"] or []))
            best, why = max((name_similarity(x, y) for x in hnames for y in pnames), key=lambda t: t[0])
            if best < 0.6 and not phone:
                continue
            f = {"name": round(best, 3), "alias": 0.0, "father": 0.0, "phone": 1.0 if phone else 0.0, "address": 0.0,
                 "firstName": 1.0 if _first_compatible(hnames, pnames) else 0.0}
            reasons, contra = [why], []
            if not f["firstName"]:
                contra.append("different first name — shared surname/father/address may indicate a relative, not the same person")
            for al in h["alias_names"] or []:
                if any(fuzz.ratio(al, y) >= 92 for y in pnames):
                    f["alias"] = 1.0
                    reasons.append(f"prior record lists alias '{al}', matching this profile's name")
            fathers = ctx.father.get(pid, set())
            mismatch = 0.0
            if h["father_name"] and fathers:
                if max(fuzz.token_set_ratio(h["father_name"], x) for x in fathers) >= 90:
                    f["father"] = 1.0
                    reasons.append(f"same father's name ({h['father_name']}) in prior record and FIR particulars")
                else:
                    mismatch = FATHER_MISMATCH
                    contra.append(f"father's name differs: prior record '{h['father_name']}' vs FIR '{sorted(fathers)[0]}'")
            elif h["father_name"]:
                reasons.append("father's name not recorded for this profile — cannot be compared")
            if phone:
                reasons.append(f"phone at time of record ({h['phone_at_record']}) is used by this profile")
            stated = ctx.address.get(pid, set())
            if h["address"] and (h["address"] in stated or h["address"] == night_place.get(pid)):
                f["address"] = 1.0
                reasons.append(f"same address ({h['address']})")
            elif hcity and (hcity in {_city(a) for a in stated} or hcity == _city(night_place.get(pid))):
                f["address"] = 0.5
                reasons.append(f"same city ({hcity})")
            elif hcity and night_place.get(pid):
                contra.append(f"prior record address in {hcity}; profile's night-time area is in {_city(night_place[pid])}")
            score = max(0.0, min(1.0, sum(W[k] * f[k] for k in W) - mismatch))
            band = _band(score, f)
            if band == "INSUFFICIENT_EVIDENCE" and best < 0.9:
                continue
            rows.append((f"HL-{h['history_id']}-{pid}", h["history_id"], pid, round(score, 3), band,
                         db.Json(f), db.Json(reasons), db.Json(contra)))
    existing = {r["link_id"]: r["status"] for r in db.query("SELECT link_id, status FROM history_links")}
    db.execute("DELETE FROM history_links WHERE status='PENDING'")
    db.execute_values("INSERT INTO history_links (link_id, history_id, person_id, score, band, features, reasons, contradicting, status) "
                      "VALUES %s ON CONFLICT (link_id) DO UPDATE SET score=EXCLUDED.score, band=EXCLUDED.band, "
                      "features=EXCLUDED.features, reasons=EXCLUDED.reasons, contradicting=EXCLUDED.contradicting, updated_at=now()",
                      [r + (existing.get(r[0], "PENDING"),) for r in rows])
    return {"historyRecords": len(hist), "candidateLinks": len(rows)}


def _record(h: dict) -> dict:
    return {"historyId": h["history_id"], "evidenceId": h["evidence_id"], "recordType": h["record_type"],
            "sourceSystem": h["source_system"], "name": h["full_name"], "aliases": h["alias_names"], "father": h["father_name"],
            "address": h["address"], "offence": h["offence_category"], "sections": h["sections"], "firReference": h["fir_reference"],
            "policeStation": h["police_station"], "date": h["record_date"].isoformat() if h["record_date"] else None,
            "disposition": h["disposition"], "modusOperandi": h["modus_operandi"], "reliability": h["source_reliability"]}


def _links(person_id: str, min_band=("HIGH", "MEDIUM", "LOW")) -> list[dict]:
    out = []
    for r in db.query("SELECT l.*, h.* FROM history_links l JOIN criminal_history h USING (history_id) "
                      "WHERE l.person_id=%s AND l.band = ANY(%s) AND l.status <> 'REJECTED' ORDER BY l.score DESC",
                      (person_id, list(min_band))):
        out.append({"linkId": r["link_id"], "personId": r["person_id"], "score": r["score"], "band": r["band"],
                    "status": r["status"], "features": r["features"], "reasons": r["reasons"], "contradicting": r["contradicting"],
                    "record": _record(r)})
    return out


def person_history(person_id: str) -> dict:
    direct = _links(person_id)
    via = []
    for c in db.query("SELECT person_a, person_b, band, score, status FROM identity_candidates WHERE (person_a=%s OR person_b=%s) "
                      "AND band IN ('HIGH','MEDIUM') AND status <> 'REJECTED'", (person_id, person_id)):
        other = c["person_b"] if c["person_a"] == person_id else c["person_a"]
        for l in _links(other, ("HIGH", "MEDIUM")):
            via.append({**l, "viaPersonId": other, "identityBand": c["band"], "identityScore": c["score"],
                        "identityStatus": c["status"]})
    # network-associated cases: cases of this person's strongest associates and cases sharing identifiers
    own = {r["case_id"] for r in db.query("SELECT DISTINCT case_id FROM person_case_roles WHERE person_id=%s", (person_id,))}
    roles = defaultdict(set)
    for r in db.query("SELECT person_id, case_id FROM person_case_roles WHERE role <> 'RECORD_SUBJECT'"):
        roles[r["person_id"]].add(r["case_id"])
    P = person_projection()
    assoc = {}
    if person_id in P:
        for nb in sorted(P[person_id], key=lambda n: -P[person_id][n]["weight"])[:10]:
            for cid in roles.get(nb, set()) - own:
                a = assoc.setdefault(cid, {"caseId": cid, "via": [], "strength": 0.0})
                a["via"].append({"personId": nb, "basis": P[person_id][nb]["basis"][:3]})
                a["strength"] += P[person_id][nb]["weight"]
    for link in cross_case():
        x, y = link["cases"]
        for mine, other in ((x, y), (y, x)):
            if mine in own and other not in own:
                a = assoc.setdefault(other, {"caseId": other, "via": [], "strength": 0.0})
                a["via"].append({"case": mine, "basis": [f"{v['type']} {v['id']}" for v in link["links"][:3]]})
                a["strength"] += link["strength"]
    return {"personId": person_id, "priorRecords": direct, "priorRecordsViaPossibleIdentity": via,
            "associatedCases": sorted(assoc.values(), key=lambda a: -a["strength"])[:12],
            "note": "Prior records are context, not evidence of the current allegation. Acquittals/discharges mean no "
                    "finding of guilt. Links are candidates until confirmed; history is excluded from priority scoring."}


def review(link_id: str, decision: str, reviewer: str = "investigator", note: str = "") -> dict:
    decision = decision.upper()
    if decision not in ("CONFIRMED", "REJECTED", "DEFERRED", "PENDING"):
        raise ValueError("decision must be CONFIRMED, REJECTED, DEFERRED or PENDING")
    cur = db.query_one("SELECT * FROM history_links WHERE link_id=%s", (link_id,))
    if not cur:
        raise KeyError(link_id)
    db.execute("INSERT INTO history_reviews (link_id, decision, reviewer, note, previous_status) VALUES (%s,%s,%s,%s,%s)",
               (link_id, decision, reviewer, note, cur["status"]))
    db.execute("UPDATE history_links SET status=%s, updated_at=now() WHERE link_id=%s", (decision, link_id))
    ledger.append("HISTORY_LINK_REVIEW", None, None, reviewer, {"linkId": link_id, "decision": decision,
                                                                "previous": cur["status"], "note": note})
    return {"linkId": link_id, "status": decision}


def evaluate(gt: dict) -> dict:
    p2h = gt["person_to_human"]
    truth = {h["history_id"]: h for h in gt.get("history", [])}
    links = db.query("SELECT history_id, person_id, band FROM history_links")
    strong = [l for l in links if l["band"] in ("HIGH", "MEDIUM")]
    correct = [l for l in strong if truth.get(l["history_id"], {}).get("human") == p2h.get(l["person_id"])]
    linked_ok = {l["history_id"] for l in correct}
    true_present = {hid for hid, h in truth.items() if h["human"]}
    wrong = [l for l in strong if l not in correct]
    by_kind = defaultdict(lambda: {"records": 0, "linkedHighMedium": 0, "wrongLinks": 0})
    for hid, h in truth.items():
        k = by_kind[h["kind"]]; k["records"] += 1
        k["linkedHighMedium"] += hid in linked_ok
        k["wrongLinks"] += sum(1 for l in wrong if l["history_id"] == hid)
    return {"highOrMediumLinks": len(strong), "correct": len(correct),
            "precision": round(len(correct) / len(strong), 3) if strong else None,
            "recall": round(len(linked_ok & true_present) / len(true_present), 3) if true_present else None,
            "byKind": dict(by_kind)}
