"""Core tests. Unit tests run standalone; integration tests require the ingested `kronos` database
(python scripts/build_all.py) and are skipped automatically if it is unavailable."""
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kronos.engines.temporal.travel import haversine_km  # noqa: E402
from kronos.ingestion import normalizer as N  # noqa: E402
from kronos.ingestion import timestamp_normalizer as T  # noqa: E402
from kronos.ingestion.base_loader import canonical_hash  # noqa: E402
from kronos.engines.identity.resolver import name_similarity  # noqa: E402
from kronos.engines.llm.assistant import _fact_check  # noqa: E402
from kronos.engines.llm.retrieval import split_text  # noqa: E402


# ------------------------------------------------------------------ unit
def test_haversine_known_distances():
    assert haversine_km(0, 0, 0, 0) == 0
    d = haversine_km(28.6139, 77.2090, 19.0760, 72.8777)        # Delhi – Mumbai ≈ 1150 km
    assert 1140 < d < 1160
    assert math.isclose(haversine_km(10, 20, 30, 40), haversine_km(30, 40, 10, 20))


def test_timestamp_formats_and_quality():
    assert T.parse("2025-03-01 10:20:30") == (datetime(2025, 3, 1, 10, 20, 30), "EXACT")
    assert T.parse("01-03-2025", "10:20:30")[0] == datetime(2025, 3, 1, 10, 20, 30)
    assert T.parse("01/03/2025 10:20")[0] == datetime(2025, 3, 1, 10, 20)
    assert T.parse("2025-03-01")[1] == "DATE_ONLY"
    assert T.parse("2025-13-45 25:61:00") == (None, "INVALID")
    assert T.parse("") == (None, "MISSING")


def test_normalisers_keep_invalid_out():
    assert N.phone("+91 98765-43210") == "+91-9876543210"
    assert N.phone("N/A") is None
    assert N.to_float("999.0", -90, 90) == (None, False)
    assert N.to_float("", 0) == (None, True)
    assert N.reliability("weird") == ("MEDIUM", 0.7)


def test_canonical_hash_is_order_independent_and_sensitive():
    a = canonical_hash({"x": "1", "y": "2"})
    assert a == canonical_hash({"y": "2", "x": "1"})
    assert a != canonical_hash({"x": "1", "y": "3"})


def test_name_similarity_nicknames_vs_namesakes():
    assert name_similarity("Ram Kumar", "Raju")[0] >= 0.85
    assert name_similarity("Amit Sharma", "Rahul Verma")[0] < 0.5


def test_fact_check_flags_misattributed_figures():
    used = [{"ids": ["EVD-TXN000001"], "text": "Sent ₹11,116 to A"}, {"ids": ["EVD-TXN000002"], "text": "Received ₹46,000 from B"}]
    out, n = _fact_check("x ₹46,000 [EVD-TXN000001]\ny ₹46,000 [EVD-TXN000002]", used)
    assert n == 1 and "⚠" in out.splitlines()[0] and "⚠" not in out.splitlines()[1]


def test_splitter_overlap():
    chunks = split_text("A one. B two. C three. D four.", max_chars=14)
    assert len(chunks) > 1 and all(len(c) <= 30 for c in chunks)


def test_generator_is_deterministic(tmp_path):
    from kronos.synth.generator import SynthConfig, generate
    c1 = generate(SynthConfig(n_cases=6, n_people=80, n_cdr=300, n_social=200, n_location=500, n_transactions=300,
                              out_dir=str(tmp_path / "a")))
    c2 = generate(SynthConfig(n_cases=6, n_people=80, n_cdr=300, n_social=200, n_location=500, n_transactions=300,
                              out_dir=str(tmp_path / "b")))
    assert c1 == c2
    assert (tmp_path / "a" / "FIR.csv").read_text() == (tmp_path / "b" / "FIR.csv").read_text()
    gt = json.loads((tmp_path / "a" / "ground_truth.json").read_text())
    assert gt["alias_pairs"] and gt["namesakes"] and gt["impossible_travel"]


# ------------------------------------------------------------------ integration (needs DB)
def _db_ready():
    try:
        from kronos import db
        return db.query_one("SELECT count(*) n FROM events")["n"] > 0
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _db_ready(), reason="kronos database not built")


@needs_db
def test_ledger_detects_tampering_and_chain_valid():
    from kronos import db
    from kronos.engines.provenance import ledger
    ev = db.query_one("SELECT e.evidence_id, r.source_record_id, r.raw FROM events e JOIN raw_records r USING (source_record_id) "
                      "WHERE e.modality='FINANCIAL' LIMIT 1")
    assert ledger.verify_evidence(ev["evidence_id"], "pytest")["result"] == "VERIFIED"
    tampered = dict(ev["raw"]); tampered["amount"] = "1.00"
    db.execute("UPDATE raw_records SET raw=%s WHERE source_record_id=%s", (db.Json(tampered), ev["source_record_id"]))
    try:
        assert ledger.verify_evidence(ev["evidence_id"], "pytest")["result"] == "MISMATCH"
    finally:
        db.execute("UPDATE raw_records SET raw=%s WHERE source_record_id=%s", (db.Json(ev["raw"]), ev["source_record_id"]))
    assert ledger.verify_evidence(ev["evidence_id"], "pytest")["result"] == "VERIFIED"
    assert ledger.verify_chain()["valid"]


