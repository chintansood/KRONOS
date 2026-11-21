"""Explainable investigative prioritisation.

Ranks people in a case by how much *further investigation* the available records warrant.
It is NOT a guilt score: every factor's contribution is shown, contradicting evidence lowers
the priority, and thin evidence yields 'Insufficient evidence to rank'.
"""
from __future__ import annotations

from ... import db
from ..graph.analytics import metrics
from ..multimodal import case_intel

ROLE_RELEVANCE = {"PRINCIPAL_ACCUSED": 1.0, "ACCUSED": 0.8, "ASSOCIATE": 0.5, "MENTIONED": 0.3, "RECORD_SUBJECT": 0.2,
                  "WITNESS": 0.1, "VICTIM": 0.05, "COMPLAINANT": 0.05}
WEIGHTS = {"directEvidenceRelevance": 0.20, "independentSources": 0.15, "crossSourceCorroboration": 0.10,
           "temporalConsistency": 0.15, "financialAnomalies": 0.15, "communicationRelationships": 0.10,
           "graphRelationshipStrength": 0.05, "identityMatchConfidence": 0.05, "sourceReliability": 0.05}
LABELS = [(0.55, "Highest current investigative priority"), (0.35, "Person requiring further verification"),
          (0.15, "Potentially relevant entity")]


def assess(case_id: str) -> dict:
    I = case_intel.get(case_id)
    if not I:
        return {}
    obs = {o["personId"]: o for o in I["crossSourceObservations"]}
    met = metrics()["nodes"]
    case_btw = [met.get(p["personId"], {}).get("betweenness", 0) for p in I["people"]]
    max_btw = max(case_btw + [1e-9])
    idm = {}
    for r in db.query("SELECT person_a, person_b, score FROM identity_candidates WHERE band IN ('HIGH','MEDIUM') "
                      "AND status <> 'REJECTED'"):
        idm[r["person_a"]] = max(idm.get(r["person_a"], 0), r["score"]); idm[r["person_b"]] = max(idm.get(r["person_b"], 0), r["score"])
    fin = I["financial"]["flagged"]
    comm_pairs = I["communication"]["pairs"]
    accused = {p["personId"] for p in I["people"] if p["primaryRole"] in ("PRINCIPAL_ACCUSED", "ACCUSED")}
    rows = []
    for p in I["people"]:
        pid = p["personId"]
        o = obs.get(pid, {"facts": [], "independentSources": 0})
        srcs = {f["source"] for f in o["facts"] if f["source"] != "LOCATION_CONTRA"}
        near = [x for x in I["location"]["nearIncident"] if x["personId"] == pid]
        far = [x for x in I["location"]["namedPersonsElsewhere"] if x["personId"] == pid]
        ff = [f for f in fin if pid in (f["sender"], f["receiver"])]
        cp = [x for x in comm_pairs if pid in x["persons"] and any(q in accused for q in x["persons"] if q != pid)]
        rel_vals = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.45}
        factors = {
            "directEvidenceRelevance": (ROLE_RELEVANCE.get(p["primaryRole"], 0.2),
                                        f"recorded role: {p['primaryRole'].lower().replace('_', ' ')} ({p['roles'][0]['method']})"),
            "independentSources": (min(1.0, len(srcs) / 3), f"{len(srcs)} independent source type(s): {', '.join(sorted(srcs)) or 'none'}"),
            "crossSourceCorroboration": (1.0 if len(srcs) >= 2 else 0.0, "findings align across ≥2 sources" if len(srcs) >= 2 else "no cross-source alignment"),
            "temporalConsistency": (1.0 if near and not far else 0.0 if not far else -1.0,
                                    "record near incident place/time" if near and not far else
                                    "record far from incident at the time (contradicts presence)" if far else "no location record near the incident time"),
            "financialAnomalies": (min(1.0, len(ff) / 3), f"party to {len(ff)} flagged transaction(s)"),
            "communicationRelationships": (min(1.0, sum(x["total"] for x in cp) / 20),
                                           f"{sum(x['total'] for x in cp)} contacts with recorded accused"),
            "graphRelationshipStrength": (met.get(pid, {}).get("betweenness", 0) / max_btw, "relative betweenness within this case's network"),
            "identityMatchConfidence": (idm.get(pid, 0.0), "possible identity link to another record" if pid in idm else "no identity candidates"),
            "sourceReliability": (sum(rel_vals.get(x.get("reliability", "MEDIUM"), 0.7) for x in near) / len(near) if near else 0.7,
                                  "mean reliability of location evidence" if near else "default (no location evidence)"),
        }
        contrib = {k: round(WEIGHTS[k] * v[0], 3) for k, v in factors.items()}
        score = max(0.0, sum(contrib.values()))
        evidence_n = len([e for f in o["facts"] for e in f["evidenceIds"]]) + len(p["evidenceIds"])
        label = next((l for t, l in LABELS if score >= t), "Insufficient evidence to rank")
        if evidence_n < 2:
            label = "Insufficient evidence to rank"
        if far and label == "Highest current investigative priority":
            label = "Person requiring further verification"
        rows.append({"personId": pid, "name": p["name"], "recordedRole": p["primaryRole"], "priorityScore": round(score, 3),
                     "label": label,
                     "factors": [{"factor": k, "value": round(v[0], 3), "weight": WEIGHTS[k], "contribution": contrib[k],
                                  "explanation": v[1]} for k, v in factors.items()],
                     "contradictingEvidence": [x["evidenceId"] for x in far],
                     "supportingEvidence": sorted({e for f in o["facts"] if f["source"] != "LOCATION_CONTRA" for e in f["evidenceIds"]})[:10]})
    rows.sort(key=lambda r: -r["priorityScore"])
    return {"caseId": case_id, "ranking": rows, "weights": WEIGHTS,
            "disclaimer": "An investigative priority ranking indicates where verification effort may be useful. "
                          "It is not a finding or probability of guilt."}
