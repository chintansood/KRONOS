"""Next-best-evidence recommendations.

Every recommendation states which evidence gap it would close and is explicitly typed as:
  AVAILABLE                – already in KRONOS and cited
  AVAILABLE_NOT_RETRIEVED  – held in KRONOS (e.g. under another case) but not part of this case file
  TO_BE_OBTAINED           – must be requested from a bank / telecom / platform / registry / CCTV owner
  CANNOT_VERIFY_CURRENTLY  – no current route to verification
A recommendation is never presented as an existing record.

Confidence / value scoring — each recommendation gets an explainable value score in [0, 1]:
  0.30 × uncertainty reduction  (1 − |evidential balance| of the related person's hypothesis: unresolved = most valuable)
+ 0.30 × finding strength       (how strong the finding is that motivates the request)
+ 0.20 × subject priority       (investigative priority of the related person, relative to the case)
+ 0.20 × obtainability          (already held > to be obtained > cannot verify; CCTV older than ~30 days is likely overwritten)
+ 0.15 bonus if the evidence could clear a named person (exculpatory potential)
Priority labels (HIGH / MEDIUM / LOW) are derived from this score.
"""
from __future__ import annotations

import hashlib

import pandas as pd

from ... import db
from ..multimodal import case_intel
from ..store import events


def _id(*parts):
    return "NBE-" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:10].upper()


