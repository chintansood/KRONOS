"""Integrated fuzzy identity resolution.

Question: could two person records (e.g. 'Ram Kumar' in CASE001 and 'Raju' in CASE014, or a
person who later reappears under a new name with a new phone, SIM, handset and account) refer
to the same human being?

Evidence contributed by each engine
  Multimodal : name / nickname similarity, aliases recorded in FIR text ("X @ Y"), father's name and
               stated address from FIR particulars ("S/o", "R/o"), shared phone / handset / SIM / account
  Temporal   : BEHAVIOURAL PATTERNS — routine-place profile, night-time area, hour-of-day rhythm,
               activity hand-off (one identity goes quiet as the other appears) — and contradictions
               (both records active far apart at the same moment = physically two people)
  Graph      : social-circle continuity (the same regular contacts), neighbourhood overlap
Contradictions: direct communication between the two records, simultaneous presence in distant places,
same name without any shared identifier, different father's names.

Policy: a behavioural match without any shared identifier can reach at most MEDIUM ("requires
verification"); HIGH requires a hard identifier or a recorded alias. Strong contradictions block
behavioural matches. Records are NEVER merged automatically — investigators confirm / reject / defer,
and every decision is audited and written to the ledger.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from itertools import combinations

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from ... import db
from ...config import settings
from ...synth.world import NICKNAMES
from ..graph.analytics import person_projection
from ..provenance import ledger
from ..store import events
from ..temporal.travel import haversine_km

ID_W = {"alias_recorded": 0.30, "phone": 0.32, "device": 0.22, "sim": 0.30, "account": 0.28, "father": 0.20, "address": 0.08}
NAME_W = 0.15
BEH_W = {"contacts": 0.45, "places": 0.10, "home": 0.05, "rhythm": 0.05, "handoff": 0.35}
PENALTY_STRONG = {"direct_contact": 0.40, "simultaneous": 0.45}
PENALTY_SOFT = {"namesake_no_ids": 0.10, "father_mismatch": 0.12}
HARD = ("phone", "device", "sim", "account", "alias_recorded", "father")


def _norm(name: str) -> list[str]:
    return re.sub(r"[^a-z ]", "", (name or "").lower()).split()


def _first_variants(tok: str) -> set:
    v = {tok}
    v |= set(NICKNAMES.get(tok, []))
    for canon, nicks in NICKNAMES.items():
        if tok in nicks:
            v.add(canon); v |= set(nicks)
    return v


def name_similarity(a: str, b: str) -> tuple[float, str]:
    ta, tb = _norm(a), _norm(b)
    if not ta or not tb:
        return 0.0, "no name"
    base = fuzz.token_set_ratio(" ".join(ta), " ".join(tb)) / 100
    nick = bool(_first_variants(ta[0]) & _first_variants(tb[0]))
    sur_a, sur_b = ta[-1] if len(ta) > 1 else None, tb[-1] if len(tb) > 1 else None
    if nick and (sur_a == sur_b or sur_a is None or sur_b is None):
        return max(base, 0.85), f"'{a}' / '{b}': known nickname/short form" + ("" if sur_a == sur_b else " (one surname missing)")
    if nick:
        return max(base, 0.6), f"'{a}' / '{b}': first names are nickname variants, surnames differ"
    return base, f"'{a}' / '{b}': string similarity {base:.2f}"


def _cos(u: np.ndarray, v: np.ndarray) -> float:
    return float(u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9))


class Ctx:
    """Per-person profiles used by all engines' identity features."""

    def __init__(self):
        df = events()
        # pseudonymised people from real court records are never fuzzy-matched with anyone
        self.persons = {p["person_id"]: p for p in db.query("SELECT * FROM persons WHERE coalesce(origin, 'SYNTHETIC') <> 'PUBLIC_RECORD'")}
        loc = df[(df.modality == "LOCATION") & df.latitude.notna() & df.ts.notna() & df.person_id.notna()]
        night = loc[(loc.ts.dt.hour >= 22) | (loc.ts.dt.hour < 6)]
        self.home = {pid: (g.latitude.median(), g.longitude.median()) for pid, g in night.groupby("person_id") if len(g) >= 3}
        self.places = {pid: Counter(g.location_name.dropna()) for pid, g in loc.groupby("person_id") if len(g) >= 5}
        self.place_index = sorted({pl for c in self.places.values() for pl in c})
        act = df[df.person_id.notna() & df.ts.notna() & (df.modality != "FIR")]
        self.rhythm = {pid: np.bincount(g.ts.dt.hour, minlength=24).astype(float) for pid, g in act.groupby("person_id")}
        self.span = {pid: (g.ts.min(), g.ts.max()) for pid, g in act.groupby("person_id") if len(g) >= 5}
        comm = df[df.modality.isin(["CDR", "SOCIAL"]) & df.entity_id_2.notna() & df.person_id.notna()]
        self.contacts = defaultdict(Counter)
        self.direct = defaultdict(list)
        for a, b, e in zip(comm.person_id, comm.entity_id_2, comm.evidence_id):
            self.contacts[a][b] += 1; self.contacts[b][a] += 1
            self.direct[frozenset((a, b))].append(e)
        geo = df[df.latitude.notna() & df.ts.notna() & df.person_id.notna() & df.modality.isin(["LOCATION", "CDR", "SOCIAL"])]
        self.geo_by = {pid: g[["ts", "latitude", "longitude", "accuracy_m", "evidence_id"]].sort_values("ts")
                       for pid, g in geo.groupby("person_id")}
        self.aliases = defaultdict(list)
        for r in db.query("""SELECT a.source_record_id, a.evidence_id, a.entity_text alias_text, a.linked_person_id alias_pid,
                                    (SELECT p.linked_person_id FROM text_entities p WHERE p.source_record_id=a.source_record_id
                                      AND p.entity_type='PERSON' AND p.span_end <= a.span_start AND p.linked_person_id IS NOT NULL
                                      ORDER BY p.span_end DESC LIMIT 1) main_pid
                             FROM text_entities a WHERE a.entity_type='ALIAS'"""):
            if r["main_pid"]:
                self.aliases[r["main_pid"]].append(r)
        self.father, self.address = defaultdict(set), defaultdict(set)
        self.attr_ev = defaultdict(list)
        for r in db.query("SELECT linked_person_id, entity_type, normalized, evidence_id FROM text_entities "
                          "WHERE entity_type IN ('FATHER_NAME','ADDRESS') AND linked_person_id IS NOT NULL"):
            (self.father if r["entity_type"] == "FATHER_NAME" else self.address)[r["linked_person_id"]].add(r["normalized"])
            self.attr_ev[r["linked_person_id"]].append(r["evidence_id"])
        # inverse "document frequency" of each contact: a contact shared by many people says little about identity
        df_c = Counter(k for c in self.contacts.values() for k in c)
        n = max(1, len(self.contacts))
        self.idf = {k: math.log(n / (1 + v)) + 0.1 for k, v in df_c.items()}
        self.graph = person_projection()

    def regular_contacts(self, pid, exclude=()) -> set:
        c = self.contacts.get(pid, Counter())
        return {k for k, n in c.items() if n >= 2 and k not in exclude}

    def contact_profile(self, pid, exclude=None) -> dict:
        """Who a record talks to and how often, weighted by contact rarity (IDF)."""
        return {k: n * self.idf.get(k, 0.1) for k, n in self.contacts.get(pid, Counter()).items() if k != exclude}

    def place_vec(self, pid):
        c = self.places.get(pid)
        if not c:
            return None
        return np.array([c.get(pl, 0) for pl in self.place_index], dtype=float)


