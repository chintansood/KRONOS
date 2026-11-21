"""Hybrid retrieval index: pgvector (local nomic-embed-text embeddings) + PostgreSQL full-text,
fused with Reciprocal Rank Fusion. Every chunk keeps its case / person / evidence IDs."""
from __future__ import annotations

import re

from ... import db
from ...config import settings
from ..multimodal import summarizer
from . import ollama

SENT = re.compile(r"(?<=[.!?])\s+")


def split_text(text: str, max_chars: int = 900, overlap_sentences: int = 1) -> list[str]:
    """Sentence-aware splitter with one-sentence overlap."""
    sents = [s for s in SENT.split(text or "") if s.strip()]
    chunks, cur = [], []
    for s in sents:
        if cur and len(" ".join(cur)) + len(s) > max_chars:
            chunks.append(" ".join(cur))
            cur = cur[-overlap_sentences:] if overlap_sentences else []
        cur.append(s)
    if cur:
        chunks.append(" ".join(cur))
    return chunks or ([text] if text else [])


def _chunks() -> list[tuple]:
    out = []
    for s in db.query("SELECT case_id, summary_json FROM case_summaries"):
        j, cid = s["summary_json"], s["case_id"]
        pids = [p["personId"] for p in j["people"]]
        out.append((f"SUM-{cid}-overview", cid, pids, "CASE_SUMMARY", j["importantEvidence"][:10],
                    f"Case {cid} summary. {j['conciseSummary']} {j['detailedNarrative']}"))
        out.append((f"SUM-{cid}-people", cid, pids, "CASE_SUMMARY", [e for p in j["people"] for e in p["evidenceIds"]][:12],
                    f"People recorded in {cid}: " + "; ".join(f"{p['name']} ({p['personId']}) recorded as {p['recordedRole']}" for p in j["people"])))
        for i, o in enumerate(j["suspiciousObservations"]):
            out.append((f"SUM-{cid}-obs{i}", cid, pids, "FINDING", o["evidenceIds"], f"{cid} observation: {o['text']}"))
        for i, f in enumerate(j["financialSummary"]["flagged"][:10]):
            out.append((f"SUM-{cid}-fin{i}", cid, pids, "FINDING", [f["evidenceId"]],
                        f"{cid} flagged transaction {f['evidenceId']} ₹{f['amount']:,.0f} on {f['timestamp']}: {'; '.join(f['reasons'])}"))
    for r in db.query("SELECT evidence_id, case_id, text_content, extra FROM events WHERE modality='FIR'"):
        pids = [x["person_id"] for x in db.query("SELECT DISTINCT person_id FROM person_case_roles WHERE evidence_id=%s", (r["evidence_id"],))]
        for i, c in enumerate(split_text(r["text_content"])):
            out.append((f"FIR-{r['evidence_id']}-{i}", r["case_id"], pids, "FIR", [r["evidence_id"]],
                        f"{r['extra'].get('record_type', 'FIR')} {r['extra'].get('fir_number')} ({r['case_id']}): {c}"))
    for r in db.query("SELECT evidence_id, case_id, person_id, entity_id_2, ts, text_content, extra FROM events WHERE modality='SOCIAL'"):
        x = r["extra"] or {}
        out.append((f"MSG-{r['evidence_id']}", r["case_id"], [p for p in (r["person_id"], r["entity_id_2"]) if p], "MESSAGE",
                    [r["evidence_id"]], f"{x.get('platform')} message on {r['ts'].strftime('%Y-%m-%d %H:%M') if r['ts'] else 'unknown date'} from {x.get('sender_name')} "
                                        f"({r['person_id']}) to {x.get('receiver_name')} ({r['entity_id_2']}): {r['text_content']}"))
    for p in db.query("""SELECT p.person_id, p.display_name, p.names, p.phones, p.devices, p.accounts,
                                array_agg(DISTINCT r.case_id || ':' || r.role) roles
                         FROM persons p JOIN person_case_roles r USING (person_id) GROUP BY 1,2,3,4,5,6"""):
        out.append((f"PER-{p['person_id']}", None, [p["person_id"]], "PERSON_PROFILE", [],
                    f"Person {p['person_id']} {p['display_name']} (names: {', '.join(p['names'])}). Phones {', '.join(p['phones'])}; "
                    f"devices {', '.join(p['devices'])}; accounts {', '.join(p['accounts'])}. Case roles: {', '.join(p['roles'])}."))
    return out


