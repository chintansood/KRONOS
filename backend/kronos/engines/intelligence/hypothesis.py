"""Hypothesis engine — supporting AND alternative/exculpatory analysis, with explainable confidence scoring.

For each hypothesis ("<person> was involved in the incident recorded in <case>") it lists the evidence
that supports it, the evidence that contradicts it, alternative innocent explanations, missing records,
verification steps and a mandatory human-review flag.

Confidence scoring (in the spirit of Analysis of Competing Hypotheses):
  * every item gets an evidential weight from its source type and reliability, with diminishing returns
    for repeated items from the same source (so ten calls do not outweigh one independent alibi);
  * evidential balance = (S − C) / (S + C + 0.5)  ∈ (−1, 1)   — leans supporting / unresolved / leans contradicting
  * completeness = share of the core sources (FIR, location, communication, financial) that bear on it.
This is an aid for testing competing explanations — NOT a probability of guilt. Prior criminal records
are shown as context only and are deliberately excluded from the score. Nothing is fabricated: if no
contradicting evidence exists in the records, it says so explicitly.
"""
from __future__ import annotations

from collections import defaultdict

from ... import db
from ..identity import resolver
from ..multimodal import case_intel
from ..store import events
from . import priority

ALT = {
    "LOCATION": "Being near the incident place may be routine (home, work, market) — check whether the person regularly visits it.",
    "COMMUNICATION": "Frequent contact may reflect family, business or social ties unrelated to the incident.",
    "FINANCIAL": "Flagged transactions may have legitimate explanations (business payments, loans, property, salary) — verify documents.",
    "TEMPORAL": "Location inconsistencies may come from a shared/cloned handset or data error rather than the person's movement.",
    "FIR": "Being named in an FIR records an allegation; it is not itself proof of involvement.",
    "IDENTITY": "An identity match may be wrong — similar names, shared family devices or accounts can belong to different people.",
}
# base evidential weights by source (supporting / contradicting)
SUP_W = {"FIR": 0.45, "LOCATION": 0.8, "COMMUNICATION": 0.6, "FINANCIAL": 0.6, "IDENTITY": 0.3}
CON_W = {"LOCATION": 0.9, "FIR": 0.35, "DEVICE": 0.3, "FINANCIAL": 0.3, "IDENTITY": 0.3, "ANALYSIS": 0.4}
REL = {"HIGH": 1.0, "MEDIUM": 0.8, "LOW": 0.55}
CORE = ("FIR", "LOCATION", "COMMUNICATION", "FINANCIAL")


def _weigh(items: list[dict], base: dict) -> float:
    """Sum of weights with diminishing returns per source: 1st item full, then ×0.5, ×0.25 …"""
    seen, total = defaultdict(int), 0.0
    for it in items:
        w = base.get(it["source"], 0.3) * REL.get(it.get("reliability", "MEDIUM"), 0.8)
        w *= 0.5 ** seen[it["source"]]
        seen[it["source"]] += 1
        it["weight"] = round(w, 3)
        total += w
    return total