def _simultaneous(ga: pd.DataFrame, gb: pd.DataFrame, window_min=20) -> list[dict]:
    """Records of A and B close in time but too far apart for one person to be at both."""
    if ga is None or gb is None:
        return []
    out = []
    tb = gb.ts.values
    for r in ga.itertuples():
        lo = np.searchsorted(tb, np.datetime64(r.ts - pd.Timedelta(minutes=window_min)))
        hi = np.searchsorted(tb, np.datetime64(r.ts + pd.Timedelta(minutes=window_min)))
        for s in gb.iloc[lo:hi].itertuples():
            d = haversine_km(r.latitude, r.longitude, s.latitude, s.longitude)
            unc = ((r.accuracy_m or 1500) + (s.accuracy_m or 1500)) / 1000
            hours = max(abs((r.ts - s.ts).total_seconds()) / 3600, 1 / 60)
            if d - unc > 3 and (d - unc) / hours > settings.travel_max_ground_kmh:
                out.append({"a": r.evidence_id, "b": s.evidence_id, "km": round(d, 1),
                            "minutesApart": round(abs((r.ts - s.ts).total_seconds()) / 60)})
                if len(out) >= 5:
                    return out
    return out


def behaviour(a: str, b: str, ctx: Ctx) -> tuple[float, dict, list[str]]:
    """Behavioural similarity in [0,1] with explanations (social circle, routine places, night-time area,
    daily rhythm, activity hand-off). Uses no identifiers and no names."""
    f, why = {}, []
    ca, cb = ctx.regular_contacts(a, {b}), ctx.regular_contacts(b, {a})
    shared = ca & cb
    f["sharedContacts"] = len(shared)
    pa, pb = ctx.contact_profile(a, b), ctx.contact_profile(b, a)
    keys = sorted(set(pa) | set(pb))
    f["contacts"] = round(_cos(np.array([pa.get(k, 0.0) for k in keys]), np.array([pb.get(k, 0.0) for k in keys])), 3) if keys else 0.0
    if shared:
        why.append(f"social-circle continuity: {len(shared)} regular contacts in common ({', '.join(sorted(shared)[:4])}); "
                   f"rarity-weighted contact-profile similarity {f['contacts']:.2f}")
    va, vb = ctx.place_vec(a), ctx.place_vec(b)
    f["places"] = round(_cos(va, vb), 3) if va is not None and vb is not None else 0.0
    if f["places"] >= 0.6:
        top = [pl for pl, _ in (ctx.places[a] & ctx.places[b]).most_common(3)]
        why.append(f"same routine places (similarity {f['places']:.2f}): {', '.join(top)}")
    if a in ctx.home and b in ctx.home:
        d = haversine_km(*ctx.home[a], *ctx.home[b])
        f["home"] = 1.0 if d < 1 else 0.5 if d < 5 else 0.0
        if f["home"]:
            why.append(f"night-time locations {d:.1f} km apart")
    else:
        f["home"] = 0.0
    f["rhythm"] = round(_cos(ctx.rhythm[a], ctx.rhythm[b]), 3) if a in ctx.rhythm and b in ctx.rhythm else 0.0
    f["handoff"] = 0.0
    if a in ctx.span and b in ctx.span:
        (fa, la), (fb, lb) = ctx.span[a], ctx.span[b]
        overlap = (min(la, lb) - max(fa, fb)).total_seconds() / 86400
        shorter = max(1.0, min((la - fa).total_seconds(), (lb - fb).total_seconds()) / 86400)
        if overlap <= 2:
            gap = -overlap
            f["handoff"] = 1.0 if gap <= 120 else 0.5
            first, second = (a, b) if fa <= fb else (b, a)
            why.append(f"activity hand-off: {first}'s records end {ctx.span[first][1]:%d %b %Y}, "
                       f"{second}'s begin {ctx.span[second][0]:%d %b %Y} ({max(0, gap):.0f}-day gap, no overlap)")
        elif overlap <= 0.1 * shorter:
            f["handoff"] = 0.4
    bh = sum(BEH_W[k] * f[k] for k in BEH_W)
    return round(bh, 3), f, why