def recommend(case_id: str) -> list[dict]:
    I = case_intel.get(case_id)
    if not I:
        return []
    o = I["overview"]
    df = events()
    recs = []

    def add(etype, reason, gap, value, priority, action, status, person=None, basis=None):
        rid = _id(case_id, etype, person, gap)
        recs.append({"id": rid, "evidenceType": etype, "caseId": case_id, "personId": person, "reason": reason,
                     "evidenceGap": gap, "expectedInvestigativeValue": value, "priority": priority,
                     "verificationAction": action, "status": status, "basisEvidenceIds": (basis or [])[:6]})

    fin = I["financial"]
    # 1. account ownership for flagged accounts
    flagged_accts = {}
    for f in fin["flagged"]:
        for a in (f["senderAccount"], f["receiverAccount"]):
            if a:
                flagged_accts.setdefault(a, []).append(f["evidenceId"])
    acct_info = {a["account"]: a for a in fin["accounts"]}
    for a, evs in list(flagged_accts.items())[:6]:
        info = acct_info.get(a, {})
        if not info.get("holders") or info.get("sharedHolders"):
            add("Account ownership verification (KYC / account-opening form)",
                f"Account {a} is party to flagged transactions and its holder is " +
                ("not established in records" if not info.get("holders") else f"recorded for multiple persons ({', '.join(info['holders'])})"),
                "beneficial owner of account unknown or ambiguous", "Attributes funds to an identified person; may also clear an account holder",
                "HIGH", f"Request KYC, account-opening documents and linked mobile/email for {a} from the bank", "TO_BE_OBTAINED", basis=evs)
    # 2. bank statements for chains
    if fin["passThroughChains"] or fin["structuring"] or fin["fanIn"]:
        chain_ev = [c["in"] for c in fin["passThroughChains"]] + [e for s in fin["structuring"] for e in s["evidenceIds"]]
        start = (pd.Timestamp(o["incident_ts"]) - pd.Timedelta(days=60)).strftime("%d %b %Y") if o.get("incident_ts") else "case start"
        end = (pd.Timestamp(o["incident_ts"]) + pd.Timedelta(days=60)).strftime("%d %b %Y") if o.get("incident_ts") else "date"
        add("Full bank statements for flagged accounts",
            "Flagged money movement continues beyond the records currently held",
            "onward destination of funds after the last recorded hop", "Establishes the complete money trail and any legitimate source",
            "HIGH", f"Obtain statements from {start} to {end} for accounts in the flagged chain", "TO_BE_OBTAINED", basis=chain_ev)
    # 3. shell / company records
    for org in [x for x in I["organisations"] if x["received"] >= 500000][:3]:
        add("Company registration and director details (MCA / GST)",
            f"{org['name']} ({org['orgId']}) received ₹{org['received']:,.0f} in this case's records",
            "whether the company has genuine business activity and who controls it",
            "Distinguishes a trading firm from a pass-through entity", "MEDIUM",
            f"Request ROC/MCA filings, GST returns and director list for {org['name']}", "TO_BE_OBTAINED")
    # 4. shared devices
    ce = df[df.case_id == case_id]
    for dev, g in ce[ce.device_id.notna()].groupby("device_id"):
        users = sorted(g.person_id.dropna().unique())
        if len(users) > 1:
            add("Device and SIM subscriber records (CAF) / handset seizure",
                f"Handset {dev} appears in records of {', '.join(users)}",
                "who actually used the handset at relevant times", "Prevents attributing a shared device's activity to the wrong person",
                "HIGH", f"Obtain CAF for SIMs used in {dev}; seize/examine handset; record statements on device use",
                "TO_BE_OBTAINED", person=users[0], basis=list(g.evidence_id[:4]))
    # 5. impossible / air travel
    for t in I["travelInconsistencies"][:4]:
        ticket = df[(df.person_id == t["personId"]) & (df.modality == "FINANCIAL")
                    & df.extra.map(lambda x: "air ticket" in ((x or {}).get("purpose") or "").lower())]
        if t["verdict"] == "REQUIRES_AIR_TRAVEL" and not ticket.empty:
            add("Air-travel record (already on file)", "Fast movement between two cities is consistent with a flight",
                "whether the person actually flew", "Explains the location sequence without wrongdoing", "LOW",
                "Cross-check the ticket purchase with airline manifest", "AVAILABLE", person=t["personId"],
                basis=list(ticket.evidence_id[:2]) + [t["first"]["evidenceId"], t["second"]["evidenceId"]])
        else:
            add("Location verification (tower dump / CCTV / independent GPS)",
                f"Location sequence for {t['personId']} is {t['verdict'].replace('_', ' ').lower()} "
                f"({t['distanceKm']} km in {t['elapsedMinutes']} min)",
                "which of the two conflicting records reflects the person's true location",
                "Detects cloned SIM / shared handset / data error; may remove a false lead", "HIGH",
                f"Request tower dump for both cells and handset forensic report for {t['first']['deviceId']}",
                "TO_BE_OBTAINED", person=t["personId"], basis=[t["first"]["evidenceId"], t["second"]["evidenceId"]])
    # 6. CCTV near incident
    if o.get("incident_location") and o.get("incident_ts"):
        it = pd.Timestamp(o["incident_ts"])
        add("CCTV footage", f"No visual record of the incident at {o['incident_location']} is held",
            "independent confirmation of who was present at the incident",
            "Can corroborate or contradict location records of named persons", "HIGH",
            f"Collect CCTV from {o['incident_location']} for {(it - pd.Timedelta(hours=1)):%d %b %Y %H:%M}–{(it + pd.Timedelta(hours=1)):%H:%M} "
            "(check retention period — footage may already be overwritten)", "TO_BE_OBTAINED")
    # 7. authenticated chats
    imp = I["communication"]["importantMessages"]
    if imp:
        add("Authenticated communication records (platform data + BSA s.63 certificate)",
            f"{len(imp)} message(s) referencing accounts/amounts/phones are held only as extracted records",
            "admissible, authenticated copies of the messages", "Makes key messages usable and confirms sender identity", "MEDIUM",
            "Request subscriber + message logs from the platform via legal process; obtain s.63 certificate", "TO_BE_OBTAINED",
            basis=[m["evidenceId"] for m in imp[:5]])
    # 8. missing records for accused
    for m in I["missingInformation"]:
        if not m.get("personId"):
            continue
        other = df[(df.person_id == m["personId"]) & (df.case_id != case_id)]
        if not other.empty and "geolocated" in m["gap"]:
            near = other[(other.ts - pd.Timestamp(o["incident_ts"])).abs() <= pd.Timedelta(hours=6)] if o.get("incident_ts") else other.iloc[0:0]
            if not near.empty:
                add("Records held under another case", f"{m['personId']} has records near the incident time filed under "
                    f"{', '.join(sorted(near.case_id.unique()))}", m["gap"], "May place the person at or away from the incident",
                    "HIGH", "Retrieve and review these records in this case file", "AVAILABLE_NOT_RETRIEVED",
                    person=m["personId"], basis=list(near.evidence_id[:4]))
                continue
        add("Call detail records / location data" if "geolocated" in m["gap"] or "call" in m["gap"] else "Bank records",
            f"Gap for {m['personId']}: {m['gap']}", m["gap"], "Fills the gap needed to test presence/involvement", "MEDIUM",
            f"Requisition records for {m['personId']} covering the incident period", "TO_BE_OBTAINED", person=m["personId"])
    # 9. alibi verification
    for e in I["location"]["namedPersonsElsewhere"][:3]:
        add("Alibi verification", f"{e['personId']} has a {e['modality']} record {e['distanceKm']} km away at the incident time",
            "whether the alibi record is authentic and attributable to the person",
            "Could exculpate a named person — must be verified before conclusions", "HIGH",
            f"Verify {e['evidenceId']} source; seek independent witnesses/CCTV/receipts at {e['location']}", "AVAILABLE",
            person=e["personId"], basis=[e["evidenceId"]])
    # 10. unlinked names
    for u in [x for x in I["uncertainties"] if "could not be linked" in x][:3]:
        add("Identification of a person named in FIR", u, "identity of a named person", "Completes the list of involved persons",
            "MEDIUM", "Record statement of complainant to obtain identifiers (phone, address) for this name", "CANNOT_VERIFY_CURRENTLY")
    # 11. behavioural identity matches (possible identity switch) involving people in this case
    case_people = {p["personId"] for p in I["people"]}
    for c in db.query("SELECT candidate_id, person_a, person_b, score, band, supporting, features FROM identity_candidates "
                      "WHERE band IN ('MEDIUM','HIGH') AND status IN ('PENDING','DEFERRED') AND (person_a = ANY(%s) OR person_b = ANY(%s))",
                      (list(case_people), list(case_people))):
        if (c["features"] or {}).get("basis") == "behavioural":
            mine = c["person_a"] if c["person_a"] in case_people else c["person_b"]
            other = c["person_b"] if mine == c["person_a"] else c["person_a"]
            add("Identity verification for a possible identity switch",
                f"{mine} and {other} share a social circle, routine places and hand over activity in time, but no identifier",
                f"whether {mine} and {other} are the same person", "Links or separates two records without relying on names",
                "HIGH", f"Obtain CAF/KYC for both numbers and accounts, handset purchase records, and compare photographs/fingerprints",
                "TO_BE_OBTAINED", person=mine, basis=[x["evidenceId"] for x in (c["supporting"] or []) if x.get("evidenceId")])
    # 12. prior-record links that are not yet strong enough (context only — never used for suspicion)
    for l in db.query("SELECT l.person_id, l.band, l.history_id, h.evidence_id FROM history_links l JOIN criminal_history h USING (history_id) "
                      "WHERE l.person_id = ANY(%s) AND l.band IN ('MEDIUM','LOW') AND l.status='PENDING'", (list(case_people),)):
        add("Prior-record identity verification (fingerprints via NAFIS / photograph)",
            f"Prior record {l['history_id']} may belong to {l['person_id']} ({l['band']} link)",
            "whether the prior record is this person's — context only, not evidence of the current allegation",
            "Prevents attributing someone else's record to this person", "LOW",
            "Compare fingerprints/photograph with the prior record through NAFIS / CCTNS", "TO_BE_OBTAINED",
            person=l["person_id"], basis=[l["evidence_id"]])
    # investigator overrides of status
    over = {r["request_id"]: r["status"] for r in db.query("SELECT request_id, status FROM evidence_requests WHERE case_id=%s", (case_id,))}
    seen = set()
    out = []
    for r in recs:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        if r["id"] in over:
            r["status"] = over[r["id"]]; r["statusSetByInvestigator"] = True
        out.append(r)
    _score(case_id, I, out)
    return sorted(out, key=lambda r: -r["valueScore"])


