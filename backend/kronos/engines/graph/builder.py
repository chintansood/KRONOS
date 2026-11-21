"""Heterogeneous investigation graph.

Node types : PERSON, CASE, PHONE, DEVICE, SIM, ACCOUNT, COMPANY, LOCATION, FIR
Edge types : PERSON_APPEARS_IN_CASE, PERSON_CALLED_PERSON, PERSON_MESSAGED_PERSON, PERSON_USED_PHONE,
             PERSON_USED_DEVICE, PERSON_USED_SIM, PERSON_ASSOCIATED_WITH_ACCOUNT, ACCOUNT_SENT_TO_ACCOUNT,
             COMPANY_HOLDS_ACCOUNT, PERSON_ASSOCIATED_WITH_COMPANY, PERSON_VISITED_LOCATION,
             PERSON_MENTIONED_IN_COMMUNICATION, PERSON_NAMED_IN_FIR, CASE_CONTAINS_EVIDENCE, PERSON_LINKED_TO_PERSON
Individual calls / transactions / messages are aggregated into edges; each edge keeps the
underlying evidence IDs, case IDs, first/last timestamps, count and mean source reliability.
Edges are only created from explicit identifiers in records — never from name similarity.
"""
from __future__ import annotations

import threading
from collections import defaultdict

import networkx as nx
import pandas as pd

from ... import db
from ..store import data_version, events

REL = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.45}
_lock = threading.Lock()
_cache = {"v": None, "g": None}


class EdgeAgg:
    __slots__ = ("count", "evidence", "cases", "first", "last", "rel", "attrs")

    def __init__(self):
        self.count, self.evidence, self.cases, self.first, self.last, self.rel, self.attrs = 0, [], set(), None, None, 0.0, {}

    def add(self, ev, case, ts, rel):
        self.count += 1
        if ev and len(self.evidence) < 40:
            self.evidence.append(ev)
        if case:
            self.cases.add(case)
        if ts is not None and not pd.isna(ts):
            self.first = ts if self.first is None or ts < self.first else self.first
            self.last = ts if self.last is None or ts > self.last else self.last
        self.rel += REL.get(rel, 0.7)


