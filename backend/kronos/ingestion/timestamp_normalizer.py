"""Normalise heterogeneous source timestamps to naive IST datetimes.

Returns (datetime | None, quality) where quality is one of
EXACT | DATE_ONLY | MISSING | INVALID. Original strings are never modified (they stay
in raw_records)."""
from __future__ import annotations

from datetime import datetime

FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
]
DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]


def parse(value: str | None, time_value: str | None = None) -> tuple[datetime | None, str]:
    if value is None or str(value).strip() == "":
        return None, "MISSING"
    v = str(value).strip()
    if time_value:
        v = f"{v} {str(time_value).strip()}"
    for f in FORMATS:
        try:
            return datetime.strptime(v, f), "EXACT"
        except ValueError:
            pass
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(v, f), "DATE_ONLY"
        except ValueError:
            pass
    return None, "INVALID"
