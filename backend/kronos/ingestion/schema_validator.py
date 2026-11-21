"""Column-level schema validation for source CSVs."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Issue:
    severity: str          # ERROR -> row quarantined (kept in raw_records, no event) | WARNING -> field nulled
    field: str
    issue: str
    raw_value: str | None = None


@dataclass
class SourceSchema:
    modality: str
    required_columns: list[str]
    key_fields: list[str] = field(default_factory=lambda: ["source_record_id", "evidence_id", "case_id"])

    def check_header(self, header: list[str]) -> list[str]:
        return [c for c in self.required_columns if c not in header]

    def check_keys(self, row: dict) -> list[Issue]:
        return [Issue("ERROR", k, "missing key field", row.get(k)) for k in self.key_fields if not (row.get(k) or "").strip()]