def build() -> nx.MultiDiGraph:
    df = events()
    E: dict[tuple, EdgeAgg] = defaultdict(EdgeAgg)
    nodes: dict[str, dict] = {}

    def node(nid, typ, label=None, **kw):
        if not isinstance(nid, str) or not nid:
            return None
        n = nodes.setdefault(nid, {"type": typ, "label": label or nid})
        if label and n["label"] == nid:
            n["label"] = label
        n.update({k: v for k, v in kw.items() if v is not None})
        return nid

    def edge(a, b, typ, r, **attrs):
        if isinstance(a, str) and isinstance(b, str) and a and b and a != b:
            e = E[(a, b, typ)]
            e.add(r.evidence_id, r.case_id, r.ts, r.source_reliability)
            e.attrs.update(attrs)

    persons = {p["person_id"]: p for p in db.query("SELECT person_id, display_name FROM persons")}
    for pid, p in persons.items():
        node(pid, "PERSON", p["display_name"])
    for c in db.query("SELECT case_id, title, offence_category FROM cases"):
        node(c["case_id"], "CASE", c["title"], offence=c["offence_category"])
    for r in df.itertuples():
        x = r.extra or {}
        m = r.modality
        if m == "CDR":
            edge(r.person_id, r.entity_id_2, "PERSON_CALLED_PERSON", r)
            edge(r.person_id, node(r.phone_number, "PHONE"), "PERSON_USED_PHONE", r)
            edge(r.person_id, node(r.device_id, "DEVICE"), "PERSON_USED_DEVICE", r)
            edge(r.person_id, node(r.sim_id, "SIM"), "PERSON_USED_SIM", r)
            if isinstance(r.entity_id_2, str):
                edge(r.entity_id_2, node(r.counterpart_phone, "PHONE"), "PERSON_USED_PHONE", r)
        elif m == "SOCIAL":
            edge(r.person_id, r.entity_id_2, "PERSON_MESSAGED_PERSON", r)
            edge(r.person_id, node(r.phone_number, "PHONE"), "PERSON_USED_PHONE", r)
            edge(r.person_id, node(r.device_id, "DEVICE"), "PERSON_USED_DEVICE", r)
        elif m == "LOCATION":
            if isinstance(r.location_name, str):
                edge(r.person_id, node("LOC:" + r.location_name, "LOCATION", r.location_name), "PERSON_VISITED_LOCATION", r)
            edge(r.person_id, node(r.device_id, "DEVICE"), "PERSON_USED_DEVICE", r)
        elif m == "FINANCIAL":
            a = node(r.account_number, "ACCOUNT"); b = node(r.counterpart_account, "ACCOUNT")
            edge(a, b, "ACCOUNT_SENT_TO_ACCOUNT", r)
            if isinstance(r.person_id, str):
                edge(r.person_id, a, "PERSON_ASSOCIATED_WITH_ACCOUNT", r)
            if x.get("receiver_person_id"):
                edge(x["receiver_person_id"], b, "PERSON_ASSOCIATED_WITH_ACCOUNT", r)
            elif isinstance(r.entity_id_2, str) and r.entity_id_2.startswith("P"):
                edge(r.entity_id_2, b, "PERSON_ASSOCIATED_WITH_ACCOUNT", r)
            if x.get("sender_org_id"):
                edge(node(x["sender_org_id"], "COMPANY", x.get("sender_name")), a, "COMPANY_HOLDS_ACCOUNT", r)
                if x.get("receiver_person_id"):
                    edge(x["receiver_person_id"], x["sender_org_id"], "PERSON_ASSOCIATED_WITH_COMPANY", r,
                         basis=x.get("purpose"))
            if x.get("receiver_org_id"):
                edge(node(x["receiver_org_id"], "COMPANY", x.get("receiver_name")), b, "COMPANY_HOLDS_ACCOUNT", r)
        elif m == "FIR":
            node(r.source_record_id, "FIR", x.get("fir_number") or r.source_record_id, evidenceId=r.evidence_id)
            edge(r.case_id, r.source_record_id, "CASE_CONTAINS_EVIDENCE", r)
    roles = pd.DataFrame(db.query("SELECT person_id, case_id, role, source_record_id, evidence_id, confidence FROM person_case_roles"))
    ev_case = df.drop_duplicates("evidence_id").set_index("evidence_id")
    for r in roles.itertuples():
        key = (r.person_id, r.case_id, "PERSON_APPEARS_IN_CASE")
        e = E[key]
        e.count += 1
        e.cases.add(r.case_id)
        e.rel += r.confidence or 0.7
        e.attrs.setdefault("roles", [])
        if r.role not in e.attrs["roles"]:
            e.attrs["roles"].append(r.role)
        if isinstance(r.evidence_id, str):
            e.evidence.append(r.evidence_id)
        if isinstance(r.source_record_id, str) and r.role != "RECORD_SUBJECT":
            e2 = E[(r.person_id, r.source_record_id, "PERSON_NAMED_IN_FIR")]
            e2.count += 1; e2.cases.add(r.case_id); e2.rel += r.confidence or 0.7
            e2.attrs["role"] = r.role
            e2.evidence.append(r.evidence_id)
    for t in db.query("SELECT linked_person_id, evidence_id, case_id, entity_text FROM text_entities "
                      "WHERE modality='SOCIAL' AND entity_type='PERSON' AND linked_person_id IS NOT NULL"):
        if t["evidence_id"] in ev_case.index:
            sender = ev_case.loc[t["evidence_id"], "person_id"]
            if isinstance(sender, str) and sender != t["linked_person_id"]:
                e = E[(sender, t["linked_person_id"], "PERSON_MENTIONED_IN_COMMUNICATION")]
                e.count += 1; e.cases.add(t["case_id"]); e.evidence.append(t["evidence_id"]); e.rel += 0.7
    for c in db.query("SELECT person_a, person_b, score FROM identity_candidates WHERE status='CONFIRMED'"):
        e = E[(c["person_a"], c["person_b"], "PERSON_LINKED_TO_PERSON")]
        e.count = 1; e.rel = 1.0; e.attrs.update(basis="investigator-confirmed identity match", score=c["score"])
    G = nx.MultiDiGraph()
    for nid, a in nodes.items():
        G.add_node(nid, **a)
    for (a, b, typ), e in E.items():
        if a not in G:
            G.add_node(a, type="PERSON" if a.startswith("P") else "UNKNOWN", label=a)
        if b not in G:
            G.add_node(b, type="CASE" if b.startswith("CASE") else "UNKNOWN", label=b)
        G.add_edge(a, b, key=typ, type=typ, count=e.count, evidence=e.evidence, cases=sorted(e.cases),
                   first=e.first.isoformat() if e.first is not None else None,
                   last=e.last.isoformat() if e.last is not None else None,
                   reliability=round(e.rel / max(1, e.count), 2), **e.attrs)
    return G


def graph() -> nx.MultiDiGraph:
    v = data_version() + str(db.query_one("SELECT count(*) n FROM identity_candidates WHERE status='CONFIRMED'")["n"])
    with _lock:
        if _cache["v"] != v:
            _cache["g"] = build()
            _cache["v"] = v
        return _cache["g"]
