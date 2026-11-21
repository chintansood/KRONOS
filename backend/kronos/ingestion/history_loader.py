"""Criminal-history loader (prior arrests / charge-sheets / court records from a separate records system).
These rows carry no KRONOS person IDs — linking them to current profiles is done by the
criminal-history linkage engine, never assumed from a name."""
from . import normalizer as N
from . import timestamp_normalizer as T
from .base_loader import BaseLoader
from .schema_validator import Issue, SourceSchema


class HistoryLoader(BaseLoader):
    file_name = "CRIMINAL_HISTORY.csv"
    schema = SourceSchema("HISTORY", ["record_id", "full_name", "father_name", "record_date", "offence_category",
                                      "disposition", "evidence_id", "source_record_id"],
                          key_fields=["source_record_id", "evidence_id", "record_id"])

    def to_event(self, row):
        issues = []
        d, q = T.parse(row.get("record_date"))
        if q in ("INVALID", "MISSING"):
            issues.append(Issue("WARNING", "record_date", f"date {q.lower()}", row.get("record_date")))
        by, ok = N.to_int(row.get("birth_year"))
        if not ok or (by is not None and not 1900 < by < 2015):
            issues.append(Issue("WARNING", "birth_year", "implausible birth year; set to NULL", row.get("birth_year"))); by = None
        if not (row.get("full_name") or "").strip():
            issues.append(Issue("ERROR", "full_name", "missing name — record cannot be linked"))
        rel, _ = N.reliability(row.get("source_reliability"))
        return dict(history_id=row["record_id"].strip(), source_record_id=row["source_record_id"].strip(),
                    evidence_id=row["evidence_id"].strip(), record_type=row.get("record_type"),
                    source_system=row.get("source_system"), full_name=(row.get("full_name") or "").strip(),
                    alias_names=[a.strip() for a in (row.get("alias_names") or "").split(";") if a.strip()],
                    father_name=(row.get("father_name") or "").strip() or None, birth_year=by,
                    address=row.get("address"), phone_at_record=N.phone(row.get("phone_at_record")),
                    fir_reference=row.get("fir_reference"), offence_category=row.get("offence_category"),
                    sections=row.get("sections"), police_station=row.get("police_station"), district=row.get("district"),
                    record_date=d.date() if d else None, disposition=(row.get("disposition") or "").upper() or None,
                    modus_operandi=row.get("modus_operandi"), source_reliability=rel, extra={}), issues
