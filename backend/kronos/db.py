"""Thin PostgreSQL access layer (psycopg2 + small connection pool)."""
from __future__ import annotations

import contextlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

import psycopg2
import psycopg2.extras
import psycopg2.pool

from .config import settings

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
psycopg2.extras.register_default_jsonb(loads=json.loads)


def pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 12, settings.database_url)
    return _pool


@contextlib.contextmanager
def conn():
    c = pool().getconn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        pool().putconn(c)


def query(sql: str, params: Sequence | dict | None = None) -> list[dict]:
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()] if cur.description else []


def query_one(sql: str, params=None) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=None) -> int:
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def execute_values(sql: str, rows: Iterable[Sequence], page_size: int = 2000) -> None:
    rows = list(rows)
    if not rows:
        return
    with conn() as c, c.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=page_size)


def clean(o: Any):
    """Recursively replace NaN/inf (pandas missing values) with None so payloads are valid JSON."""
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else o
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [clean(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):     # numpy scalars
        try:
            return clean(o.item())
        except Exception:  # noqa: BLE001
            return str(o)
    return o


def Json(v: Any):
    return psycopg2.extras.Json(clean(v), dumps=lambda o: json.dumps(o, default=str))


def apply_schema() -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text()
    with conn() as c, c.cursor() as cur:
        cur.execute(sql)
