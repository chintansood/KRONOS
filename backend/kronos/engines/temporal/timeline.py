"""Temporal Network Engine — person-centred chronology.

* person timeline across FIR / CDR / location / financial / social records
* daily routine view with explicit data gaps (no invented activity)
* communication bursts and co-location (possible meetings) detection
"""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from ... import db
from ...config import settings
from ..multimodal import financial
from ..store import cached, events
from . import travel

MOD_UI = {"FIR": "FIR", "CDR": "CDR", "LOCATION": "LOCATION", "FINANCIAL": "FINANCIAL", "SOCIAL": "COMMUNICATION"}
ROLE_LABEL = {"PRINCIPAL_ACCUSED": "principal accused", "ACCUSED": "accused", "COMPLAINANT": "complainant",
              "VICTIM": "victim", "WITNESS": "witness", "ASSOCIATE": "associate", "MENTIONED": "mentioned person"}


def _fmt(ts):
    return {"timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "dateStr": ts.strftime("%d %b %Y"),
            "monthStr": ts.strftime("%b").upper(), "timeStr": ts.strftime("%H:%M")}


def person_fir_roles(pid: str) -> dict[str, list]:
    out = defaultdict(list)
    for r in db.query("SELECT source_record_id, role, method, confidence FROM person_case_roles "
                      "WHERE person_id=%s AND source_record_id IS NOT NULL", (pid,)):
        out[r["source_record_id"]].append(r)
    return out


# ------------------------------------------------------------------ bursts & co-location
def bursts(window_h: float = 3.0, min_events: int = 4) -> list[dict]:
    def compute():
        df = events()
        c = df[df.modality.isin(["CDR", "SOCIAL"]) & df.ts.notna() & df.person_id.notna() & df.entity_id_2.notna()].copy()
        c["a"] = c[["person_id", "entity_id_2"]].min(axis=1)
        c["b"] = c[["person_id", "entity_id_2"]].max(axis=1)
        out = []
        for (a, b), g in c.groupby(["a", "b"]):
            if len(g) < min_events:
                continue
            g = g.sort_values("ts")
            ts = g.ts.tolist()
            i = 0
            while i < len(ts):
                j = i
                while j + 1 < len(ts) and ts[j + 1] - ts[i] <= pd.Timedelta(hours=window_h):
                    j += 1
                if j - i + 1 >= min_events:
                    w = g.iloc[i:j + 1]
                    baseline = len(g) / max(1.0, (g.ts.max() - g.ts.min()).total_seconds() / 86400)
                    out.append({"persons": [a, b], "start": ts[i].strftime("%Y-%m-%d %H:%M"),
                                "end": ts[j].strftime("%Y-%m-%d %H:%M"), "count": int(j - i + 1),
                                "pairDailyBaseline": round(baseline, 2), "caseIds": sorted(set(w.case_id)),
                                "evidenceIds": list(w.evidence_id)})
                    i = j + 1
                else:
                    i += 1
        return out
    return cached(f"bursts:{window_h}:{min_events}", compute)


