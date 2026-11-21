"""Shared loader machinery: read CSV -> validate -> (raw record, normalised event, issues)."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import normalizer as N
from .schema_validator import Issue, SourceSchema


def canonical_hash(raw: dict) -> str:
    """SHA-256 over a canonical JSON serialisation of the original row."""
    return hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@dataclass
class LoadResult:
    modality: str
    file_name: str
    raw: list = field(default_factory=list)       # (source_record_id, case_id, row_number, raw dict, sha, quarantined)
    events: list = field(default_factory=list)    # normalised event dicts
    issues: list = field(default_factory=list)    # (row_number, source_record_id, Issue)
    stats: dict = field(default_factory=dict)


class BaseLoader:
    schema: SourceSchema
    file_name: str

    def to_event(self, row: dict) -> tuple[dict | None, list[Issue]]:
        raise NotImplementedError

    # helpers -------------------------------------------------------------
    @staticmethod
    def coord(row, lat_key, lon_key, issues):
        lat, ok1 = N.to_float(row.get(lat_key), -90, 90)
        lon, ok2 = N.to_float(row.get(lon_key), -180, 180)
        if not (ok1 and ok2):
            issues.append(Issue("WARNING", f"{lat_key}/{lon_key}", "invalid coordinate; set to NULL",
                                f"{row.get(lat_key)},{row.get(lon_key)}"))
            return None, None
        return lat, lon

    def base_event(self, row, modality):
        rel, conf = N.reliability(row.get("source_reliability"))
        return dict(
            event_id=f"EVT-{row['source_record_id'].replace('SRC-', '')}",
            source_record_id=row["source_record_id"], evidence_id=row["evidence_id"], case_id=row["case_id"].strip(),
            modality=modality, source_reliability=rel, confidence=conf, extra={},
        )

    def load(self, directory: Path) -> LoadResult:
        path = Path(directory) / self.file_name
        res = LoadResult(self.schema.modality, self.file_name)
        if not path.exists():
            res.stats = {"file_missing": True}
            return res
        seen = set()
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            missing = self.schema.check_header(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{self.file_name}: missing required columns {missing}")
            for i, row in enumerate(reader, start=2):        # row 1 = header
                raw = dict(row)
                sha = canonical_hash(raw)
                issues = self.schema.check_keys(row)
                srid = (row.get("source_record_id") or "").strip() or f"{self.schema.modality}-ROW{i}"
                if srid in seen:
                    issues.append(Issue("ERROR", "source_record_id", "duplicate source_record_id", srid))
                    srid = f"{srid}#DUP{i}"
                seen.add(srid)
                event = None
                if not any(x.severity == "ERROR" for x in issues):
                    event, more = self.to_event(row)
                    issues += more
                    if any(x.severity == "ERROR" for x in more):
                        event = None
                quarantined = event is None
                res.raw.append((srid, (row.get("case_id") or "").strip() or None, i, raw, sha, quarantined))
                if event:
                    if event.get("ts") is None and event.get("ts_quality") not in ("EXACT", "DATE_ONLY"):
                        event["extra"]["timestamp_issue"] = event.get("ts_quality")
                    res.events.append(event)
                for x in issues:
                    res.issues.append((i, srid, x))
        res.stats = {"rows": len(res.raw), "events": len(res.events),
                     "quarantined": sum(1 for r in res.raw if r[5]),
                     "warnings": sum(1 for _, _, x in res.issues if x.severity == "WARNING"),
                     "errors": sum(1 for _, _, x in res.issues if x.severity == "ERROR")}
        return res
