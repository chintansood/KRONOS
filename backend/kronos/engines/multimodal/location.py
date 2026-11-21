"""Location analysis for a case: frequent places, presence near the incident, shared places
across cases, co-presence of case persons. Location accuracy is always reported."""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from ..store import events
from ..temporal import travel
from ..temporal.timeline import colocations


def analyse_case(case_id: str, incident_ts=None, inc_lat=None, inc_lon=None, named: set | None = None,
                 radius_km: float = 1.0, window_h: float = 2.0) -> dict:
    df = events()
    L = df[(df.case_id == case_id) & df.latitude.notna() & df.ts.notna()
           & df.modality.isin(["LOCATION", "CDR", "SOCIAL", "FINANCIAL"]) & df.person_id.notna()]
    freq = []
    for pid, g in L[L.modality == "LOCATION"].groupby("person_id"):
        top = g.location_name.value_counts().head(3)
        freq.append({"personId": pid, "records": int(len(g)),
                     "topPlaces": [{"place": k, "records": int(v)} for k, v in top.items()]})
    near = []
    if incident_ts is not None and inc_lat is not None:
        inc = pd.Timestamp(incident_ts)
        w = L[(L.ts >= inc - pd.Timedelta(hours=window_h)) & (L.ts <= inc + pd.Timedelta(hours=window_h))]
        for r in w.itertuples():
            d = travel.haversine_km(inc_lat, inc_lon, r.latitude, r.longitude)
            unc = (r.accuracy_m or 1500) / 1000
            if d - unc <= radius_km:
                near.append({"personId": r.person_id, "evidenceId": r.evidence_id, "modality": r.modality,
                             "timestamp": r.ts.strftime("%Y-%m-%d %H:%M"), "distanceKm": round(d, 2),
                             "accuracyM": r.accuracy_m, "location": r.location_name, "namedInFIR": r.person_id in (named or set()),
                             "minutesFromIncident": round((r.ts - inc).total_seconds() / 60)})
        # where were FIR-named persons NOT near the incident? (possible exculpatory evidence)
    elsewhere = []
    if incident_ts is not None and named:
        inc = pd.Timestamp(incident_ts)
        w = L[(L.ts >= inc - pd.Timedelta(hours=3)) & (L.ts <= inc + pd.Timedelta(hours=3)) & L.person_id.isin(named)]
        for r in w.itertuples():
            d = travel.haversine_km(inc_lat, inc_lon, r.latitude, r.longitude) if inc_lat is not None else None
            if d is not None and d - (r.accuracy_m or 1500) / 1000 > 15:
                elapsed = abs((r.ts - inc).total_seconds()) / 3600
                elsewhere.append({"personId": r.person_id, "evidenceId": r.evidence_id, "modality": r.modality,
                                  "timestamp": r.ts.strftime("%Y-%m-%d %H:%M"), "location": r.location_name,
                                  "distanceKm": round(d, 1), "minutesFromIncident": round((r.ts - inc).total_seconds() / 60),
                                  "reachableByRoad": d / max(elapsed, 0.01) <= 80,
                                  "reliability": r.source_reliability, "accuracyM": r.accuracy_m})
    # places that also appear in other cases
    allL = df[(df.modality == "LOCATION") & df.location_name.notna()]
    place_cases = allL.groupby("location_name").case_id.unique()
    shared = []
    for place in L.location_name.dropna().unique():
        cs = sorted(set(place_cases.get(place, [])) - {case_id})
        if cs:
            shared.append({"place": place, "otherCases": cs[:10], "otherCaseCount": len(cs)})
    shared.sort(key=lambda x: -x["otherCaseCount"])
    co = [c for c in colocations() if case_id in c["caseIds"]]
    return {"frequentPlaces": freq, "nearIncident": near, "namedPersonsElsewhere": elsewhere,
            "sharedPlacesAcrossCases": shared[:15], "coPresence": co[:30],
            "parameters": {"radiusKm": radius_km, "windowHours": window_h},
            "note": "Distances account for record accuracy; cell-tower positions can be off by several km."}