def _band(score: float, hard: bool, beh: dict, strong_pen: float) -> str:
    if hard:
        if score >= settings.identity_high:
            return "HIGH"
        if score >= settings.identity_medium:
            return "MEDIUM"
        return "LOW" if score >= settings.identity_low else "INSUFFICIENT_EVIDENCE"
    # behaviour-only: never HIGH. MEDIUM needs a strongly similar social circle (≥3 shared regular contacts,
    # rarity-weighted profile similarity ≥0.6), a consistent routine, an identity hand-off in time and no strong
    # contradiction.
    # (a person who switches name and phone normally keeps the same home/work routine, so routine-place
    # consistency is required too; without it the behavioural evidence is weaker and stays LOW)
    if strong_pen == 0 and beh["contacts"] >= 0.6 and beh["sharedContacts"] >= 3 and beh["handoff"] >= 0.5 \
            and beh["places"] >= 0.6 and score >= 0.6:
        return "MEDIUM"
    if strong_pen < 0.3 and beh["contacts"] >= 0.45 and beh["sharedContacts"] >= 2 and score >= 0.45:
        return "LOW"
    return "INSUFFICIENT_EVIDENCE"


def score_pair(a: str, b: str, ctx: Ctx) -> dict:
    A, B = ctx.persons[a], ctx.persons[b]
    feats, reasons, support, contra = {}, [], [], []
    ns, why = max((name_similarity(x, y) for x in (A["names"] or [A["display_name"]]) for y in (B["names"] or [B["display_name"]])),
                  key=lambda t: t[0])
    feats["name"] = round(ns, 3); reasons.append(why)
    al = [r for r in ctx.aliases.get(a, []) if r["alias_pid"] == b or fuzz.ratio(r["alias_text"], B["display_name"]) > 90] + \
         [r for r in ctx.aliases.get(b, []) if r["alias_pid"] == a or fuzz.ratio(r["alias_text"], A["display_name"]) > 90]
    feats["alias_recorded"] = 1.0 if al else 0.0
    if al:
        reasons.append(f"FIR text records an alias ('{al[0]['alias_text']}') for this person")
        support += [{"evidenceId": r["evidence_id"], "why": f"alias '{r['alias_text']}' recorded in FIR"} for r in al[:3]]
    for key, col in (("phone", "phones"), ("device", "devices"), ("sim", "sims"), ("account", "accounts")):
        shared = sorted(set(A[col] or []) & set(B[col] or []))
        feats[key] = 1.0 if shared else 0.0
        if shared:
            reasons.append(f"shared {key}: {', '.join(shared[:3])}")
            ev = db.query("SELECT evidence_id, person_id FROM events WHERE person_id IN (%s,%s) AND "
                          "(phone_number = ANY(%s) OR device_id = ANY(%s) OR sim_id = ANY(%s) OR account_number = ANY(%s)) "
                          "ORDER BY ts LIMIT 6", (a, b, shared, shared, shared, shared))
            support += [{"evidenceId": e["evidence_id"], "why": f"{e['person_id']} record uses shared {key}"} for e in ev]
    fa_, fb_ = ctx.father.get(a, set()), ctx.father.get(b, set())
    soft_pen = 0.0
    feats["father"] = 0.0
    if fa_ and fb_:
        best = max(fuzz.token_set_ratio(x, y) for x in fa_ for y in fb_)
        if best >= 90:
            feats["father"] = 1.0
            reasons.append(f"same father's name recorded in FIR particulars ({sorted(fa_)[0]})")
            support += [{"evidenceId": e, "why": "father's name in FIR particulars"} for e in (ctx.attr_ev[a][:1] + ctx.attr_ev[b][:1])]
        else:
            soft_pen += PENALTY_SOFT["father_mismatch"]
            contra.append({"evidenceId": (ctx.attr_ev[a] or [None])[0],
                           "why": f"different father's names recorded ({sorted(fa_)[0]} / {sorted(fb_)[0]}) — "
                                  "could also be a false name given to police"})
    aa, ab = ctx.address.get(a, set()), ctx.address.get(b, set())
    feats["address"] = 1.0 if aa and ab and aa & ab else 0.0
    if feats["address"]:
        reasons.append(f"same stated residence in FIR particulars ({sorted(aa & ab)[0]})")
    bh, bfeats, bwhy = behaviour(a, b, ctx)
    feats.update({f"beh_{k}": v for k, v in bfeats.items()}); feats["behaviour"] = bh
    reasons += bwhy
    P = ctx.graph
    na = set(P[a]) - {b} if a in P else set(); nb = set(P[b]) - {a} if b in P else set()
    feats["graph"] = round(len(na & nb) / len(na | nb), 3) if na | nb else 0.0
    strong = 0.0
    dc = ctx.direct.get(frozenset((a, b)), [])
    if dc:
        strong += PENALTY_STRONG["direct_contact"]
        contra += [{"evidenceId": e, "why": "the two records communicate with each other"} for e in dc[:4]]
        reasons.append(f"CONTRADICTION: {len(dc)} direct communication(s) between the two records")
    sim = _simultaneous(ctx.geo_by.get(a), ctx.geo_by.get(b))
    if sim:
        strong += PENALTY_STRONG["simultaneous"]
        contra += [{"evidenceId": f"{x['a']}+{x['b']}", "why": f"active {x['km']} km apart, {x['minutesApart']} min apart"} for x in sim[:3]]
        reasons.append("CONTRADICTION: both records active in distant places at nearly the same time")
    hard = any(feats[k] for k in HARD)
    if feats["name"] >= 0.9 and not hard:
        soft_pen += PENALTY_SOFT["namesake_no_ids"]
        reasons.append("same/similar name but no shared identifiers — may be different people with the same name")
    id_score = sum(ID_W[k] * feats[k] for k in ID_W) + NAME_W * feats["name"] + 0.3 * bh
    beh_score = 0.8 * bh + 0.1 * feats["name"]
    raw = max(id_score, beh_score)
    pen = strong + soft_pen
    score = max(0.0, min(1.0, raw - pen))
    band = _band(score, hard, bfeats, strong)
    contributions = {**{k: round(ID_W[k] * feats[k], 3) for k in ID_W}, "name": round(NAME_W * feats["name"], 3),
                     **{f"behaviour_{k}": round(BEH_W[k] * bfeats[k], 3) for k in BEH_W}}
    basis = "identifier" if hard else "behavioural"
    if not hard and band in ("MEDIUM", "LOW"):
        reasons.insert(0, "BEHAVIOURAL MATCH — no shared identifier; requires verification (e.g. CAF/KYC, fingerprints)")
    return {"candidateId": f"IDC-{a}-{b}", "personA": a, "personB": b, "nameA": A["display_name"], "nameB": B["display_name"],
            "score": round(score, 3), "band": band, "basis": basis, "features": feats, "contributions": contributions,
            "penalty": round(pen, 3), "reasons": reasons, "supporting": support[:10], "contradicting": contra[:10]}


