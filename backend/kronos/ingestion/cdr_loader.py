"""Call Detail Record loader."""
from . import normalizer as N
from . import timestamp_normalizer as T
from .base_loader import BaseLoader
from .schema_validator import Issue, SourceSchema


class CDRLoader(BaseLoader):
    file_name = "CDR.csv"
    schema = SourceSchema("CDR", ["case_id", "caller_number", "receiver_number", "call_date", "call_time",
                                  "duration_sec", "imei", "evidence_id", "source_record_id"])

    def to_event(self, row):
        issues = []
        e = self.base_event(row, "CDR")
        ts, q = T.parse(row.get("call_date"), row.get("call_time"))
        if q in ("INVALID", "MISSING"):
            issues.append(Issue("WARNING", "call_date", f"timestamp {q.lower()}", row.get("call_date")))
        a, b = N.phone(row.get("caller_number")), N.phone(row.get("receiver_number"))
        if not a:
            issues.append(Issue("WARNING", "caller_number", "unparseable phone number", row.get("caller_number")))
        dur, ok = N.to_int(row.get("duration_sec"))
        if not ok or (dur is not None and dur < 0):
            issues.append(Issue("WARNING", "duration_sec", "invalid duration", row.get("duration_sec"))); dur = None
        lat, lon = self.coord(row, "tower_lat", "tower_lon", issues)
        kind = (row.get("call_type") or "VOICE").upper()
        e.update(ts=ts, ts_quality=q, person_id=N.ident(row.get("caller_person_id")),
                 entity_id_1=N.ident(row.get("caller_person_id")), entity_id_2=N.ident(row.get("receiver_person_id")),
                 entity_type="PERSON", phone_number=a, counterpart_phone=b, device_id=N.ident(row.get("imei")),
                 sim_id=N.ident(row.get("imsi")), latitude=lat, longitude=lon, accuracy_m=1500.0,
                 location_name=row.get("tower_location"), event_type="SMS" if kind == "SMS" else "VOICE_CALL",
                 duration_sec=dur,
                 event_description=(f"{'SMS' if kind == 'SMS' else 'Call'} {row.get('caller_name')} ({a}) → "
                                    f"{row.get('receiver_name')} ({b})" + (f", {dur}s" if dur else "")
                                    + f" [{row.get('call_status')}] via {row.get('cell_tower_id')}"))
        e["extra"] = {"caller_name": row.get("caller_name"), "receiver_name": row.get("receiver_name"),
                      "call_status": row.get("call_status"), "cell_tower_id": row.get("cell_tower_id")}
        return e, issues