STRENGTH = {"Device and SIM subscriber records (CAF) / handset seizure": 0.8, "Company registration and director details (MCA / GST)": 0.6,
            "Air-travel record (already on file)": 0.3, "CCTV footage": 0.7, "Records held under another case": 0.9,
            "Alibi verification": 1.0, "Identification of a person named in FIR": 0.4,
            "Identity verification for a possible identity switch": 0.8,
            "Prior-record identity verification (fingerprints via NAFIS / photograph)": 0.5}
OBTAIN = {"AVAILABLE": 1.0, "AVAILABLE_NOT_RETRIEVED": 1.0, "RECEIVED": 1.0, "REQUESTED": 0.7, "TO_BE_OBTAINED": 0.6,
          "CANNOT_VERIFY_CURRENTLY": 0.2, "DISMISSED": 0.0}
EXCULPATORY = {"Alibi verification", "Air-travel record (already on file)"}


def _score(case_id: str, I: dict, recs: list[dict]) -> None:
    from . import hypothesis, priority as prio_mod
    prio = {r["personId"]: r["priorityScore"] for r in prio_mod.assess(case_id)["ranking"]}
    pmax = max(list(prio.values()) + [1e-9])
    as_of = events().ts.max()
    balance = {}
    for r in recs:
        pid = r["personId"]
        if pid and pid not in balance:
            try:
                balance[pid] = hypothesis.assess_person(case_id, pid, I)["confidence"]["evidentialBalance"]
            except Exception:  # noqa: BLE001
                balance[pid] = 0.0
        et = r["evidenceType"]
        if et in STRENGTH:
            strength = STRENGTH[et]
        elif et.startswith("Location verification"):
            strength = 1.0 if "impossible" in r["reason"].lower() else 0.6
        elif et.startswith("Account ownership"):
            strength = min(1.0, 0.5 + 0.1 * len(r["basisEvidenceIds"]))
        elif et.startswith("Full bank statements"):
            strength = min(1.0, 0.4 + 0.1 * len(r["basisEvidenceIds"]))
        elif et.startswith("Authenticated communication"):
            strength = min(1.0, 0.4 + 0.1 * len(r["basisEvidenceIds"]))
        else:
            strength = 0.6
        unc = 1 - abs(balance.get(pid, 0.4)) if pid else 0.6
        subj = prio.get(pid, 0.5 * pmax) / pmax if pid else 0.5
        obtain = OBTAIN.get(r["status"], 0.6)
        notes = []
        if et == "CCTV footage" and I["overview"].get("incident_ts"):
            age = (as_of - pd.Timestamp(I["overview"]["incident_ts"])).days
            if age > 30:
                obtain = 0.2
                notes.append(f"incident is {age} days before the latest record — CCTV retention (typically 30–90 days) may have lapsed")
        bonus = 0.15 if et in EXCULPATORY else 0.0
        v = min(1.0, 0.30 * unc + 0.30 * strength + 0.20 * subj + 0.20 * obtain + bonus)
        r["valueScore"] = round(v, 3)
        r["priority"] = "HIGH" if v >= 0.62 else "MEDIUM" if v >= 0.45 else "LOW"
        r["scoreBreakdown"] = {"uncertaintyReduction": round(unc, 2), "findingStrength": round(strength, 2),
                               "subjectPriority": round(subj, 2), "obtainability": round(obtain, 2),
                               "exculpatoryBonus": bonus, "notes": notes}


def set_status(case_id: str, request_id: str, status: str) -> dict:
    allowed = {"AVAILABLE", "AVAILABLE_NOT_RETRIEVED", "TO_BE_OBTAINED", "CANNOT_VERIFY_CURRENTLY", "REQUESTED", "RECEIVED", "DISMISSED"}
    if status not in allowed:
        raise ValueError(f"status must be one of {sorted(allowed)}")
    db.execute("INSERT INTO evidence_requests (request_id, case_id, status) VALUES (%s,%s,%s) ON CONFLICT (request_id) "
               "DO UPDATE SET status=EXCLUDED.status, updated_at=now()", (request_id, case_id, status))
    db.execute("INSERT INTO evidence_request_log (request_id, case_id, status, actor) VALUES (%s,%s,%s,%s)",
               (request_id, case_id, status, "investigator"))
    return {"id": request_id, "status": status}