def generate_candidates() -> list[dict]:
    ctx = Ctx()
    persons = ctx.persons
    pairs = set()
    ids = sorted(persons)
    # blocking 1: name / nickname similarity
    first = {p: _norm(persons[p]["display_name"])[:1] for p in ids}
    for a, b in combinations(ids, 2):
        na, nb = persons[a]["display_name"], persons[b]["display_name"]
        if fuzz.token_set_ratio(na, nb) >= 85 or (first[a] and first[b] and _first_variants(first[a][0]) & _first_variants(first[b][0])
                                                  and (len(_norm(na)) == 1 or len(_norm(nb)) == 1 or _norm(na)[-1] == _norm(nb)[-1])):
            pairs.add((a, b))
    # blocking 2: shared identifiers
    for col in ("phones", "devices", "sims", "accounts"):
        users = defaultdict(set)
        for p in ids:
            for v in persons[p][col] or []:
                users[v].add(p)
        for v, ps in users.items():
            if 1 < len(ps) <= 5:
                pairs |= set(combinations(sorted(ps), 2))
    # blocking 3: recorded aliases
    for main, rows in ctx.aliases.items():
        for r in rows:
            if r["alias_pid"] and r["alias_pid"] != main:
                pairs.add(tuple(sorted((main, r["alias_pid"]))))
    # blocking 4: behaviour — social-circle continuity between subjects (finds identity switches with no shared identifier)
    subjects = [p for p in ids if persons[p]["is_subject"] and len(ctx.regular_contacts(p)) >= 2]
    regular = {p: ctx.regular_contacts(p) for p in subjects}
    for a, b in combinations(subjects, 2):
        ca, cb = regular[a] - {b}, regular[b] - {a}
        if len(ca) >= 2 and len(cb) >= 2 and len(ca & cb) / min(len(ca), len(cb)) >= 0.4:
            pairs.add((a, b))
    # blocking 5: same father's name recorded in FIR particulars
    by_father = defaultdict(set)
    for p, fs in ctx.father.items():
        for f in fs:
            by_father[f.lower()].add(p)
    for f, ps in by_father.items():
        if 1 < len(ps) <= 5:
            pairs |= set(combinations(sorted(ps), 2))
    out = [score_pair(a, b, ctx) for a, b in sorted(pairs)]
    out = [c for c in out if c["score"] > 0.05 or c["features"]["name"] >= 0.85 or any(c["features"][k] for k in HARD)
           or c["band"] != "INSUFFICIENT_EVIDENCE"]
    existing = {r["candidate_id"]: r["status"] for r in db.query("SELECT candidate_id, status FROM identity_candidates")}
    db.execute("DELETE FROM identity_candidates WHERE status='PENDING'")
    db.execute_values("INSERT INTO identity_candidates (candidate_id, person_a, person_b, score, band, features, supporting, "
                      "contradicting, reasons, status) VALUES %s ON CONFLICT (candidate_id) DO UPDATE SET score=EXCLUDED.score, "
                      "band=EXCLUDED.band, features=EXCLUDED.features, supporting=EXCLUDED.supporting, "
                      "contradicting=EXCLUDED.contradicting, reasons=EXCLUDED.reasons, updated_at=now()",
                      [(c["candidateId"], c["personA"], c["personB"], c["score"], c["band"],
                        db.Json({"features": c["features"], "contributions": c["contributions"], "penalty": c["penalty"],
                                 "basis": c["basis"]}),
                        db.Json(c["supporting"]), db.Json(c["contradicting"]), db.Json(c["reasons"]),
                        existing.get(c["candidateId"], "PENDING")) for c in out])
    return out


