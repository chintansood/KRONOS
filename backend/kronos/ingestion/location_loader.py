"""Location record loader (GPS / cell tower / check-in)."""
from . import normalizer as N
from . import timestamp_normalizer as T
from .base_loader import BaseLoader
from .schema_validator import Issue, SourceSchema


class LocationLoader(BaseLoader):
    file_name = "LOCATION.csv"
    schema = SourceSchema("LOCATION", ["case_id", "person_id", "timestamp", "latitude", "longitude", "accuracy_m",
                                       "source_type", "evidence_id", "source_record_id"])

    def to_event(self, row):
        issues = []
        e = self.base_event(row, "LOCATION")
        ts, q = T.parse(row.get("timestamp"))
        if q in ("INVALID", "MISSING"):
            issues.append(Issue("WARNING", "timestamp", f"timestamp {q.lower()}", row.get("timestamp")))
        lat, lon = self.coord(row, "latitude", "longitude", issues)
        acc, ok = N.to_float(row.get("accuracy_m"), 0, 100000)
        if not ok:
            issues.append(Issue("WARNING", "accuracy_m", "invalid accuracy", row.get("accuracy_m")))
        pid = N.ident(row.get("person_id"))
        if not pid:
            issues.append(Issue("WARNING", "person_id", "missing person_id; record kept, attributed via device/phone only"))
        src = (row.get("source_type") or "UNKNOWN").upper()
        e.update(ts=ts, ts_quality=q, person_id=pid, entity_id_1=pid, entity_type="PERSON",
                 phone_number=N.phone(row.get("phone_number")), device_id=N.ident(row.get("device_id")),
                 latitude=lat, longitude=lon, accuracy_m=acc, location_name=row.get("location_name"),
                 event_type=f"LOCATION_{src}",
                 event_description=f"{src.replace('_', ' ').title()} fix at {row.get('location_name')}"
                                   + (f" (±{acc:.0f} m)" if acc else ""))
        e["extra"] = {"location_type": row.get("location_type"), "source_type": src}
        return e, issues