def build_index(embed: bool = True, batch: int = 64) -> dict:
    for cid in [r["case_id"] for r in db.query("SELECT case_id FROM cases")]:
        summarizer.generate_case_summary(cid)
    chunks = _chunks()
    db.execute("TRUNCATE doc_chunks")
    db.execute_values("INSERT INTO doc_chunks (chunk_id, case_id, person_ids, doc_type, evidence_ids, content) VALUES %s",
                      [(c[0], c[1], c[2], c[3], c[4], c[5]) for c in chunks],
                      page_size=1000)
    db.execute("UPDATE doc_chunks SET tsv = to_tsvector('english', content)")
    embedded = 0
    if embed:
        try:
            for i in range(0, len(chunks), batch):
                part = chunks[i:i + batch]
                vecs = ollama.embed(["search_document: " + c[5][:2000] for c in part])
                db.execute_values("UPDATE doc_chunks d SET embedding = v.e::vector FROM (VALUES %s) AS v(id, e) WHERE d.chunk_id = v.id",
                                  [(c[0], str(v)) for c, v in zip(part, vecs)])
                embedded += len(part)
        except ollama.LLMUnavailable as e:
            return {"chunks": len(chunks), "embedded": embedded, "warning": f"embedding unavailable: {e}"}
    return {"chunks": len(chunks), "embedded": embedded}


def index_cases(case_ids: list[str], embed: bool = True, batch: int = 32) -> dict:
    """Add (or refresh) retrieval chunks for specific cases and their people, without rebuilding the whole index."""
    want = set(case_ids)
    pids = {r["person_id"] for r in db.query("SELECT DISTINCT person_id FROM person_case_roles WHERE case_id = ANY(%s)", (list(want),))}
    chunks = [c for c in _chunks() if c[1] in want or (c[1] is None and set(c[2]) & pids)]
    if not chunks:
        return {"chunks": 0, "embedded": 0}
    db.execute("DELETE FROM doc_chunks WHERE chunk_id = ANY(%s)", ([c[0] for c in chunks],))
    db.execute_values("INSERT INTO doc_chunks (chunk_id, case_id, person_ids, doc_type, evidence_ids, content) VALUES %s",
                      [(c[0], c[1], c[2], c[3], c[4], c[5]) for c in chunks])
    db.execute("UPDATE doc_chunks SET tsv = to_tsvector('english', content) WHERE chunk_id = ANY(%s)", ([c[0] for c in chunks],))
    embedded = 0
    if embed:
        try:
            for i in range(0, len(chunks), batch):
                part = chunks[i:i + batch]
                vecs = ollama.embed(["search_document: " + c[5][:2000] for c in part])
                db.execute_values("UPDATE doc_chunks d SET embedding = v.e::vector FROM (VALUES %s) AS v(id, e) WHERE d.chunk_id = v.id",
                                  [(c[0], str(v)) for c, v in zip(part, vecs)])
                embedded += len(part)
        except ollama.LLMUnavailable as e:
            return {"chunks": len(chunks), "embedded": embedded, "warning": f"embedding unavailable: {e}"}
    return {"chunks": len(chunks), "embedded": embedded}


def search(query: str, case_id: str | None = None, person_id: str | None = None, k: int = 10,
           doc_types: list[str] | None = None) -> list[dict]:
    where, params = ["TRUE"], []
    if case_id:
        where.append("(case_id = %s OR case_id IS NULL)"); params.append(case_id)
    if person_id:
        where.append("%s = ANY(person_ids)"); params.append(person_id)
    if doc_types:
        where.append("doc_type = ANY(%s)"); params.append(doc_types)
    w = " AND ".join(where)
    ranked: dict[str, float] = {}
    rows: dict[str, dict] = {}
    fts = db.query(f"SELECT chunk_id, case_id, person_ids, doc_type, evidence_ids, content FROM doc_chunks WHERE {w} "
                   f"AND tsv @@ websearch_to_tsquery('english', %s) ORDER BY ts_rank(tsv, websearch_to_tsquery('english', %s)) DESC LIMIT 30",
                   params + [query, query])
    if not fts:   # fall back to OR-matching of terms
        terms = " | ".join(re.findall(r"[A-Za-z0-9]{3,}", query)[:12]) or "case"
        fts = db.query(f"SELECT chunk_id, case_id, person_ids, doc_type, evidence_ids, content FROM doc_chunks WHERE {w} "
                       f"AND tsv @@ to_tsquery('english', %s) ORDER BY ts_rank(tsv, to_tsquery('english', %s)) DESC LIMIT 30",
                       params + [terms, terms])
    for i, r in enumerate(fts):
        ranked[r["chunk_id"]] = ranked.get(r["chunk_id"], 0) + 1 / (60 + i); rows[r["chunk_id"]] = r
    try:
        qv = ollama.embed(["search_query: " + query])[0]
        vec = db.query(f"SELECT chunk_id, case_id, person_ids, doc_type, evidence_ids, content FROM doc_chunks WHERE {w} "
                       f"AND embedding IS NOT NULL ORDER BY embedding <=> %s::vector LIMIT 30", params + [str(qv)])
        for i, r in enumerate(vec):
            ranked[r["chunk_id"]] = ranked.get(r["chunk_id"], 0) + 1 / (60 + i); rows[r["chunk_id"]] = r
    except ollama.LLMUnavailable:
        pass
    best = sorted(ranked, key=lambda c: -ranked[c])[:k]
    return [{**rows[c], "score": round(ranked[c], 4)} for c in best]