def _row(r) -> dict:
    names = {p["person_id"]: p["display_name"] for p in db.query("SELECT person_id, display_name FROM persons WHERE person_id IN (%s,%s)",
                                                                  (r["person_a"], r["person_b"]))}
    return {"candidateId": r["candidate_id"], "personA": r["person_a"], "personB": r["person_b"],
            "nameA": names.get(r["person_a"]), "nameB": names.get(r["person_b"]), "score": r["score"], "band": r["band"],
            **r["features"], "reasons": r["reasons"], "supporting": r["supporting"], "contradicting": r["contradicting"],
            "status": r["status"], "updatedAt": r["updated_at"].isoformat(),
            "history": [{"decision": h["decision"], "reviewer": h["reviewer"], "note": h["note"],
                         "at": h["reviewed_at"].isoformat()} for h in
                        db.query("SELECT * FROM identity_reviews WHERE candidate_id=%s ORDER BY reviewed_at", (r["candidate_id"],))],
            "note": "Candidate only. Records are never merged automatically; original identities are preserved."}


def list_candidates(person_id=None, band=None, status=None, limit=100) -> list[dict]:
    q, p = "SELECT * FROM identity_candidates WHERE TRUE", []
    if person_id:
        q += " AND (person_a=%s OR person_b=%s)"; p += [person_id, person_id]
    if band:
        q += " AND band=%s"; p.append(band)
    else:
        q += " AND band <> 'INSUFFICIENT_EVIDENCE'" if not person_id else ""
    if status:
        q += " AND status=%s"; p.append(status)
    q += " ORDER BY score DESC LIMIT %s"; p.append(limit)
    return [_row(r) for r in db.query(q, p)]


