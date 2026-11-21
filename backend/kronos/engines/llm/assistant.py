"""KRONOS Assistance & Detective — evidence-grounded LLM layer (local Llama 3.1 8B via Ollama).

Pipeline per question
 1. resolve scope (case / person from UI + IDs mentioned in the question)
 2. detect intents → decide which engines hold relevant information
 3. collect evidence items from the engines (each item keeps its evidence/source IDs)
 4. add hybrid-retrieval chunks (pgvector + full text)
 5. rank, de-duplicate, apply a token budget and split into batches
 6. batch → extract cited notes (map); synthesise (reduce) — IDs preserved throughout
 7. validate citations: any ID not present in the supplied evidence is removed and reported
 8. return a frontend ChatMessage with referenced evidence / case / person IDs
If the LLM is unavailable, a deterministic, fully cited answer is assembled from the same evidence.
"""
from __future__ import annotations

import re
import time
from datetime import datetime

import pandas as pd

from ... import db
from ...config import settings
from ..identity import resolver
from ..intelligence import hypothesis, next_evidence, priority
from ..multimodal import case_intel, financial
from ..store import events
from ..temporal import timeline, travel
from . import language, ollama, retrieval
from . import search as evsearch

ID_RX = re.compile(r"\b(EVD-[A-Z]+\d+|NBE-[0-9A-F]{10}|IDC-P\d{5}-P\d{5}|CASE\d{3}|P\d{5})\b")
INTENTS = {
    "SUMMARY": r"summar|overview|what happened|brief|describe",
    "PEOPLE": r"\bwho\b|people|person|mentioned|accused|suspect|witness|complainant|victim|named",
    "FINANCIAL": r"financ|money|transaction|transfer|amount|paid|payment|bank|account|₹|rs\b|launder|fund",
    "COMMUNICATION": r"call|communicat|message|chat|sms|whatsapp|telegram|contact|phone",
    "LOCATION": r"locat|where|place|visit|travel|present|near|alibi|gps|tower",
    "TIMELINE": r"when|timeline|chronolog|before|after|first|earliest|latest|last|recent|date|sequence|routine",
    "CASES": r"which cases|how many cases|other cases|cross|across cases|primary",
    "IDENTITY": r"same person|alias|identity|also known|duplicate|nickname",
    "EVIDENCE": r"evidence|support|record|prove|source",
    "PRIORITY": r"priority|further investigation|warrant|focus|rank|most important|who should",
    "HYPOTHESIS": r"hypothes|involv|contradict|exculpat|alternat|against|innocent|guilt|culprit|\bthe criminal\b|committed|why not|"
                  r"\bcommit\b|mastermind|\barrest",
    "NEXT": r"next|additional evidence|obtain|what else|missing|gap|recommend",
    "PATTERN": r"pattern|unusual|anomal|suspicious|connection|link|network|related",
}

EXCULPATORY = re.compile(r"not\s+(be\s+|been\s+)?(guilty|involved|the culprit)|innocen|alternat|exculpat|why not|"
                         r"defen[cs]e|explain (it )?away|other explanation", re.I)

SYS_ASSIST = """You are KRONOS ASSISTANCE, a factual assistant for police investigators.
Rules:
- Use ONLY the numbered evidence provided. Never use outside knowledge or invent records.
- After every factual statement cite the supporting ID(s) in square brackets exactly as given, e.g. [EVD-TXN000123].
  Never cite the item numbers in round brackets; cite only the IDs.
- Every bullet point MUST end with at least one evidence ID in square brackets (EVD-…); copy IDs exactly from the evidence.
- Include case IDs, person IDs, timestamps and amounts exactly as written in the evidence.
- If the evidence does not answer the question, say plainly that it cannot be established from available records.
- Describe recorded roles ("recorded as accused"); never state or imply guilt.
- Prior criminal records are context only: never use them as evidence for the current allegation, and always state
  the disposition (e.g. acquitted) and that the record link may be unconfirmed.
- Be concise: a direct answer, then up to 6 bullet points, then one line starting 'Uncertainty:'."""

SYS_DETECT = """You are KRONOS DETECTIVE, an analytical assistant that helps investigators test hypotheses.
Rules:
- Use ONLY the numbered evidence provided; cite IDs in square brackets after each point, e.g. [EVD-LOC000812].
- Clearly label analysis as hypotheses, never as facts or findings of guilt.
- ALWAYS give both sides: what supports a line of inquiry AND what contradicts it or offers an innocent explanation.
- If no contradicting evidence is present, say so explicitly; do not invent any.
- Prior criminal records are context only and must never be used as support for a hypothesis.
- Use these headings: Possible patterns / Supporting evidence / Contradicting evidence & alternative explanations /
  Missing evidence & next steps / Uncertainty. Keep it under 300 words."""

