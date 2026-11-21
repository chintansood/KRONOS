"""Named-entity recognition for FIR narratives and chat messages.

Approach: deterministic patterns (phones, accounts, amounts, dates, vehicles) + gazetteers
built from the ingested records themselves (person names seen in CDR/financial/social
subscriber fields, place names, organisation names). Person roles are assigned from the
wording of the sentence that mentions them (complainant / accused / witness / victim /
associate / mentioned). Every entity keeps its character span so it can be shown in the
original text. Mention in an FIR never implies suspicion by itself.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz

PHONE = re.compile(r"\+91-?\d{10}")
ACCOUNT = re.compile(r"\b[A-Z]{4}-\d{11}\b")
AMOUNT = re.compile(r"(?:Rs\.?|₹)\s?[\d,]+(?:\.\d+)?")
DATETIME = re.compile(r"\b\d{2}/\d{2}/\d{4}(?: at about \d{2}:\d{2} hrs)?")
VEHICLE = re.compile(r"\b[A-Z]{2}\d{1,2}[A-Z]?-[A-Z]{1,2}-\d{4}\b")
KIN = re.compile(r"\s[SDW]/o ([A-Z][a-z]+(?: [A-Z][a-z]+){0,3})(?:, R/o ([^;.]+))?")   # "X S/o Y, R/o Z"
ALIAS = re.compile(r"([A-Z][a-z]+(?: [A-Z][a-z]+){0,3}) @ ([A-Z][a-z]+(?: [A-Z][a-z]+){0,3})")
SENT = re.compile(r"[^.;]+[.;]?")

# role cues: (regex, role, priority). Higher priority wins when a person has several mentions.
CUES = [
    (r"\bco-accused\b", "ACCUSED", 6), (r"\baccused\b", "ACCUSED", 6), (r"\bapprehended\b", "ACCUSED", 6),
    (r"\brevealed the role of\b", "ACCUSED", 5), (r"\bidentified from cctv\b", "ACCUSED", 5),
    (r"\bintroduced himself as\b", "ACCUSED", 4),
    (r"\bcomplainant\b", "COMPLAINANT", 5), (r"\bvictims?\b", "VICTIM", 4), (r"\breported (similar )?losses\b", "VICTIM", 4),
    (r"\bwitness(?:ed)?\b", "WITNESS", 3), (r"\bsecurity guard\b", "WITNESS", 3), (r"\bstatement of\b", "WITNESS", 2),
    (r"\bin association with\b", "ACCUSED", 4), (r"\bact with\b", "ASSOCIATE", 3),
    (r"\brelative\b", "MENTIONED", 2), (r"\bsold to\b", "MENTIONED", 2), (r"\bunder verification\b", "MENTIONED", 2),
    (r"\bmentioned\b", "MENTIONED", 1),
]
CUES = [(re.compile(p, re.I), r, w) for p, r, w in CUES]
NEGATIONS = re.compile(r"no role has been attributed|no material against|do not personally know|could not identify|denied", re.I)


@dataclass
class Entity:
    text: str
    type: str
    start: int
    end: int
    normalized: str | None = None
    role: str | None = None
    linked_person_id: str | None = None
    confidence: float = 0.0
    note: str | None = None


class Gazetteer:
    def __init__(self, person_names: dict[str, set], places: list[str], orgs: list[str],
                 person_phones: dict[str, set], person_cases: dict[str, set]):
        self.name_to_pids = {n: set(p) for n, p in person_names.items() if n and len(n) > 2}
        self.person_phones = person_phones
        self.person_cases = person_cases
        names = sorted(self.name_to_pids, key=len, reverse=True)
        self.name_re = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b") if names else None
        pl = sorted(set(p for p in places if p), key=len, reverse=True)
        self.place_re = re.compile("(" + "|".join(re.escape(p) for p in pl) + ")") if pl else None
        og = sorted(set(o for o in orgs if o), key=len, reverse=True)
        self.org_re = re.compile("(" + "|".join(re.escape(o) for o in og) + ")") if og else None

    def link(self, name: str, case_id: str | None, nearby_phones: set) -> tuple[str | None, float, str]:
        pids = self.name_to_pids.get(name)
        if not pids:   # fuzzy fallback for spelling variants
            best = [(n, fuzz.WRatio(name, n)) for n in self.name_to_pids if abs(len(n) - len(name)) < 4]
            best = [b for b in best if b[1] >= 93]
            if not best:
                return None, 0.0, "no matching person record"
            pids = set().union(*(self.name_to_pids[b[0]] for b in best))
        scored = []
        for p in pids:
            s = 0.55
            if case_id and case_id in self.person_cases.get(p, ()):
                s += 0.3
            if nearby_phones & self.person_phones.get(p, set()):
                s += 0.15
            scored.append((s, p))
        scored.sort(reverse=True)
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            return None, scored[0][0] / 2, f"ambiguous: {len(scored)} records share this name ({', '.join(p for _, p in scored)})"
        note = "linked using case context" if scored[0][0] >= 0.85 else "linked by name only"
        return scored[0][1], round(min(scored[0][0], 0.98), 2), note


def _role_for(sentence: str, rel_start: int, rel_end: int) -> tuple[str | None, float]:
    """Nearest role cue wins (cues before the name are preferred: 'the accused X' vs
    'X, a relative of one accused'); cue priority only breaks ties."""
    best, best_key = None, None
    for rx, role, pr in CUES:
        for m in rx.finditer(sentence):
            if m.end() <= rel_start:
                dist = rel_start - m.end()
            elif m.start() >= rel_end:
                dist = (m.start() - rel_end) * 1.5
            else:
                continue
            if dist > 90:
                continue
            key = (dist, -pr)
            if best_key is None or key < best_key:
                best, best_key = role, key
    return best, (best_key[0] if best_key else 0)


def extract(text: str, gaz: Gazetteer, case_id: str | None = None, with_roles: bool = True) -> list[Entity]:
    ents: list[Entity] = []
    if not text:
        return ents
    for rx, t in ((PHONE, "PHONE"), (ACCOUNT, "ACCOUNT"), (AMOUNT, "AMOUNT"), (DATETIME, "DATETIME"), (VEHICLE, "VEHICLE")):
        for m in rx.finditer(text):
            norm = m.group(0)
            if t == "PHONE":
                norm = "+91-" + re.sub(r"\D", "", norm)[-10:]
            elif t == "AMOUNT":
                norm = re.sub(r"[^\d.]", "", norm.replace("Rs.", "").replace("Rs", ""))
            ents.append(Entity(m.group(0), t, m.start(), m.end(), norm, confidence=0.99))
    if gaz.place_re:
        for m in gaz.place_re.finditer(text):
            ents.append(Entity(m.group(0), "LOCATION", m.start(), m.end(), m.group(0), confidence=0.95))
    if gaz.org_re:
        for m in gaz.org_re.finditer(text):
            ents.append(Entity(m.group(0), "ORG", m.start(), m.end(), m.group(0), confidence=0.95))
    phones_in_text = {e.normalized for e in ents if e.type == "PHONE"}
    aliases = {m.start(2): m for m in ALIAS.finditer(text)}
    if gaz.name_re:
        for sm in SENT.finditer(text):
            sent, off = sm.group(0), sm.start()
            neg = bool(NEGATIONS.search(sent))
            sent_phones = {"+91-" + re.sub(r"\D", "", p)[-10:] for p in PHONE.findall(sent)}
            for m in gaz.name_re.finditer(sent):
                name = m.group(1)
                a, b = off + m.start(1), off + m.end(1)
                if text[max(0, a - 4):a] in ("S/o ", "D/o ", "W/o "):
                    continue            # a parent's name, not a mention of the person record with that name
                pid, conf, note = gaz.link(name, case_id, sent_phones or phones_in_text)
                role, _ = _role_for(sent, m.start(1), m.end(1)) if with_roles else (None, 0)
                if a in aliases:
                    note = f"recorded alias of '{aliases[a].group(1)}' in the same text"
                    etype = "ALIAS"
                else:
                    etype = "PERSON"
                if neg and role in ("ACCUSED", "ASSOCIATE"):
                    pass  # denial by an accused does not change the recorded role
                ents.append(Entity(name, etype, a, b, name, role or ("MENTIONED" if with_roles else None), pid, conf,
                                   note + ("; sentence contains a disclaimer/denial" if neg else "")))
    # "Name S/o Father, R/o Address" — attach father's name / stated address to the person just named
    for e in [x for x in ents if x.type in ("PERSON", "ALIAS")]:
        m = KIN.match(text, e.end)
        if m:
            ents.append(Entity(m.group(1), "FATHER_NAME", m.start(1), m.end(1), m.group(1), None, e.linked_person_id,
                               e.confidence, f"father's name stated for {e.text}"))
            if m.group(2):
                ents.append(Entity(m.group(2).strip(), "ADDRESS", m.start(2), m.end(2), m.group(2).strip(), None,
                                   e.linked_person_id, e.confidence, f"residence stated for {e.text}"))
    ents.sort(key=lambda e: e.start)
    return ents


ROLE_PRIORITY = {"COMPLAINANT": 6, "ACCUSED": 5, "VICTIM": 4, "WITNESS": 3, "ASSOCIATE": 2, "MENTIONED": 1}


def person_roles(ents: list[Entity]) -> dict[str, tuple[str, float]]:
    """Strongest recorded role per linked person within one document. ALIAS mentions are
    identity clues (handled by identity resolution), not roles for another record; links
    made by name only (no case context) are too weak to assign a role."""
    out = {}
    for e in ents:
        if e.type == "PERSON" and e.linked_person_id and e.role and e.confidence >= 0.8:
            cur = out.get(e.linked_person_id)
            if not cur or ROLE_PRIORITY[e.role] > ROLE_PRIORITY[cur[0]]:
                out[e.linked_person_id] = (e.role, e.confidence)
    return out


def build_gazetteer() -> Gazetteer:
    from ... import db
    names, phones, cases = defaultdict(set), defaultdict(set), defaultdict(set)
    for r in db.query("SELECT person_id, display_name, names, phones FROM persons WHERE coalesce(origin, 'SYNTHETIC') <> 'PUBLIC_RECORD'"):
        for n in r["names"] or []:
            names[n].add(r["person_id"])
        phones[r["person_id"]] = set(r["phones"] or [])
    for r in db.query("SELECT DISTINCT person_id, case_id FROM events WHERE person_id IS NOT NULL "
                      "UNION SELECT DISTINCT entity_id_2, case_id FROM events WHERE entity_id_2 LIKE 'P%%'"):
        cases[r["person_id"]].add(r["case_id"])
    places = [r["location_name"] for r in db.query("SELECT DISTINCT location_name FROM events WHERE modality IN ('LOCATION','FIR')")]
    orgs = [r["n"] for r in db.query("SELECT DISTINCT extra->>'receiver_name' n FROM events WHERE extra->>'receiver_org_id' <> '' "
                                     "UNION SELECT DISTINCT extra->>'sender_name' FROM events WHERE extra->>'sender_org_id' <> ''")]
    return Gazetteer(names, places, orgs, phones, cases)