def review(candidate_id: str, decision: str, reviewer: str = "investigator", note: str = "") -> dict:
    decision = decision.upper()
    if decision not in ("CONFIRMED", "REJECTED", "DEFERRED", "PENDING"):
        raise ValueError("decision must be CONFIRMED, REJECTED, DEFERRED or PENDING")
    cur = db.query_one("SELECT * FROM identity_candidates WHERE candidate_id=%s", (candidate_id,))
    if not cur:
        raise KeyError(candidate_id)
    db.execute("INSERT INTO identity_reviews (candidate_id, decision, reviewer, note, previous_status) VALUES (%s,%s,%s,%s,%s)",
               (candidate_id, decision, reviewer, note, cur["status"]))
    db.execute("UPDATE identity_candidates SET status=%s, updated_at=now() WHERE candidate_id=%s", (decision, candidate_id))
    ledger.append("IDENTITY_REVIEW", None, None, reviewer, {"candidateId": candidate_id, "decision": decision,
                                                            "previous": cur["status"], "note": note})
    return _row(db.query_one("SELECT * FROM identity_candidates WHERE candidate_id=%s", (candidate_id,)))


def evaluate(gt: dict) -> dict:
    p2h = gt["person_to_human"]
    cands = {(r["person_a"], r["person_b"]): r for r in db.query("SELECT * FROM identity_candidates")}
    same = {tuple(sorted(a["person_ids"])) for a in gt["alias_pairs"] + gt.get("burner_pairs", [])}
    res = {"aliasPairs": len(same), "bands": {}}
    for pair in same:
        b = cands.get(pair, {}).get("band", "NOT_GENERATED")
        res["bands"][b] = res["bands"].get(b, 0) + 1
    hi = [k for k, v in cands.items() if v["band"] in ("HIGH", "MEDIUM")]
    tp = sum(1 for a, b in hi if p2h.get(a) == p2h.get(b))
    res["highOrMedium"] = len(hi); res["highOrMediumCorrect"] = tp
    res["precisionHighMedium"] = round(tp / len(hi), 3) if hi else None
    res["recallHighMedium"] = round(sum(1 for p in same if p in hi) / len(same), 3) if same else None
    ns = [tuple(sorted(n["person_ids"])) for n in gt["namesakes"]]
    res["namesakes"] = {str(p): cands.get(p, {}).get("band", "NOT_GENERATED") for p in ns}
    sd = [tuple(sorted(s["person_ids"])) for s in gt["shared_devices"]]
    res["householdsSharingHandsetAndHome"] = {str(p): cands.get(p, {}).get("band", "NOT_GENERATED") for p in sd}
    bp = [tuple(sorted(b["person_ids"])) for b in gt.get("burner_pairs", [])]
    res["burnerPairsNoSharedIdentifier"] = {str(p): cands.get(p, {}).get("band", "NOT_GENERATED") for p in bp}
    beh = [k for k, v in cands.items() if v["band"] in ("HIGH", "MEDIUM") and (v["features"] or {}).get("basis") == "behavioural"]
    res["behaviouralMatches"] = {"highOrMedium": len(beh), "correct": sum(1 for a, b in beh if p2h.get(a) == p2h.get(b))}
    return res