SYS_REWRITE = ("Rewrite the investigator's latest question as one standalone question, resolving pronouns and references "
               "from the conversation. Keep all IDs (CASE…, P…, EVD-…). Output only the question.")

SYS_MAP = """Extract only the facts from the evidence below that help answer the question. Keep every relevant ID in
square brackets. Output short bullet points; if nothing is relevant output 'NONE'."""


def _intents(q: str, mode: str) -> set[str]:
    ql = q.lower()
    out = {k for k, rx in INTENTS.items() if re.search(rx, ql)}
    if mode == "DETECTIVE":
        out |= {"PRIORITY", "HYPOTHESIS", "NEXT", "PATTERN"} if not out & {"PRIORITY", "HYPOTHESIS", "NEXT", "PATTERN"} else set()
    return out or {"SUMMARY"}


class Evidence:
    def __init__(self):
        self.items: list[dict] = []
        self.keys = set()

    def add(self, text: str, ids: list[str], score: float, source: str, ts: str | None = None, case: str | None = None):
        key = (text[:120])
        if key in self.keys or not text:
            return
        self.keys.add(key)
        self.items.append({"text": text, "ids": [i for i in ids if i][:6], "score": score, "source": source, "ts": ts,
                           "case": case})


def _rel_min(m) -> str:
    try:
        m = int(round(float(m)))
    except (TypeError, ValueError):
        return "time relative to the incident unknown"
    return "at the incident time" if m == 0 else f"{abs(m)} min {'before' if m < 0 else 'after'} the incident"


def _add_alternates(E, h: dict, score: float):
    """Each alternate hypothesis (why the person may NOT have been involved) as its own cited evidence item."""
    for al in (h.get("alternateHypotheses") or [])[:3]:
        E.add(f"Alternate hypothesis {al['code']} for {h['personId']} — {al['title']} ({al['label']}, strength {al['strength']}): "
              f"{al['statement']} Evidence: " + "; ".join(x["text"] for x in al["evidence"][:2]) + f". Test that would settle it: {al['test']}",
              [i for x in al["evidence"][:2] for i in x["evidenceIds"][:1]], score, "ALTERNATE")
    if h.get("comparison"):
        E.add(f"Line of inquiry vs alternates for {h['personId']}: {h['comparison']['verdict']}", [h["personId"]], score, "ALTERNATE")


def _fmt_ev(r) -> str:
    ts = r.ts.strftime("%Y-%m-%d %H:%M") if pd.notna(r.ts) else "date unknown"
    return f"{ts} {r.case_id} {r.modality}: {r.event_description} (reliability {r.source_reliability})"