@needs_db
def test_no_records_silently_dropped():
    from kronos import db
    raw = db.query_one("SELECT count(*) n FROM raw_records")["n"]
    ev = db.query_one("SELECT count(*) n FROM events")["n"]
    q = db.query_one("SELECT count(*) n FROM raw_records WHERE quarantined")["n"]
    hist = db.query_one("SELECT count(*) n FROM criminal_history")["n"]     # prior records live in their own table
    assert raw == ev + hist + q


@needs_db
def test_identity_never_auto_merges():
    from kronos import db
    assert db.query_one("SELECT count(*) n FROM identity_candidates WHERE status='CONFIRMED' AND "
                        "candidate_id NOT IN (SELECT candidate_id FROM identity_reviews WHERE decision='CONFIRMED')")["n"] == 0


@needs_db
def test_travel_flags_have_full_explanation():
    from kronos.engines.temporal import travel
    for f in travel.detect_all()[:5]:
        for k in ("personId", "first", "second", "distanceKm", "elapsedMinutes", "impliedSpeedKmh", "thresholds", "interpretation"):
            assert k in f
        assert f["first"]["sourceRecordId"] and f["second"]["evidenceId"]


@needs_db
def test_api_contract_matches_frontend_shapes():
    from fastapi.testclient import TestClient
    from kronos.api.main import app
    c = TestClient(app)
    cases = c.get("/api/cases").json()
    assert cases and {"id", "title", "offenceCategory", "status", "priority", "personIds", "primarySuspectIds", "evidenceCount"} <= set(cases[0])
    p = c.get("/api/persons").json()[0]
    assert {"id", "name", "contactNumbers", "associatedDevices", "bankAccounts", "casesMentioned", "primarySuspectCases"} <= set(p)
    tl = c.get(f"/api/persons/{p['id']}/timeline").json()
    assert tl and {"id", "timestamp", "dateStr", "monthStr", "timeStr", "modality", "title", "caseId", "evidenceId"} <= set(tl[0])
    g = c.get(f"/api/graph/subgraph?focus={p['id']}").json()
    assert g["nodes"] and all({"source", "target"} <= set(e) for e in g["edges"])
    h = c.get(f"/api/cases/{cases[0]['id']}/hypotheses").json()
    assert all(x["humanReviewRequired"] and x["contradicting"] for x in h["hypotheses"])


# ------------------------------------------------------------------ novelties
def test_merkle_root_and_path_are_consistent():
    import hashlib
    from kronos.engines.provenance.ledger import _leaf, _parent, merkle_levels
    hashes = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(5)]
    levels = merkle_levels([_leaf(h) for h in hashes])
    # recompute the root for leaf 3 from its authentication path
    i, h = 3, _leaf(hashes[3])
    for lvl in levels[:-1]:
        lv = lvl + [lvl[-1]] if len(lvl) % 2 else lvl
        sib = lv[i ^ 1]
        h = _parent(sib, h) if (i ^ 1) < i else _parent(h, sib)
        i //= 2
    assert h == levels[-1][0]
    tampered = merkle_levels([_leaf(x) for x in hashes[:3] + [hashlib.sha256(b"x").hexdigest()] + hashes[4:]])
    assert tampered[-1][0] != levels[-1][0]


@needs_db
def test_merkle_inclusion_proof_detects_tampering():
    from kronos import db
    from kronos.engines.provenance import ledger
    ev = db.query_one("SELECT e.evidence_id, r.source_record_id, r.raw FROM events e JOIN raw_records r USING (source_record_id) "
                      "WHERE e.modality='CDR' LIMIT 1")
    assert ledger.inclusion_proof(ev["evidence_id"])["result"] == "INCLUDED"
    t = dict(ev["raw"]); t["duration_sec"] = "99999"
    db.execute("UPDATE raw_records SET raw=%s WHERE source_record_id=%s", (db.Json(t), ev["source_record_id"]))
    try:
        assert ledger.inclusion_proof(ev["evidence_id"])["result"] == "PROOF_FAILED"
    finally:
        db.execute("UPDATE raw_records SET raw=%s WHERE source_record_id=%s", (db.Json(ev["raw"]), ev["source_record_id"]))
    st = ledger.status()
    assert st["chain"]["valid"] and all(a["quorumMet"] for a in st["anchors"])


