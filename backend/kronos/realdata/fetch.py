"""Fetch criminal-petition orders from the Indian High Court Judgments open dataset (AWS Open Data Registry).

* Licence: CC-BY-4.0 (dataset by Dattam Labs, documents sourced from the eCourts portal). Attribution is kept with
  every record. Orders of Indian courts are public documents.
* Metadata is read column-wise from the public parquet files (anonymous S3 — no account, no key).
* PDFs are downloaded over HTTPS from the public bucket — at most one request per second, cached on disk, never
  re-downloaded — with a generic User-Agent (no personal or project information is sent).
* Every downloaded document is hashed (SHA-256); hash, URL, licence and retrieval time are kept as provenance.
"""
from __future__ import annotations

import hashlib
import io
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BUCKET = "indian-high-court-judgments"
HTTPS = f"https://{BUCKET}.s3.amazonaws.com/"
LICENSE = "CC-BY-4.0 · Indian High Court Judgments open dataset (Dattam Labs), documents from eCourts"
DATASET_URL = "https://registry.opendata.aws/indian-high-court-judgments/"
COURTS = {"3_22": ("High Court of Punjab and Haryana", "phhc"), "7_26": ("High Court of Delhi", "dhcdb")}
UA = "public-records-research-fetcher/1.0"
_last = [0.0]


def metadata(year: int, court: str = "3_22", columns=("title", "description", "pdf_link", "cnr", "decision_date",
                                                         "disposal_nature", "date_of_registration")):
    import pyarrow.fs as pafs
    import pyarrow.parquet as pq
    bench = COURTS[court][1]
    s3 = pafs.S3FileSystem(anonymous=True, region="ap-south-1")
    path = f"{BUCKET}/metadata/parquet/year={year}/court={court}/bench={bench}/metadata.parquet"
    df = pq.read_table(s3.open_input_file(path), columns=list(columns)).to_pandas()
    df["year"], df["court_code"] = year, court
    return df


def pdf_url(row) -> str:
    bench = COURTS[row["court_code"]][1]
    return f"{HTTPS}data/pdf/year={row['year']}/court={row['court_code']}/bench={bench}/{Path(row['pdf_link']).name}"


def fetch(url: str, cache_dir: Path, client: httpx.Client | None = None) -> dict:
    """Download once (≤1 request/s), cache, hash."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / Path(url).name
    meta = f.with_suffix(".fetched")
    if f.exists() and meta.exists():
        data = f.read_bytes()
        return {"bytes": data, "sha256": hashlib.sha256(data).hexdigest(), "fetchedAt": meta.read_text().strip(),
                "url": url, "cached": True}
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    c = client or httpx.Client(headers={"User-Agent": UA}, timeout=30)
    r = c.get(url)
    _last[0] = time.time()
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return {"bytes": None, "status": r.status_code, "url": url}
    fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
    f.write_bytes(r.content)
    meta.write_text(fetched)
    return {"bytes": r.content, "sha256": hashlib.sha256(r.content).hexdigest(), "fetchedAt": fetched, "url": url, "cached": False}


def text_of(pdf: bytes) -> tuple[str, int, bool]:
    """Text layer of a PDF. Orders typeset with fonts lacking a Unicode map come out as symbols: those are flagged
    unreadable (they would need OCR) instead of being guessed at."""
    from pypdf import PdfReader
    rd = PdfReader(io.BytesIO(pdf))
    txt = "\n".join((p.extract_text() or "") for p in rd.pages)
    txt = re.sub(r"[ \t ]+", " ", txt)
    nonspace = re.sub(r"\s", "", txt)
    letters = sum(ch.isascii() and ch.isalpha() for ch in nonspace)
    words = re.findall(r"[a-z]+", txt.lower())
    common = sum(w in {"the", "of", "and", "to", "in", "is", "that", "petitioner", "fir", "court", "under"} for w in words)
    readable = len(nonspace) > 400 and letters / max(1, len(nonspace)) > 0.72 and common / max(1, len(words)) > 0.12
    return txt, len(rd.pages), readable