def colocations(radius_m: float = 300, window_min: int = 30) -> list[dict]:
    def compute():
        df = events()
        L = df[(df.modality == "LOCATION") & df.ts.notna() & df.latitude.notna() & df.person_id.notna()
               & (df.accuracy_m.fillna(9999) <= 200)].copy()
        L["cell"] = list(zip((L.latitude / 0.005).round().astype(int), (L.longitude / 0.005).round().astype(int)))
        L["tb"] = (L.ts.astype("int64") // (window_min * 60 * 10**9)).astype(int)
        popularity = L.groupby("location_name").person_id.nunique().to_dict()
        comm = df[df.modality.isin(["CDR", "SOCIAL"]) & df.entity_id_2.notna()]
        talk = defaultdict(list)
        for a, b, t in zip(comm.person_id, comm.entity_id_2, comm.ts):
            talk[frozenset((a, b))].append(t)
        R = list(zip(L.person_id, L.ts, L.latitude, L.longitude, L.location_name, L.case_id, L.evidence_id))
        idx = defaultdict(list)
        for k, (cell, tb) in enumerate(zip(L.cell, L.tb)):
            idx[(cell, tb)].append(k)
        seen, out = set(), []
        for (cell, tb), ids in idx.items():
            near = [j for dc in (-1, 0, 1) for dd in (-1, 0, 1) for dt in (-1, 0, 1)
                    for j in idx.get(((cell[0] + dc, cell[1] + dd), tb + dt), ())]
            for i in ids:
                pa, ta, la, oa, na, ca, ea = R[i]
                for j in near:
                    pb, tb_, lb, ob, nb, cb, eb = R[j]
                    if pa >= pb or abs((ta - tb_).total_seconds()) > window_min * 60:
                        continue
                    d = travel.haversine_km(la, oa, lb, ob) * 1000
                    if d > radius_m:
                        continue
                    key = (pa, pb, ta.floor("6h"))
                    if key in seen:
                        continue
                    seen.add(key)
                    comms = [t for t in talk.get(frozenset((pa, pb)), []) if abs((t - ta).total_seconds()) <= 48 * 3600]
                    pop = popularity.get(na, 0)
                    out.append({"persons": [pa, pb], "timestamp": ta.strftime("%Y-%m-%d %H:%M"),
                                "location": na, "distanceM": round(d), "placePopularity": int(pop),
                                "communicationsWithin48h": len(comms), "caseIds": sorted({ca, cb}),
                                "evidenceIds": [ea, eb],
                                "assessment": ("co-presence corroborated by communication between the two"
                                               if comms else
                                               "co-presence at a frequently visited place — weak signal"
                                               if pop >= 8 else "co-presence without other corroboration")})
        return out
    return cached(f"coloc:{radius_m}:{window_min}", compute)


# ------------------------------------------------------------------ timeline
def timeline(pid: str, case_id=None, start=None, end=None, modality=None, limit: int | None = 600) -> list[dict]:
    df = events()
    sel = df[((df.person_id == pid) | (df.entity_id_2 == pid)) & (df.modality != "FIR")]
    roles = person_fir_roles(pid)
    fir = df[(df.modality == "FIR") & df.source_record_id.isin(list(roles))]
    sel = pd.concat([sel, fir])
    if case_id:
        sel = sel[sel.case_id == case_id]
    if start:
        sel = sel[sel.ts >= pd.Timestamp(start)]
    if end:
        sel = sel[sel.ts <= pd.Timestamp(end) + pd.Timedelta(days=1)]
    sel = sel[sel.ts.notna()].sort_values("ts")
    fin_flags = financial.flagged_ids()
    trav = {}
    for f in travel.detect(pid):
        trav[f["second"]["evidenceId"]] = f
    burst_ids = {e: b for b in bursts() if pid in b["persons"] for e in b["evidenceIds"]}
    coloc_ids = {}
    for c in colocations():
        if pid in c["persons"] and c["communicationsWithin48h"] > 0:
            for e in c["evidenceIds"]:
                coloc_ids[e] = c
    names = {r["person_id"]: r["display_name"] for r in db.query("SELECT person_id, display_name FROM persons")}
    out = []
    for _, r in sel.iterrows():
        x = r.extra or {}
        ev = {"id": r.event_id, **_fmt(r.ts), "modality": MOD_UI.get(r.modality, r.modality), "caseId": r.case_id,
              "evidenceId": r.evidence_id, "sourceRecordId": r.source_record_id, "reliability": r.source_reliability,
              "severity": "NORMAL", "isAnomaly": False}
        if pd.notna(r.latitude):
            ev.update(latitude=float(r.latitude), longitude=float(r.longitude))
        if r.location_name and isinstance(r.location_name, str):
            ev["locationName"] = r.location_name
        if r.device_id and isinstance(r.device_id, str):
            ev["deviceOrHardwareId"] = r.device_id
        outgoing = r.person_id == pid
        other = r.entity_id_2 if outgoing else r.entity_id_1
        if isinstance(other, str) and other:
            ev["counterpartyId"] = other
        oname = names.get(other, other) if isinstance(other, str) else None
        m = r.modality
        if m == "FIR":
            rl = ", ".join(ROLE_LABEL.get(x["role"], x["role"].lower()) for x in roles.get(r.source_record_id, []))
            ev["title"] = f"Named in {x.get('record_type', 'FIR').replace('_', ' ').lower()} as {rl}"
            ev["description"] = (f"{x.get('fir_number')} — {x.get('offence_category')} at {x.get('police_station')}. "
                                 f"Incident recorded at {r.location_name} on {(x.get('incident_ts') or '')[:16].replace('T', ' ')}. "
                                 "Recorded role only; not a finding of guilt.")
            ev.pop("latitude", None); ev.pop("longitude", None)
        elif m == "CDR":
            kind = "SMS" if r.event_type == "SMS" else "Call"
            ev["title"] = f"{kind} {'to' if outgoing else 'from'} {oname}"
            ev["description"] = r.event_description
        elif m == "SOCIAL":
            ev["title"] = f"{x.get('platform')} message {'to' if outgoing else 'from'} {oname}"
            ev["description"] = f"\"{r.text_content}\""
        elif m == "FINANCIAL":
            amt = float(r.amount) if pd.notna(r.amount) else None
            ev["amount"] = amt
            if outgoing:
                ev["title"] = f"Sent ₹{amt:,.0f} to {x.get('receiver_name')}" if amt else "Outgoing transaction"
            else:
                ev["title"] = f"Received ₹{amt:,.0f} from {x.get('sender_name')}" if amt else "Incoming transaction"
            ev["description"] = r.event_description
        else:
            ev["title"] = f"Recorded at {r.location_name}"
            ev["description"] = r.event_description
        if r.evidence_id in trav:
            f = trav[r.evidence_id]
            ev.update(isAnomaly=True, anomalyType="IMPOSSIBLE_TRAVEL",
                      severity="CRITICAL" if f["verdict"] == "IMPOSSIBLE" else "SUSPICIOUS")
            ev["description"] += (f" ⚠ {f['effectiveDistanceKm']} km from previous record ({f['first']['evidenceId']}) "
                                  f"in {f['elapsedMinutes']} min — {f['verdict'].replace('_', ' ').lower()}; verify.")
        elif r.evidence_id in fin_flags:
            f = fin_flags[r.evidence_id]
            ev.update(isAnomaly=True, anomalyType="FINANCIAL_SURGE", severity="SUSPICIOUS")
            ev["description"] += " ⚠ Flagged: " + "; ".join(f["reasons"][:2])
        elif r.evidence_id in burst_ids:
            b = burst_ids[r.evidence_id]
            ev.update(isAnomaly=True, anomalyType="BURST", severity="SUSPICIOUS")
            ev["description"] += f" ⚠ Part of a burst of {b['count']} contacts within 3 h ({b['start']}–{b['end'][-5:]})."
        elif r.evidence_id in coloc_ids:
            c = coloc_ids[r.evidence_id]
            peer = [p for p in c["persons"] if p != pid][0]
            ev.update(isAnomaly=True, anomalyType="RENDEZVOUS", severity="SUSPICIOUS")
            ev["description"] += f" ⚠ Co-located with {peer} ({c['distanceM']} m), who was also in contact within 48 h."
        if modality and ev["modality"] != modality:
            continue
        out.append(ev)
    # derived cross-case markers: first record of this person in each additional case (clearly labelled)
    seen = []
    for ev in list(out):
        if ev["caseId"] not in seen:
            seen.append(ev["caseId"])
            if len(seen) > 1 and (not modality or modality == "CROSS_CASE"):
                out.append({**ev, "id": f"XC-{pid}-{ev['caseId']}", "modality": "CROSS_CASE",
                            "title": f"First recorded appearance in {ev['caseId']}",
                            "description": f"Derived marker: earliest record of {pid} in {ev['caseId']} "
                                           f"(previous cases: {', '.join(seen[:-1])}). Based on {ev['evidenceId']}.",
                            "isAnomaly": False, "severity": "NORMAL", "anomalyType": None})
    out.sort(key=lambda e: (e["timestamp"], e["modality"] != "CROSS_CASE"))
    if limit and len(out) > limit:
        # keep every flagged/FIR/cross-case event, thin routine pings proportionally
        keep = [e for e in out if e["isAnomaly"] or e["modality"] in ("FIR", "CROSS_CASE", "FINANCIAL")]
        rest = [e for e in out if e not in keep]
        step = max(1, len(rest) // max(1, limit - len(keep)))
        out = sorted(keep + rest[::step], key=lambda e: e["timestamp"])
    return out


def routine(pid: str, date: str | None = None) -> dict:
    df = events()
    sel = df[((df.person_id == pid) | (df.entity_id_2 == pid)) & df.ts.notna() & (df.modality != "FIR")]
    days = sel.ts.dt.date.value_counts()
    if date is None:
        if days.empty:
            return {"personId": pid, "date": None, "entries": [], "gaps": [], "coverage": "no dated records"}
        date = str(days.idxmax())
    d = pd.Timestamp(date)
    day = sel[(sel.ts >= d) & (sel.ts < d + pd.Timedelta(days=1))].sort_values("ts")
    entries, gaps, prev = [], [], None
    for _, r in day.iterrows():
        if prev is not None and (r.ts - prev).total_seconds() / 3600 >= settings.routine_gap_hours:
            gaps.append({"from": prev.strftime("%H:%M"), "to": r.ts.strftime("%H:%M"),
                         "hours": round((r.ts - prev).total_seconds() / 3600, 1)})
            entries.append({"time": prev.strftime("%H:%M") + "–" + r.ts.strftime("%H:%M"), "kind": "GAP",
                            "text": "No records in this period (activity unknown — not absence of activity)"})
        verb = {"LOCATION": f"Recorded location: {r.location_name}", "CDR": "Call/SMS record",
                "SOCIAL": "Message record", "FINANCIAL": f"Financial transaction ₹{r.amount:,.0f}" if pd.notna(r.amount) else "Financial transaction"}[r.modality]
        entries.append({"time": r.ts.strftime("%H:%M"), "kind": r.modality, "text": verb,
                        "evidenceId": r.evidence_id, "caseId": r.case_id, "location": r.location_name})
        prev = r.ts
    return {"personId": pid, "date": str(d.date()), "recordCount": int(len(day)), "entries": entries, "gaps": gaps,
            "availableDates": [str(x) for x in sorted(days.index)][-60:],
            "coverage": (f"{len(day)} records on this date. This is a partial reconstruction from available records "
                         "only; periods without records are shown as gaps, not as inactivity.")}