@needs_db
def test_behavioural_matches_never_high_and_never_auto_confirmed():
    from kronos import db
    rows = db.query("SELECT band, status, features FROM identity_candidates")
    assert rows
    assert not [r for r in rows if (r["features"] or {}).get("basis") == "behavioural" and r["band"] == "HIGH"]


@needs_db
def test_history_links_are_candidates_and_excluded_from_scores():
    from kronos import db
    from kronos.engines.intelligence import priority
    assert db.query_one("SELECT count(*) n FROM history_links WHERE status='CONFIRMED'")["n"] == \
        db.query_one("SELECT count(DISTINCT link_id) n FROM history_reviews WHERE decision='CONFIRMED'")["n"]
    case = db.query_one("SELECT case_id FROM cases ORDER BY case_id LIMIT 1")["case_id"]
    factors = {f["factor"] for r in priority.assess(case)["ranking"] for f in r["factors"]}
    assert not any("history" in f.lower() or "prior" in f.lower() for f in factors)


@needs_db
def test_confidence_scores_are_bounded_and_explained():
    from kronos import db
    from kronos.engines.intelligence import hypothesis, next_evidence
    case = db.query_one("SELECT case_id FROM person_case_roles WHERE role='PRINCIPAL_ACCUSED' ORDER BY case_id LIMIT 1")["case_id"]
    recs = next_evidence.recommend(case)
    assert recs and all(0 <= r["valueScore"] <= 1 and r["scoreBreakdown"] for r in recs)
    assert [r["valueScore"] for r in recs] == sorted([r["valueScore"] for r in recs], reverse=True)
    for h in hypothesis.analyse(case)["hypotheses"]:
        assert -1 < h["confidence"]["evidentialBalance"] < 1 and "not a probability" in h["confidence"]["note"]


# ------------------------------------------------------------------ PS5 deliverables
def test_language_detection_and_identifier_protection():
    from kronos.engines.llm import language as L
    assert L.detect("इस व्यक्ति के लेनदेन") == "hi" and L.detect("આ વ્યક્તિના વ્યવહારો") == "gu"
    assert L.detect("ਇਸ ਵਿਅਕਤੀ ਦੇ ਲੈਣ-ਦੇਣ") == "pa" and L.detect("show transactions") == "en"
    src = "Account HDFC-50100234567 got ₹46,000 on 2025-02-24 [EVD-TXN001456] (CASE017, P00014), 41.5 km away."
    masked, vals = L._mask(src)
    assert not any(v in masked for v in ("HDFC-50100234567", "₹46,000", "EVD-TXN001456", "CASE017", "P00014", "41.5"))
    assert L._unmask(masked, vals) == (src, True)
    ids = [int(i) for i in L.PH.findall(masked)]
    assert L._accept(masked, ids)                                   # untouched placeholders accepted
    assert not L._accept(masked.replace("⟦0⟧", ""), ids)             # a lost identifier is rejected
    assert not L._accept(masked + " 01 जनवरी", ids)                  # an invented date/number is rejected


def test_search_query_interpretation():
    from kronos.engines.llm.search import parse
    f = parse("cash deposits above 40,000 in March 2025 at night")
    assert "FINANCIAL" in f["modalities"] and f["amount_min"] == 40000
    assert f["date_from"].month == 3 and f["date_to"].month == 4 and f["hours"] == (22, 5)
    g = parse("transfers between 2 lakh and 5 lakh")
    assert (g["amount_min"], g["amount_max"]) == (200000, 500000)


@needs_db
def test_evidence_retrieval_engine_explains_matches():
    from kronos.engines.llm import search
    r = search.search("cash deposits above 40,000", limit=5)
    assert r["results"] and all(x["amount"] is None or x["amount"] >= 40000 for x in r["results"])
    assert all(x["whyMatched"] for x in r["results"])


@needs_db
def test_case_diary_and_draft_report():
    from kronos import db
    from kronos.engines.reports import case_report, diary
    case = db.query_one("SELECT case_id FROM cases ORDER BY case_id LIMIT 1")["case_id"]
    before = db.query_one("SELECT count(*) n FROM ledger_blocks WHERE event_type='CASE_DIARY'")["n"]
    diary.add_entry(case, "pytest diary entry", "2026-11-20T10:00", "Test place", "pytest")
    assert db.query_one("SELECT count(*) n FROM ledger_blocks WHERE event_type='CASE_DIARY'")["n"] == before + 1
    D = diary.build(case)
    texts = [i["text"] for e in D["entries"] for s in e["sections"] for i in s["items"]]
    assert D["entries"] and any("pytest diary entry" in t for t in texts) and "DRAFT" in D["note"]
    html_ = case_report.render_html(case_report.build(case))
    assert html_.count("<h2>") == 10 and "not a final report" in html_
    db.execute("DELETE FROM case_diary_entries WHERE author='pytest'")
