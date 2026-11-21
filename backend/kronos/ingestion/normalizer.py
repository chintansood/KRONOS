"""Identifier normalisation. Normalised values are used for matching/analytics only;
originals are preserved untouched in raw_records."""
from __future__ import annotations

import re

_DIGITS = re.compile(r"\D+")


def phone(v: str | None) -> str | None:
    if not v:
        return None
    d = _DIGITS.sub("", str(v))
    if len(d) < 10:
        return None
    return f"+91-{d[-10:]}"


def account(v: str | None) -> str | None:
    if not v:
        return None
    s = str(v).strip().upper().replace(" ", "")
    return s or None


def ident(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def to_float(v, lo=None, hi=None):
    """Returns (value|None, ok). Empty -> (None, True)."""
    if v is None or str(v).strip() == "":
        return None, True
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None, False
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        return None, False
    return x, True


def to_int(v):
    x, ok = to_float(v)
    return (int(x) if x is not None else None), ok


RELIABILITY = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.45}


def reliability(v: str | None) -> tuple[str, float]:
    r = (v or "").strip().upper()
    if r not in RELIABILITY:
        r = "MEDIUM"
    return r, RELIABILITY[r]