def _collect(q: str, mode: str, case_id: str | None, person_id: str | None, modality: str | None, intents: set,
             ctx_ids: list[str] | None = None) -> Evidence:
    E = Evidence()
    df = events()
    mod_map = {"FIR": "FIR", "COMMUNICATION": "SOCIAL", "CDR": "CDR", "LOCATION": "LOCATION", "FINANCIAL": "FINANCIAL"}
    # ---------------- person scope
    if person_id:
        p = db.query_one("SELECT * FROM persons WHERE person_id=%s", (person_id,))
        if p:
            roles = db.query("SELECT case_id, role, method, evidence_id FROM person_case_roles WHERE person_id=%s ORDER BY case_id", (person_id,))
            E.add(f"Person {person_id} ({p['display_name']}); recorded names {', '.join(p['names'])}; phones {', '.join(p['phones'])}; "
                  f"devices {', '.join(p['devices'])}; accounts {', '.join(p['accounts'])}; first record {p['first_seen']}, "
                  f"latest {p['last_seen']}.", [person_id], 5, "PERSON")
            E.add(f"{person_id} case involvement: " + "; ".join(f"{r['case_id']} recorded as {r['role']} ({r['method']})" for r in roles),
                  [r["evidence_id"] for r in roles if r["evidence_id"]] + sorted({r["case_id"] for r in roles}), 5, "ROLES")
            tl = timeline.timeline(person_id, case_id=case_id, limit=None)
            if modality and modality != "ALL":
                tl = [e for e in tl if e["modality"] == modality or (modality == "COMMUNICATION" and e["modality"] == "CDR")]
            want = {"FINANCIAL": {"FINANCIAL"}, "COMMUNICATION": {"CDR", "COMMUNICATION"}, "LOCATION": {"LOCATION"}}
            mods = set().union(*(want[i] for i in intents if i in want)) if intents & set(want) else None
            months = [m for m in ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec") if m in q.lower()]
            for i, e in enumerate(tl):
                s = 1.0
                if e["isAnomaly"]: s += 2
                if e["modality"] in ("FIR", "CROSS_CASE"): s += 2
                if mods and e["modality"] in mods: s += 2
                if months and e["monthStr"].lower() in months: s += 3
                if "TIMELINE" in intents and (i < 3 or i >= len(tl) - 3): s += 3
                E.add(f"{e['timestamp'][:16]} {e['caseId']} {e['modality']}: {e['title']} — {e['description']}",
                      [e["evidenceId"]], s, "TIMELINE", e["timestamp"], e["caseId"])
            if intents & {"LOCATION", "PATTERN", "HYPOTHESIS", "TIMELINE"}:
                flags = travel.detect(person_id)
                if not flags:     # explicit negative finding, so "none detected" answers are grounded
                    n_loc = int(((df.person_id == person_id) & df.latitude.notna()).sum())
                    E.add(f"Impossible-travel check for {person_id}: no location inconsistency detected across {n_loc} "
                          f"location-bearing records (limits {settings.travel_max_ground_kmh:.0f} km/h by road, "
                          f"{settings.travel_max_air_kmh:.0f} km/h by air).", [person_id], 6, "TRAVEL")
                for f in flags[:5]:
                    E.add(f"Location inconsistency ({f['verdict']}): {f['first']['location']} at {f['first']['timestamp']} then "
                          f"{f['second']['location']} at {f['second']['timestamp']} — {f['distanceKm']} km in {f['elapsedMinutes']} min "
                          f"(implied {f['impliedSpeedKmh']} km/h). {f['interpretation']}",
                          [f["first"]["evidenceId"], f["second"]["evidenceId"]], 6, "TRAVEL")
            from ..identity import history as hist_mod
            if intents & {"IDENTITY", "PATTERN", "HYPOTHESIS", "CASES", "PEOPLE"} or re.search(r"history|prior|record|previous|antecedent", q.lower()):
                ph = hist_mod.person_history(person_id)
                if not (ph["priorRecords"] + ph["priorRecordsViaPossibleIdentity"]):
                    E.add(f"Criminal-history check for {person_id}: no prior record is linked to this person in the available "
                          "records.", [person_id], 5, "HISTORY")
                for l in (ph["priorRecords"] + ph["priorRecordsViaPossibleIdentity"])[:5]:
                    rec = l["record"]
                    via = f" via possible identity {l['viaPersonId']}" if l.get("viaPersonId") else ""
                    E.add(f"PRIOR RECORD (context only — not evidence of the current allegation){via}: {rec['offence']} ({rec['sections']}), "
                          f"{rec['firReference']}, {rec['date']}, disposition {rec['disposition']}; link {l['band']} score {l['score']} "
                          f"[{l['status']}]. Basis: {'; '.join(l['reasons'][:3])}" + (f". Contradictions: {'; '.join(l['contradicting'][:2])}" if l["contradicting"] else ""),
                          [rec["evidenceId"]], 5, "HISTORY")
                for a in ph["associatedCases"][:4]:
                    E.add(f"Network-associated case {a['caseId']} (not one of {person_id}'s cases) via " +
                          "; ".join(f"{v.get('personId') or v.get('case')}: {', '.join(v['basis'][:2])}" for v in a["via"][:2]),
                          [a["caseId"]], 4, "GRAPH")
            if intents & {"IDENTITY", "PATTERN", "HYPOTHESIS", "CASES"}:
                cands = resolver.list_candidates(person_id=person_id)
                if not cands:
                    E.add(f"Identity resolution for {person_id}: no candidate match with any other person record was generated.",
                          [person_id], 5, "IDENTITY")
                for c in cands[:4]:
                    E.add(f"Identity candidate {c['candidateId']}: {c['nameA']} ({c['personA']}) / {c['nameB']} ({c['personB']}) "
                          f"score {c['score']} band {c['band']} status {c['status']}. Reasons: {'; '.join(c['reasons'][:5])}. "
                          f"Contradictions: {'; '.join(x['why'] for x in c['contradicting'][:2]) or 'none recorded'}.",
                          [c["candidateId"]] + [s["evidenceId"] for s in c["supporting"][:3] if s.get("evidenceId")], 6, "IDENTITY")
    # ---------------- case scope
    if case_id:
        I = case_intel.get(case_id)
        if I:
            s = db.query_one("SELECT summary_json FROM case_summaries WHERE case_id=%s", (case_id,))
            if s:
                j = s["summary_json"]
                E.add(f"Case summary {case_id}: {j['conciseSummary']} {j['detailedNarrative']}", j["importantEvidence"][:6] + [case_id], 8, "SUMMARY")
            E.add(f"People recorded in {case_id}: " + "; ".join(f"{p['name']} ({p['personId']}) recorded as {p['primaryRole']} via "
                  f"{p['roles'][0]['method']}" for p in I["people"]), [e for p in I["people"] for e in p["evidenceIds"][:1]], 7, "PEOPLE")
            for k in I["keyEvents"]:
                E.add(f"{k['timestamp']} {case_id}: {k['event']}", k["evidenceIds"], 4 + 2 * ("TIMELINE" in intents), "KEY_EVENT", k["timestamp"], case_id)
            for o in I["crossSourceObservations"]:
                E.add(f"Cross-source observation: {o['observation']}", [e for f in o["facts"] for e in f["evidenceIds"]], 5 + 2 * bool(intents & {"PATTERN", "HYPOTHESIS", "PEOPLE"}), "OBSERVATION")
            fin = I["financial"]
            if intents & {"FINANCIAL", "PATTERN", "SUMMARY", "HYPOTHESIS"}:
                E.add(f"{case_id} financial records: {fin['transactions']} transactions, total ₹{fin['totalVolume']:,.0f}, "
                      f"{fin['flaggedCount']} flagged.", [case_id], 5, "FINANCIAL")
                for f in fin["flagged"][:10]:
                    E.add(f"Flagged {f['channel']} ₹{f['amount']:,.0f} on {f['timestamp']} {f['sender']} ({f['senderName']}) → "
                          f"{f['receiver']} ({f['receiverName']}), purpose '{f['purpose']}': {'; '.join(f['reasons'][:2])}"
                          + (f" Alternative: {f['alternativeExplanation']}" if f.get("alternativeExplanation") else ""),
                          [f["evidenceId"]], 5 + 2 * ("FINANCIAL" in intents), "FIN_FLAG", f["timestamp"], case_id)
                for st in fin["structuring"][:3]:
                    E.add(f"Structuring pattern: {st['count']} transfers {st['sender']} → {st['receiver']} just below threshold, total ₹{st['total']:,.0f}",
                          st["evidenceIds"][:4], 6, "FIN_PATTERN")
                for fi in fin["fanIn"][:3]:
                    E.add(f"Fan-in: account {fi['account']} received ₹{fi['total']:,.0f} from {len(fi['senders'])} individuals ({', '.join(fi['senders'][:5])})",
                          fi["evidenceIds"][:4], 6, "FIN_PATTERN")
            comm = I["communication"]
            if intents & {"COMMUNICATION", "PATTERN", "SUMMARY", "HYPOTHESIS", "TIMELINE"}:
                for pr in comm["pairs"][:6]:
                    E.add(f"Communication {pr['names'][0]} ({pr['persons'][0]}) ↔ {pr['names'][1]} ({pr['persons'][1]}): {pr['calls']} calls, "
                          f"{pr['messages']} messages, {pr['first']} to {pr['last']}" + (f"; also in {', '.join(pr['otherCases'])}" if pr["otherCases"] else ""),
                          pr["evidenceIds"][:3], 4 + 2 * ("COMMUNICATION" in intents), "COMM")
                if comm["aroundIncident"]:
                    a = comm["aroundIncident"]
                    E.add(f"Around the incident ({a['window']}): {a['count']} contacts ({a['before']} before, {a['after']} after); "
                          f"{a['betweenNamedPersons']} between FIR-named persons; baseline ≈{a['expectedFromBaseline']}.",
                          a["namedPersonEvidence"][:5], 6, "COMM")
                for b in comm["bursts"][:3]:
                    E.add(f"Burst: {b['count']} contacts between {b['persons'][0]} and {b['persons'][1]} from {b['start']} to {b['end']}",
                          b["evidenceIds"][:4], 5, "COMM")
                for m in comm["importantMessages"][:6]:
                    E.add(f"Message {m['timestamp']} {m['from']} → {m['to']}: \"{m['text']}\" ({'; '.join(m['reasons'])})", [m["evidenceId"]],
                          5 + 2 * ("COMMUNICATION" in intents), "MESSAGE", m["timestamp"], case_id)
            loc = I["location"]
            if intents & {"LOCATION", "PATTERN", "HYPOTHESIS", "SUMMARY"}:
                for x in loc["nearIncident"][:6]:
                    E.add(f"{x['personId']} {x['modality']} record {x['distanceKm']} km from incident location, "
                          f"{_rel_min(x['minutesFromIncident'])} (accuracy {x['accuracyM']} m)", [x["evidenceId"]], 5, "LOCATION")
                for x in loc["namedPersonsElsewhere"][:4]:
                    E.add(f"Possible exculpatory: {x['personId']} recorded at {x['location'] or 'a location ' + str(x['distanceKm']) + ' km from the incident'}"
                          f"{' ' + str(x['distanceKm']) + ' km away' if x['location'] else ''}, {_rel_min(x['minutesFromIncident'])} "
                          f"(reliability {x['reliability']})", [x["evidenceId"]], 7, "LOCATION")
            if mode == "DETECTIVE" or intents & {"PRIORITY", "HYPOTHESIS", "NEXT"}:
                pr = priority.assess(case_id)
                for r in pr["ranking"][:5]:
                    top = sorted(r["factors"], key=lambda f: -abs(f["contribution"]))[:3]
                    E.add(f"Investigative priority {r['personId']} ({r['name']}, recorded {r['recordedRole']}): {r['label']} "
                          f"(score {r['priorityScore']}); main factors: " + "; ".join(f"{f['factor']} {f['contribution']} — {f['explanation']}" for f in top),
                          [r["personId"]] + r["supportingEvidence"][:2] + r["contradictingEvidence"][:2], 6 + 2 * ("PRIORITY" in intents), "PRIORITY")
                hy = hypothesis.analyse(case_id, person_id if person_id else None, top=2)
                for h in hy["hypotheses"]:
                    E.add(f"Hypothesis '{h['hypothesis']}'. Supporting: " + "; ".join(f"{s['text']}" for s in h["supporting"][:4]) +
                          ". Contradicting: " + "; ".join(s["text"] for s in h["contradicting"][:4]) + f". Assessment: {h['uncertainty']}. "
                          f"Evidential balance {h['confidence']['evidentialBalance']} ({h['confidence']['assessment']}, completeness "
                          f"{h['confidence']['completeness']}; not a probability of guilt).",
                          [e for s in h["supporting"][:3] for e in s["evidenceIds"][:1]] + [e for s in h["contradicting"][:3] for e in s["evidenceIds"][:1]],
                          8 + 2 * ("HYPOTHESIS" in intents), "HYPOTHESIS")
                    _add_alternates(E, h, 7 + 2 * ("HYPOTHESIS" in intents))
                for r in next_evidence.recommend(case_id)[:5]:
                    E.add(f"Recommended evidence {r['id']} [{r['priority']}, value score {r['valueScore']}, status {r['status']}]: {r['evidenceType']} — {r['reason']}. "
                          f"Action: {r['verificationAction']}", [r["id"]] + r["basisEvidenceIds"][:2], 5 + 3 * ("NEXT" in intents), "NEXT")
    elif person_id and (mode == "DETECTIVE" or intents & {"HYPOTHESIS", "NEXT", "PRIORITY"}):
        cases = [r["case_id"] for r in db.query("SELECT DISTINCT case_id FROM person_case_roles WHERE person_id=%s AND role <> 'RECORD_SUBJECT'", (person_id,))]
        for cid in cases[:2]:
            for h in hypothesis.analyse(cid, person_id)["hypotheses"]:
                E.add(f"Hypothesis '{h['hypothesis']}'. Supporting: " + "; ".join(s["text"] for s in h["supporting"][:4]) +
                      ". Contradicting: " + "; ".join(s["text"] for s in h["contradicting"][:4]) + f". Assessment: {h['uncertainty']}. "
                      f"Verification: {'; '.join(h['verificationSteps'][:3])}",
                      [e for s in h["supporting"][:3] for e in s["evidenceIds"][:1]] + [e for s in h["contradicting"][:3] for e in s["evidenceIds"][:1]] + [cid],
                      9, "HYPOTHESIS")
                _add_alternates(E, h, 8)
    # ---------------- global questions (no scope)
    if not case_id and not person_id:
        if intents & {"PATTERN", "PRIORITY", "CASES"}:
            from ..graph.analytics import cross_case
            for c in cross_case()[:5]:
                E.add(f"Cross-case link: {c['summary']}: " + ", ".join(f"{v['type']} {v['id']}" for v in c["links"][:4]), c["cases"], 5, "GRAPH")
    # ---------------- evidence retrieval engine (structured filters + full text + semantic)
    found = evsearch.search(q, case_id=case_id, person_id=person_id, limit=8, context_ids=ctx_ids)
    interp = "; ".join(found["interpretation"].get("explain", []))
    for i, r in enumerate(found["results"]):
        E.add(f"{r['timestamp']} {r['caseId']} {r['modality']}: {r['description']} (matched: {interp or 'text similarity'})",
              [r["evidenceId"]], 4.8 - 0.05 * i, "SEARCH", r["timestamp"], r["caseId"])
    # ---------------- hybrid retrieval
    for r in retrieval.search(q, case_id=case_id, person_id=person_id, k=8):
        E.add(r["content"][:700], r["evidence_ids"][:4] + ([r["case_id"]] if r["case_id"] else []), 3.5, "RETRIEVAL")
    # ---------------- explicit evidence IDs in the question
    for eid in set(re.findall(r"EVD-[A-Z]+\d+", q.upper())):
        row = df[df.evidence_id == eid]
        if not row.empty:
            E.add(_fmt_ev(row.iloc[0]), [eid], 10, "EXPLICIT")
    return E


NUM_RX = re.compile(r"\d[\d,]{3,}(?:\.\d+)?")


def _fact_check(text: str, used: list[dict]) -> tuple[str, int]:
    """Line-level grounding check: every figure (amount, count, date part with ≥4 digits) written on a line
    that cites evidence must appear in the text of at least one cited item. Otherwise the line is flagged.
    (Catches the failure mode where the model cites a real ID but attaches the wrong facts to it.)"""
    id2text: dict[str, list[str]] = {}
    for it in used:
        for i in it["ids"]:
            id2text.setdefault(i, []).append(it["text"])
    out, flagged = [], 0
    for line in text.split("\n"):
        ids = re.findall(r"EVD-[A-Z]+\d+", line)
        if ids:
            body = ID_RX.sub(" ", line)
            nums = {n.replace(",", "").rstrip(".") for n in NUM_RX.findall(body)}
            src = " ".join(t for i in ids for t in id2text.get(i, [])).replace(",", "")
            missing = sorted(n for n in nums if n not in src and n.split(".")[0] not in src)
            if missing:
                line += f"  ⚠ [figures {', '.join(missing[:3])} not found in the cited record(s) — verify before relying on this line]"
                flagged += 1
        out.append(line)
    return "\n".join(out), flagged


def _batches(items: list[dict], budget: int) -> list[list[dict]]:
    out, cur, used = [], [], 0
    for it in items:
        t = ollama.estimate_tokens(it["text"]) + 12
        if cur and used + t > budget:
            out.append(cur); cur, used = [], 0
        cur.append(it); used += t
    if cur:
        out.append(cur)
    return out


def _render(items: list[dict]) -> str:
    return "\n".join(f"({i + 1}) [{' | '.join(it['ids'])}] {it['text']}" for i, it in enumerate(items))


def _fallback(q: str, mode: str, items: list[dict]) -> str:
    head = "[RECORDED FACTS — deterministic summary; local LLM unavailable]" if mode == "ASSISTANCE" else \
           "[ANALYTICAL HYPOTHESIS — NOT FACT — deterministic summary; local LLM unavailable]"
    lines = [head, f"Most relevant records for: \"{q}\""]
    lines += [f"- {it['text'][:260]} [{', '.join(i for i in it['ids'] if i.startswith(('EVD-', 'NBE-', 'IDC-')))[:60]}]" for it in items[:8]]
    lines.append("Uncertainty: generated without language-model synthesis; review the cited records directly.")
    return "\n".join(lines)


FOLLOW_UP = re.compile(r"\b(he|she|him|her|his|hers|they|them|their|it|its|this|that|these|those|same|also|then|why|"
                       r"what about|and the|more|further|earlier|previous|above)\b", re.I)


def _history_text(history: list[dict] | None, n: int = 4) -> str:
    out = []
    for h in (history or [])[-n:]:
        t = re.sub(r"<[^>]+>", " ", h.get("text") or "")
        t = re.sub(r"\s+", " ", t).strip()[:500]
        if t:
            out.append(f"{'Investigator' if h.get('role') == 'user' else 'KRONOS'}: {t}")
    return "\n".join(out)


def prepare(query: str, mode: str = "ASSISTANCE", case_id: str | None = None, person_id: str | None = None,
            modality: str | None = None, history: list[dict] | None = None, lang: str | None = None,
            rewrite: bool = True, budget: int | None = None) -> dict:
    """Steps 1-5 of the pipeline: language, conversation memory, scope, intents, evidence collection, ranking and
    token-budgeted batching. Shared by `answer` and by the fine-tuning data builder, so the model is trained on
    exactly the prompts it receives in production."""
    mode = "DETECTIVE" if (mode or "").upper() == "DETECTIVE" else "ASSISTANCE"
    q_orig = query.strip()
    q_lang = language.detect(q_orig)
    # a question typed in an Indian language is answered in that language; otherwise the UI language setting applies
    target = q_lang if q_lang != "en" else (lang if lang in language.LANGS else "en")
    try:
        q = language.to_english(q_orig) if q_lang != "en" else q_orig
    except ollama.LLMUnavailable:
        q = q_orig
    # ---- conversation memory: carry entities forward and rewrite follow-ups as standalone questions
    hist_txt = _history_text(history)
    ctx_ids = list(dict.fromkeys(re.findall(r"\b(CASE\d{3}|P\d{5})\b", hist_txt.upper())))
    standalone = q
    if rewrite and hist_txt and (FOLLOW_UP.search(q) or len(q.split()) <= 7) and not re.search(r"\b(CASE\d{3}|P\d{5})\b", q.upper()):
        try:
            standalone = ollama.chat([{"role": "system", "content": SYS_REWRITE},
                                      {"role": "user", "content": f"Conversation:\n{hist_txt}\n\nLatest question: {q}"}],
                                     max_tokens=80, temperature=0).strip().strip('"')
        except ollama.LLMUnavailable:
            standalone = q
    # scope: IDs in the (standalone) question; otherwise, only for genuine follow-ups, the most recent IDs in the conversation
    m_case = re.findall(r"CASE\d{3}", standalone.upper())
    m_person = re.findall(r"\bP\d{5}\b", standalone.upper())
    follow = bool(hist_txt and FOLLOW_UP.search(q))
    recent = re.findall(r"\b(CASE\d{3}|P\d{5})\b", hist_txt.upper())[::-1]
    if not case_id:
        case_id = m_case[0] if m_case else (next((x for x in recent if x.startswith("CASE")), None) if follow else None)
    if not person_id:
        person_id = m_person[0] if m_person else (next((x for x in recent if x.startswith("P")), None) if follow else None)
    q = standalone
    intents = _intents(q, mode)
    E = _collect(q, mode, case_id, person_id, modality, intents, ctx_ids)
    # "why may this person NOT be guilty?": the alternate hypotheses lead the evidence, and the model is told to answer from them
    exculpatory = bool(EXCULPATORY.search(q))
    if exculpatory:
        for it in E.items:
            if it["source"] == "ALTERNATE":
                it["score"] += 4
    items = sorted(E.items, key=lambda x: -x["score"])
    all_batches = _batches(items, budget or settings.llm_evidence_budget_tokens)
    # the first batch always goes in; further batches only if they still hold highly relevant evidence
    # (each extra batch costs one local-LLM call, ~15-25 s on a laptop GPU)
    batches = all_batches[:1] + [b for b in all_batches[1:] if max(it["score"] for it in b) >= 6][: settings.llm_max_batches - 1]
    used = [it for b in batches for it in b]
    scope = f"Scope: case {case_id or 'any'}, person {person_id or 'any'}" + (f", modality filter {modality}" if modality and modality != "ALL" else "")
    if exculpatory and any(it["source"] == "ALTERNATE" for it in used):
        scope += ("\nThe question asks why this person may NOT have been involved. Answer from the 'Alternate hypothesis' "
                  "evidence items, strongest first: for each, give its evidence and the test that would settle it. Then give "
                  "the 'Line of inquiry vs alternates' verdict. Do not call anyone guilty or innocent.")
    if hist_txt:
        scope += "\nConversation so far (for resolving references only — every fact must come from the evidence):\n" + hist_txt
    return dict(mode=mode, q_orig=q_orig, q_lang=q_lang, target=target, q=q, case_id=case_id, person_id=person_id,
                intents=intents, items=items, batches=batches, used=used, allowed={i for it in used for i in it["ids"]},
                sys_prompt=SYS_ASSIST if mode == "ASSISTANCE" else SYS_DETECT, scope=scope, history=history)


def user_message(q: str, scope: str, ctx: str) -> str:
    return f"Question: {q}\n{scope}\n\nEvidence:\n{ctx}"


def answer(query: str, mode: str = "ASSISTANCE", case_id: str | None = None, person_id: str | None = None,
           modality: str | None = None, history: list[dict] | None = None, lang: str | None = None) -> dict:
    t0 = time.time()
    P = prepare(query, mode, case_id, person_id, modality, history, lang)
    mode, q_orig, q_lang, target, q = P["mode"], P["q_orig"], P["q_lang"], P["target"], P["q"]
    case_id, person_id, intents, items, batches, used = P["case_id"], P["person_id"], P["intents"], P["items"], P["batches"], P["used"]
    allowed, sys_prompt, scope = P["allowed"], P["sys_prompt"], P["scope"]
    model_used, removed, unsupported = None, [], 0
    try:
        if len(batches) <= 1:
            ctx = _render(used)
        else:   # map: extract cited notes per batch; reduce: synthesise
            notes = []
            for b in batches:
                n = ollama.chat([{"role": "system", "content": SYS_MAP},
                                 {"role": "user", "content": user_message(q, scope, _render(b))}], max_tokens=200)
                if n.strip().upper() != "NONE":
                    notes.append(n)
            ctx = "\n".join(notes) or _render(batches[0])
        text = ollama.chat([{"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_message(q, scope, ctx)}],
                           max_tokens=480 if mode == "DETECTIVE" else 420)
        model_used = ollama.model_name()
        # citation validation
        def keep(m):
            tok = m.group(0)
            if tok.startswith(("EVD-", "NBE-", "IDC-")) and tok not in allowed:
                removed.append(tok)
                return "[unverified reference removed]"
            return tok
        text = ID_RX.sub(keep, text)
        # collapse degenerate repeated citations, e.g. "[EVD-1 | EVD-1 | EVD-1]" → "[EVD-1]"
        text = re.sub(r"\[([^\[\]]{0,600})\]", lambda m: "[" + " | ".join(dict.fromkeys(
            x.strip() for x in re.split(r"[|,]", m.group(1)) if x.strip())) + "]", text)
        text = re.sub(r"\[\s*\[unverified reference removed\]\s*\]", "[unverified reference removed]", text)
        text, unsupported = _fact_check(text, used)
        if unsupported:
            text += f"\n\n(KRONOS grounding check: {unsupported} line(s) contain figures not present in their cited records.)"
        prefix = "[RECORDED FACTS]" if mode == "ASSISTANCE" else "[ANALYTICAL HYPOTHESIS — NOT FACT]"
        text = f"{prefix}\n{text}"
        if removed:
            text += f"\n\n(KRONOS removed {len(removed)} citation(s) not present in the supplied evidence.)"
    except ollama.LLMUnavailable:
        text = _fallback(q, mode, used)
    english = text
    translated_ok = None
    if target != "en":
        lines = text.split("\n")
        tr_lines, n_done = language.translate_lines(lines, target)
        n_total = sum(1 for t in lines if t.strip() and re.search(r"[A-Za-z]", t))
        translated_ok = n_done == n_total
        text = (language.banner(target) + (f" [{n_done} of {n_total} lines translated; lines that could not be translated with "
                                           "every identifier intact are shown in English.]" if not translated_ok else "")
                + "\n" + "\n".join(tr_lines))
    cited = ID_RX.findall(english)
    ev_ids = list(dict.fromkeys(c for c in cited if c.startswith("EVD-")))
    if not ev_ids:   # surface the top evidence the answer was grounded on
        ev_ids = list(dict.fromkeys(i for it in used[:4] for i in it["ids"] if i.startswith("EVD-")))[:4]
    case_ids = list(dict.fromkeys([c for c in cited if c.startswith("CASE")] + ([case_id] if case_id else [])))
    person_ids = list(dict.fromkeys([c for c in cited if re.fullmatch(r"P\d{5}", c)] + ([person_id] if person_id else [])))
    latency = int((time.time() - t0) * 1000)
    db.execute("INSERT INTO assistant_log (mode, scope, query, answer, cited, removed_citations, model, latency_ms) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
               (mode, db.Json({"caseId": case_id, "personId": person_id, "modality": modality, "lang": target,
                               "originalQuery": q_orig}), q, text, ev_ids, removed,
                model_used, latency))
    return {
        "id": f"msg-{int(time.time() * 1000)}", "sender": "KRONOS_AI", "mode": mode, "text": text,
        "timestamp": datetime.now().strftime("%I:%M %p"),
        "referencedEvidenceIds": ev_ids[:12], "referencedCaseIds": case_ids[:8], "referencedPersonIds": person_ids[:8],
        "isAnalyticalHypothesis": mode == "DETECTIVE",
        "textEnglish": english if target != "en" else None, "language": target,
        "meta": {"intents": sorted(intents), "evidenceItems": len(used), "batches": len(batches),
                 "queryLanguage": q_lang, "answerLanguage": target, "translationOk": translated_ok,
                 "standaloneQuery": q if q != q_orig else None, "conversationTurnsUsed": len(history or []),
                 "evidenceCandidates": len(items), "droppedLowRelevance": len(items) - len(used), "model": model_used,
                 "removedCitations": removed, "unsupportedLines": unsupported, "latencyMs": latency,
                 "sources": sorted({it["source"] for it in used})},
    }
