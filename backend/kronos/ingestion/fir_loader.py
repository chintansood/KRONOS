"""FIR / police statement loader."""
from . import normalizer as N
from . import timestamp_normalizer as T
from .base_loader import BaseLoader
from .schema_validator import Issue, SourceSchema


class FIRLoader(BaseLoader):
    file_name = "FIR.csv"
    schema = SourceSchema("FIR", ["fir_number", "case_id", "record_type", "registration_date", "registration_time",
                                  "incident_datetime", "narrative", "evidence_id", "source_record_id"])

    def to_event(self, row):
        issues = []
        e = self.base_event(row, "FIR")
        ts, q = T.parse(row.get("registration_date"), row.get("registration_time"))
        inc, iq = T.parse(row.get("incident_datetime"))
        if q in ("INVALID", "MISSING"):
            issues.append(Issue("WARNING", "registration_date", f"timestamp {q.lower()}", row.get("registration_date")))
        if iq in ("INVALID", "MISSING"):
            issues.append(Issue("WARNING", "incident_datetime", f"timestamp {iq.lower()}", row.get("incident_datetime")))
        if not (row.get("narrative") or "").strip():
            issues.append(Issue("WARNING", "narrative", "empty narrative"))
        lat, lon = self.coord(row, "incident_lat", "incident_lon", issues)
        accused = [a for a in (row.get("accused_person_ids") or "").split(";") if a.strip()]
        e.update(ts=ts, ts_quality=q, person_id=N.ident(row.get("complainant_person_id")),
                 entity_id_1=N.ident(row.get("complainant_person_id")), entity_type="FIR",
                 latitude=lat, longitude=lon, accuracy_m=200.0, location_name=row.get("incident_location"),
                 event_type=row.get("record_type") or "FIR", text_content=row.get("narrative"),
                 agency_id=N.ident(row.get("agency_id")),
                 event_description=f"{row.get('record_type', 'FIR').replace('_', ' ').title()} {row.get('fir_number')} at "
                                   f"{row.get('police_station')} ({row.get('district')}): {row.get('offence_category')}")
        e["extra"] = {"fir_number": row.get("fir_number"), "police_station": row.get("police_station"),
                      "district": row.get("district"), "offence_category": row.get("offence_category"),
                      "sections": row.get("sections"), "incident_ts": inc.isoformat() if inc else None,
                      "accused_person_ids": accused, "complainant_name": row.get("complainant_name"),
                      "record_type": row.get("record_type")}
        return e, issues
