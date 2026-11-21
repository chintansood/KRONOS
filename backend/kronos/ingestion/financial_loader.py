"""Financial transaction loader."""
from . import normalizer as N
from . import timestamp_normalizer as T
from .base_loader import BaseLoader
from .schema_validator import Issue, SourceSchema


class FinancialLoader(BaseLoader):
    file_name = "FINANCIAL_TRANSACTIONS.csv"
    schema = SourceSchema("FINANCIAL", ["case_id", "txn_datetime", "sender_account", "receiver_account", "amount",
                                        "channel", "evidence_id", "source_record_id"])

    def to_event(self, row):
        issues = []
        e = self.base_event(row, "FINANCIAL")
        ts, q = T.parse(row.get("txn_datetime"))
        if q in ("INVALID", "MISSING"):
            issues.append(Issue("WARNING", "txn_datetime", f"timestamp {q.lower()}", row.get("txn_datetime")))
        amt, ok = N.to_float(row.get("amount"), 0)
        if not ok:
            issues.append(Issue("WARNING", "amount", "invalid amount; set to NULL", row.get("amount")))
        lat, lon = self.coord(row, "latitude", "longitude", issues)
        s = N.ident(row.get("sender_person_id")) or N.ident(row.get("sender_org_id"))
        r = N.ident(row.get("receiver_person_id")) or N.ident(row.get("receiver_org_id"))
        e.update(ts=ts, ts_quality=q, person_id=N.ident(row.get("sender_person_id")),
                 entity_id_1=s, entity_id_2=r, entity_type="ACCOUNT",
                 account_number=N.account(row.get("sender_account")),
                 counterpart_account=N.account(row.get("receiver_account")), amount=amt,
                 latitude=lat, longitude=lon, accuracy_m=300.0, location_name=row.get("location_name"),
                 event_type=(row.get("channel") or "UNKNOWN").upper(),
                 event_description=(f"{row.get('channel')} ₹{amt:,.2f} " if amt is not None else f"{row.get('channel')} ₹? ")
                 + f"{row.get('sender_name')} ({row.get('sender_account')}) → {row.get('receiver_name')} "
                   f"({row.get('receiver_account')}); purpose: {row.get('purpose') or 'not stated'}")
        e["extra"] = {k: row.get(k) for k in ("sender_name", "receiver_name", "sender_bank", "receiver_bank",
                                               "sender_org_id", "receiver_org_id", "receiver_person_id", "purpose",
                                               "status", "currency")}
        return e, issues
