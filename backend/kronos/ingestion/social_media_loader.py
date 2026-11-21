"""Social media / messaging loader."""
from . import normalizer as N
from . import timestamp_normalizer as T
from .base_loader import BaseLoader
from .schema_validator import Issue, SourceSchema


class SocialMediaLoader(BaseLoader):
    file_name = "SOCIAL_MEDIA_CHATS.csv"
    schema = SourceSchema("SOCIAL", ["case_id", "platform", "timestamp", "sender_phone", "receiver_phone",
                                     "message_text", "evidence_id", "source_record_id"])

    def to_event(self, row):
        issues = []
        e = self.base_event(row, "SOCIAL")
        ts, q = T.parse(row.get("timestamp"))
        if q in ("INVALID", "MISSING"):
            issues.append(Issue("WARNING", "timestamp", f"timestamp {q.lower()}", row.get("timestamp")))
        lat, lon = self.coord(row, "latitude", "longitude", issues)
        e.update(ts=ts, ts_quality=q, person_id=N.ident(row.get("sender_person_id")),
                 entity_id_1=N.ident(row.get("sender_person_id")), entity_id_2=N.ident(row.get("receiver_person_id")),
                 entity_type="PERSON", phone_number=N.phone(row.get("sender_phone")),
                 counterpart_phone=N.phone(row.get("receiver_phone")), device_id=N.ident(row.get("device_id")),
                 latitude=lat, longitude=lon, accuracy_m=100.0, event_type=f"MESSAGE_{(row.get('platform') or 'UNKNOWN').upper()}",
                 text_content=row.get("message_text"),
                 event_description=f"{row.get('platform')} message {row.get('sender_name')} → {row.get('receiver_name')}: "
                                   f"\"{(row.get('message_text') or '')[:140]}\"")
        e["extra"] = {k: row.get(k) for k in ("platform", "sender_name", "receiver_name", "sender_handle", "receiver_handle")}
        return e, issues