def assess_person(case_id: str, pid: str, I: dict | None = None) -> dict:
    """Evidence for / against one person's involvement + explainable evidential balance (no recommendations)."""
    I = I or case_intel.get(case_id)
    df = events()
    person = next((p for p in I["people"] if p["personId"] == pid), None)
    name = person["name"] if person else pid
    obs = next((o for o in I["crossSourceObservations"] if o["personId"] == pid), {"facts": []})
    support, contra, clarify = [], [], []
    if person:
        for r in person["roles"][:1] + [x for x in person["roles"][1:] if x["role"] in ("WITNESS", "COMPLAINANT", "VICTIM")]:
            if r["role"] in ("PRINCIPAL_ACCUSED", "ACCUSED", "ASSOCIATE"):
                support.append({"source": "FIR", "text": f"Recorded as {r['role'].lower().replace('_', ' ')} ({r['method']}, confidence {r['confidence']})",
                                "evidenceIds": person["evidenceIds"][:3], "reliability": "HIGH" if r["method"] == "FIR_STRUCTURED" else "MEDIUM"})
            elif r["role"] in ("WITNESS", "COMPLAINANT", "VICTIM"):
                contra.append({"source": "FIR", "text": f"Recorded in the FIR as {r['role'].lower()}, not as accused",
                               "evidenceIds": person["evidenceIds"][:3], "reliability": "HIGH"})
    for f in obs["facts"]:
        if f["source"] == "LOCATION_CONTRA":
            contra.append({"source": "LOCATION", "text": f["text"], "evidenceIds": f["evidenceIds"], "reliability": "HIGH"})
        elif f["source"] == "TEMPORAL":     # an inconsistency neither supports nor refutes involvement
            clarify.append({"source": "TEMPORAL", "text": f["text"] + " — clarify before relying on this person's location records",
                            "evidenceIds": f["evidenceIds"]})
        else:
            support.append({"source": f["source"], "text": f["text"], "evidenceIds": f["evidenceIds"], "reliability": "HIGH"})
    for t in db.query("SELECT DISTINCT e.evidence_id, e.text_content FROM text_entities te JOIN events e USING (source_record_id) "
                      "WHERE te.linked_person_id=%s AND e.case_id=%s AND e.modality='FIR'", (pid, case_id)):
        txt = t["text_content"].lower()
        for phrase in ("denied", "no role has been attributed", "no material against", "under verification", "dispute"):
            if phrase in txt:
                contra.append({"source": "FIR", "text": f"FIR text contains: '…{phrase}…'", "evidenceIds": [t["evidence_id"]],
                               "reliability": "MEDIUM"})
    pe = df[(df.person_id == pid) & (df.case_id == case_id)]
    for dev in pe.device_id.dropna().unique():
        others = df[(df.device_id == dev) & (df.person_id != pid)].person_id.dropna().unique()
        if len(others):
            contra.append({"source": "DEVICE", "text": f"Handset {dev} is also used by {', '.join(sorted(others)[:3])} — another person may have generated some records",
                           "evidenceIds": list(df[(df.device_id == dev) & (df.person_id != pid)].evidence_id[:2]), "reliability": "HIGH"})
    for a in [a for a in I["financial"]["accounts"] if pid in a["holders"] and a["sharedHolders"]]:
        contra.append({"source": "FINANCIAL", "text": f"Account {a['account']} has multiple recorded holders ({', '.join(a['holders'])})",
                       "evidenceIds": [], "reliability": "MEDIUM"})
    for c in [c for c in resolver.list_candidates(person_id=pid) if c["band"] in ("HIGH", "MEDIUM") and c["status"] != "REJECTED"][:2]:
        other = c["personB"] if c["personA"] == pid else c["personA"]
        support.append({"source": "IDENTITY", "text": f"Possible same person as {other} ({c['nameA'] if other == c['personA'] else c['nameB']}), "
                                                      f"identity score {c['score']} [{c['status']}, {c.get('basis', 'identifier')} basis]",
                        "evidenceIds": [s["evidenceId"] for s in c["supporting"][:3] if s.get("evidenceId")],
                        "reliability": "HIGH" if c["band"] == "HIGH" else "MEDIUM"})
        if c["contradicting"]:
            contra.append({"source": "IDENTITY", "text": f"Identity match with {other} has contradicting records",
                           "evidenceIds": [x["evidenceId"] for x in c["contradicting"][:3] if x.get("evidenceId") and "+" not in str(x["evidenceId"])],
                           "reliability": "MEDIUM"})
    direct_sources = {s["source"] for s in support} - {"IDENTITY"}
    if direct_sources <= {"FIR"} and support:
        contra.append({"source": "ANALYSIS", "text": "Apart from being named in the FIR, no independent record (location, communication, "
                                                      "financial) links this person to the incident", "evidenceIds": [], "reliability": "HIGH"})
    S, C = _weigh(support, SUP_W), _weigh(contra, CON_W)
    balance = (S - C) / (S + C + 0.5)
    present = {x["source"] for x in support + contra} & set(CORE)
    completeness = len(present) / len(CORE)
    label = ("Leans supporting" if balance >= 0.4 else "Leans contradicting" if balance <= -0.4 else "Unresolved")
    if not support:
        uncertainty = "No supporting evidence found in current records"
    elif not contra:
        uncertainty = (f"{len(support)} supporting item(s); no contradicting evidence found in current records "
                       "(absence of contradiction is not confirmation)")
    else:
        uncertainty = f"Mixed: {len(support)} supporting vs {len(contra)} contradicting item(s)"
    # prior criminal records: context only (never scored)
    from ..identity import history
    ctx_hist = history.person_history(pid)
    context = [{"text": f"Prior record ({l['band']} link, {l['status'].lower()}): {l['record']['offence']} "
                        f"{(l['record']['date'] or '')[:4]} — {l['record']['disposition'].lower().replace('_', ' ')}",
                "evidenceIds": [l["record"]["evidenceId"]]} for l in ctx_hist["priorRecords"] if l["band"] in ("HIGH", "MEDIUM")]
    return {"personId": pid, "name": name, "person": person, "supporting": support, "contradicting": contra,
            "requiresClarification": clarify, "uncertainty": uncertainty,
            "confidence": {"supportWeight": round(S, 3), "contradictionWeight": round(C, 3), "evidentialBalance": round(balance, 3),
                           "assessment": label, "completeness": round(completeness, 2),
                           "sourcesPresent": sorted(present), "sourcesMissing": sorted(set(CORE) - present),
                           "note": "Evidential balance compares weighted supporting vs contradicting evidence; it is not a "
                                   "probability of guilt. Prior records are excluded from this score."},
            "context": context}


