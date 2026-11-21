"""Impossible-travel detection (Haversine).

For consecutive geolocated records of one person:
    distance = 2R·asin(√(sin²(Δφ/2) + cos φ1·cos φ2·sin²(Δλ/2)))   (R = 6371.0088 km, radians)
    implied_speed = distance / elapsed_time
Location uncertainty is respected: the distance used for the speed test is reduced by the
two records' stated accuracy radii (cell-tower fixes can be off by kilometres), so tower
handovers do not produce false alarms. Findings are *inconsistencies to verify* — e.g.
shared handset, cloned SIM, data-entry error, or genuine air travel — never proof of
movement or wrongdoing.
"""
from __future__ import annotations

import math

import pandas as pd

from ...config import settings
from ..store import events

R_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R_KM * math.asin(math.sqrt(min(1.0, h)))


def detect_for_frame(df: pd.DataFrame, person_id: str, max_ground=None, max_air=None, min_km=None) -> list[dict]:
    max_ground = max_ground or settings.travel_max_ground_kmh
    max_air = max_air or settings.travel_max_air_kmh
    min_km = settings.travel_min_distance_km if min_km is None else min_km
    pts = df[(df.person_id == person_id) & df.latitude.notna() & df.longitude.notna() & df.ts.notna()
             & df.modality.isin(["LOCATION", "CDR", "SOCIAL", "FINANCIAL"])]
    pts = pts[(pts.latitude.between(-90, 90)) & (pts.longitude.between(-180, 180))].sort_values("ts")
    out = []
    prev = None
    for _, r in pts.iterrows():
        if prev is not None:
            dt_h = (r.ts - prev.ts).total_seconds() / 3600
            d = haversine_km(prev.latitude, prev.longitude, r.latitude, r.longitude)
            unc_km = ((prev.accuracy_m or settings.travel_default_accuracy_m) +
                      (r.accuracy_m or settings.travel_default_accuracy_m)) / 1000
            eff = max(0.0, d - unc_km)
            if eff >= min_km:
                if dt_h <= 0:
                    speed, verdict = float("inf"), "SIMULTANEOUS_DIFFERENT_PLACES"
                else:
                    speed = eff / dt_h
                    verdict = ("IMPOSSIBLE" if speed > max_air else
                               "REQUIRES_AIR_TRAVEL" if speed > max_ground else None)
                if verdict:
                    out.append({
                        "personId": person_id,
                        "verdict": verdict,
                        "first": {"evidenceId": prev.evidence_id, "sourceRecordId": prev.source_record_id,
                                  "caseId": prev.case_id, "modality": prev.modality,
                                  "timestamp": prev.ts.strftime("%Y-%m-%d %H:%M:%S"), "location": prev.location_name,
                                  "lat": prev.latitude, "lon": prev.longitude, "accuracyM": prev.accuracy_m,
                                  "deviceId": prev.device_id},
                        "second": {"evidenceId": r.evidence_id, "sourceRecordId": r.source_record_id,
                                   "caseId": r.case_id, "modality": r.modality,
                                   "timestamp": r.ts.strftime("%Y-%m-%d %H:%M:%S"), "location": r.location_name,
                                   "lat": r.latitude, "lon": r.longitude, "accuracyM": r.accuracy_m,
                                   "deviceId": r.device_id},
                        "distanceKm": round(d, 2), "uncertaintyKm": round(unc_km, 2),
                        "effectiveDistanceKm": round(eff, 2), "elapsedMinutes": round(dt_h * 60, 1),
                        "impliedSpeedKmh": None if math.isinf(speed) else round(speed, 1),
                        "thresholds": {"maxGroundKmh": max_ground, "maxAirKmh": max_air, "minDistanceKm": min_km},
                        "interpretation": {
                            "IMPOSSIBLE": "Faster than commercial air travel. Possible explanations: shared or cloned "
                                          "device/SIM, record attributed to the wrong person, or data error.",
                            "REQUIRES_AIR_TRAVEL": "Not achievable by road; plausible only with a flight. Check for "
                                                   "tickets/airport records before treating as inconsistent.",
                            "SIMULTANEOUS_DIFFERENT_PLACES": "Two records at the same instant in different places — "
                                                             "strongly suggests two different users or a data error.",
                        }[verdict],
                    })
        prev = r
    return out


def detect(person_id: str, **kw) -> list[dict]:
    return detect_for_frame(events(), person_id, **kw)


def detect_all(**kw) -> list[dict]:
    df = events()
    out = []
    for pid in df.person_id.dropna().unique():
        out += detect_for_frame(df, pid, **kw)
    return out


def feasibility(person_id: str, **kw) -> dict:
    """Travel-feasibility results for every consecutive pair of geolocated records of a person."""
    df = events()
    pts = df[(df.person_id == person_id) & df.latitude.notna() & df.longitude.notna() & df.ts.notna()
             & df.modality.isin(["LOCATION", "CDR", "SOCIAL", "FINANCIAL"])]
    pts = pts[(pts.latitude.between(-90, 90)) & (pts.longitude.between(-180, 180))]
    flags = detect_for_frame(df, person_id, **kw)
    by = {}
    for f in flags:
        by[f["verdict"]] = by.get(f["verdict"], 0) + 1
    n_pairs = max(0, len(pts) - 1)
    return {"personId": person_id, "pairsChecked": n_pairs, "plausible": n_pairs - len(flags),
            "requiresAirTravel": by.get("REQUIRES_AIR_TRAVEL", 0), "impossible": by.get("IMPOSSIBLE", 0),
            "simultaneousDifferentPlaces": by.get("SIMULTANEOUS_DIFFERENT_PLACES", 0), "flags": flags,
            "thresholds": {"maxGroundKmh": kw.get("max_ground") or settings.travel_max_ground_kmh,
                           "maxAirKmh": kw.get("max_air") or settings.travel_max_air_kmh,
                           "minDistanceKm": settings.travel_min_distance_km},
            "method": "Haversine distance minus both records' accuracy radii, divided by elapsed time."}
