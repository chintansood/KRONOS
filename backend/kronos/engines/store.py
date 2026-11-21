"""In-memory analytical view of the events table (pandas), refreshed when data changes."""
from __future__ import annotations

import threading

import pandas as pd

from .. import db

_lock = threading.Lock()
_cache: dict = {"version": None, "df": None}


def data_version() -> str:
    r = db.query_one("SELECT count(*) n, max(run_id) run FROM raw_records")
    c = db.query_one("SELECT count(*) n, max(updated_at) u FROM cases")
    return f"{r['run']}:{r['n']}:{c['n']}:{c['u']}"


def events() -> pd.DataFrame:
    v = data_version()
    with _lock:
        if _cache["version"] != v:
            df = pd.DataFrame(db.query("SELECT * FROM events"))
            df["ts"] = pd.to_datetime(df["ts"])
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
            df = df.sort_values("ts", na_position="last").reset_index(drop=True)
            _cache.update(version=v, df=df)
        return _cache["df"]


def person_events(pid: str) -> pd.DataFrame:
    df = events()
    return df[(df.person_id == pid) | (df.entity_id_2 == pid)]


def case_events(cid: str) -> pd.DataFrame:
    df = events()
    return df[df.case_id == cid]


def cached(key: str, fn, version: str | None = None):
    """Persisted analysis cache keyed by data version (survives API restarts)."""
    version = version or data_version()
    r = db.query_one("SELECT payload FROM analysis_cache WHERE cache_key=%s AND data_version=%s", (key, version))
    if r:
        return r["payload"]
    val = fn()
    db.execute("INSERT INTO analysis_cache (cache_key, data_version, payload) VALUES (%s,%s,%s) "
               "ON CONFLICT (cache_key) DO UPDATE SET data_version=EXCLUDED.data_version, payload=EXCLUDED.payload, "
               "computed_at=now()", (key, version, db.Json(val)))
    return val


def ev_ref(row) -> dict:
    """Compact, citation-ready reference to one evidence record."""
    return {"evidenceId": row["evidence_id"], "sourceRecordId": row["source_record_id"], "caseId": row["case_id"],
            "modality": row["modality"], "timestamp": None if pd.isna(row["ts"]) else row["ts"].strftime("%Y-%m-%d %H:%M"),
            "reliability": row["source_reliability"]}