def _person_hypothesis(case_id: str, pid: str, I: dict, prio: dict) -> dict:
    from . import next_evidence
    a = assess_person(case_id, pid, I)
    pr = next((r for r in prio["ranking"] if r["personId"] == pid), None)
    recs = [r for r in next_evidence.recommend(case_id) if r["personId"] in (pid, None)][:6]
    contra = a["contradicting"] or [{"source": "NONE", "text": "No contradicting evidence was found in the records currently held. "
                                                               "This does not mean none exists.", "evidenceIds": [], "weight": 0}]
    return {
        "hypothesisId": f"HYP-{case_id}-{pid}",
        "hypothesis": f"{a['name']} ({pid}) was involved in the incident recorded in {case_id}",
        "personId": pid,
        "supporting": a["supporting"],
        "contradicting": contra,
        "requiresClarification": a["requiresClarification"],
        "alternativeExplanations": sorted({ALT[s["source"]] for s in a["supporting"] if s["source"] in ALT}),
        "missingRecords": [m["gap"] for m in I["missingInformation"] if m.get("personId") == pid],
        "verificationSteps": [f"[{r['priority']} · value {r['valueScore']}] {r['verificationAction']} ({r['status']})" for r in recs],
        "uncertainty": a["uncertainty"],
        "confidence": a["confidence"],
        "contextPriorRecords": a["context"],
        "investigativePriority": pr["label"] if pr else "Insufficient evidence to rank",
        "humanReviewRequired": True,
    }


def analyse(case_id: str, person_id: str | None = None, top: int = 3) -> dict:
    I = case_intel.get(case_id)
    if not I:
        return {}
    prio = priority.assess(case_id)
    if person_id:
        pids = [person_id]
    else:
        pids = [r["personId"] for r in prio["ranking"] if r["recordedRole"] in ("PRINCIPAL_ACCUSED", "ACCUSED")][:top] or \
               [r["personId"] for r in prio["ranking"][:top]]
    return {"caseId": case_id, "hypotheses": [_person_hypothesis(case_id, p, I, prio) for p in pids],
            "note": "Each hypothesis is tested from both sides to reduce confirmation bias. Confidence scores are evidential "
                    "balance (not probability of guilt). Human review is required."}
