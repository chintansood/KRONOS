"""Evidence provenance ledger — a local, permissioned, append-only SHA-256 hash chain.

What it guarantees: tamper-EVIDENCE. If an evidence record (or any ledger block) is
altered after it was recorded, recomputing the hashes exposes the change.
What it does NOT guarantee: that the original evidence was authentic or lawfully
collected. Raw evidence never goes on the chain — only its hash and metadata.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone

from ... import db
from ...ingestion.base_loader import canonical_hash

GENESIS_PREV = "0" * 64
_lock = threading.Lock()


def _ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def block_hash(index, ts: str, event_type, evidence_id, content_hash, actor, metadata, prev_hash) -> str:
    payload = json.dumps([index, ts, event_type, evidence_id, content_hash, actor, metadata or {}, prev_hash],
                         sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _tip():
    r = db.query_one("SELECT block_index, block_hash FROM ledger_blocks ORDER BY block_index DESC LIMIT 1")
    return (r["block_index"], r["block_hash"]) if r else (-1, GENESIS_PREV)


def reset():
    db.execute("TRUNCATE ledger_blocks")


def append_many(entries: list[tuple[str, str | None, str | None, str, dict]]) -> int:
    """entries: (event_type, evidence_id, content_hash, actor, metadata)."""
    if not entries:
        return 0
    with _lock:
        idx, prev = _tip()
        rows = []
        for et, eid, ch, actor, meta in entries:
            idx += 1
            now = datetime.now(timezone.utc)
            ts = _ts(now)
            h = block_hash(idx, ts, et, eid, ch, actor, meta, prev)
            rows.append((idx, now, et, eid, ch, actor, db.Json(meta or {}), prev, h))
            prev = h
        db.execute_values("INSERT INTO ledger_blocks (block_index, ts, event_type, evidence_id, content_hash, actor, "
                          "metadata, prev_hash, block_hash) VALUES %s", rows, page_size=5000)
        return len(rows)


def append(event_type, evidence_id=None, content_hash=None, actor="system", metadata=None):
    append_many([(event_type, evidence_id, content_hash, actor, metadata or {})])


def ensure_genesis():
    if _tip()[0] < 0:
        append("GENESIS", None, None, "system", {"note": "KRONOS local evidence ledger (development / test ledger)"})


def verify_evidence(evidence_id: str, actor: str = "investigator") -> dict:
    ev = db.query_one("SELECT e.evidence_id, r.raw, r.content_sha256, r.source_record_id FROM events e "
                      "JOIN raw_records r USING (source_record_id) WHERE e.evidence_id=%s", (evidence_id,))
    if not ev:
        return {"evidenceId": evidence_id, "result": "NOT_FOUND"}
    blk = db.query_one("SELECT * FROM ledger_blocks WHERE evidence_id=%s AND event_type='INGEST' "
                       "ORDER BY block_index LIMIT 1", (evidence_id,))
    recomputed = canonical_hash(ev["raw"])
    out = {"evidenceId": evidence_id, "sourceRecordId": ev["source_record_id"], "algorithm": "SHA-256",
           "recomputedHash": recomputed, "recordedHash": blk["content_hash"] if blk else None,
           "ledgerBlock": blk["block_index"] if blk else None,
           "recordedAt": blk["ts"].isoformat() if blk else None}
    if not blk:
        out["result"] = "NOT_ON_LEDGER"
    else:
        blk_ok = block_hash(blk["block_index"], _ts(blk["ts"]), blk["event_type"], blk["evidence_id"],
                            blk["content_hash"], blk["actor"], blk["metadata"], blk["prev_hash"]) == blk["block_hash"]
        nxt = db.query_one("SELECT prev_hash FROM ledger_blocks WHERE block_index=%s", (blk["block_index"] + 1,))
        link_ok = nxt is None or nxt["prev_hash"] == blk["block_hash"]
        out["blockIntegrity"] = blk_ok and link_ok
        out["result"] = "VERIFIED" if (recomputed == blk["content_hash"] and blk_ok and link_ok) else "MISMATCH"
    out["note"] = ("Integrity is verified relative to the hash recorded at ingestion. This does not establish "
                   "the authenticity or lawful collection of the original evidence.")
    append("VERIFY", evidence_id, recomputed, actor, {"result": out["result"]})
    return out


def verify_chain() -> dict:
    bad, n, prev = [], 0, GENESIS_PREV
    with db.conn() as c, c.cursor(name="ledger_scan") as cur:
        cur.itersize = 5000
        cur.execute("SELECT block_index, ts, event_type, evidence_id, content_hash, actor, metadata, prev_hash, block_hash "
                    "FROM ledger_blocks ORDER BY block_index")
        for (i, ts, et, eid, ch, actor, meta, ph, bh) in cur:
            n += 1
            if ph != prev or block_hash(i, _ts(ts), et, eid, ch, actor, meta, ph) != bh:
                bad.append(i)
            prev = bh
    return {"blocks": n, "valid": not bad, "invalidBlocks": bad[:50], "tip": prev}


def history(evidence_id: str) -> list[dict]:
    rows = db.query("SELECT block_index, ts, event_type, actor, content_hash, metadata FROM ledger_blocks "
                    "WHERE evidence_id=%s ORDER BY block_index", (evidence_id,))
    return [{"block": r["block_index"], "ts": r["ts"].isoformat(), "eventType": r["event_type"], "actor": r["actor"],
             "contentHash": r["content_hash"], "metadata": r["metadata"]} for r in rows]


# ======================================================================================================
# Merkle anchoring with multi-agency (permissioned) signatures
# ------------------------------------------------------------------------------------------------------
# For every ingested file, a Merkle tree is built over the records' SHA-256 hashes and its root is written
# to the chain in an ANCHOR block, signed (Ed25519) by the participating agency nodes. An anchor is valid
# when a quorum (3 of 4) of node signatures verify. Any record can then be proven to be part of the
# anchored batch with a compact inclusion proof; tampering with a record (or with stored hashes) breaks
# the proof. In this prototype all four node keys live on one machine (data/keys) — in production each
# agency would hold its own key (e.g. in an HSM) and independently recompute the root before signing.
# ======================================================================================================
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from ...config import settings  # noqa: E402

NODES = ["AGY-CHD", "AGY-PB", "AGY-HR", "AGY-DL"]
QUORUM = 3
_KEY_DIR = settings.data_dir / "keys"


def _node_key(node: str) -> Ed25519PrivateKey:
    _KEY_DIR.mkdir(parents=True, exist_ok=True)
    f = _KEY_DIR / f"{node}.pem"
    if not f.exists():
        k = Ed25519PrivateKey.generate()
        f.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        f.chmod(0o600)
    return serialization.load_pem_private_key(f.read_bytes(), password=None)


def node_public_keys() -> dict[str, str]:
    return {n: _node_key(n).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
            for n in NODES}


def _leaf(content_hash_hex: str) -> bytes:
    return hashlib.sha256(b"\x00" + bytes.fromhex(content_hash_hex)).digest()


def _parent(l: bytes, r: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + l + r).digest()


def merkle_levels(leaves: list[bytes]) -> list[list[bytes]]:
    levels = [leaves]
    while len(levels[-1]) > 1:
        cur = levels[-1]
        if len(cur) % 2:
            cur = cur + [cur[-1]]
        levels.append([_parent(cur[i], cur[i + 1]) for i in range(0, len(cur), 2)])
    return levels


def _anchor_payload(run_id, file_name, n, root_hex) -> bytes:
    return f"KRONOS-ANCHOR|{run_id}|{file_name}|{n}|{root_hex}".encode()


def anchor_batch(run_id: str, file_name: str) -> dict:
    rows = db.query("SELECT source_record_id, content_sha256 FROM raw_records WHERE run_id=%s AND file_name=%s "
                    "ORDER BY source_record_id", (run_id, file_name))
    if not rows:
        return {}
    levels = merkle_levels([_leaf(r["content_sha256"]) for r in rows])
    root = levels[-1][0].hex()
    payload = _anchor_payload(run_id, file_name, len(rows), root)
    sigs = {n: _node_key(n).sign(payload).hex() for n in NODES}
    meta = {"run_id": run_id, "file": file_name, "records": len(rows), "merkleRoot": root, "signatures": sigs,
            "quorum": f"{QUORUM}-of-{len(NODES)}"}
    append("ANCHOR", None, root, "consortium", meta)
    return meta


def _verify_sigs(meta: dict) -> dict[str, bool]:
    payload = _anchor_payload(meta["run_id"], meta["file"], meta["records"], meta["merkleRoot"])
    out = {}
    for n in NODES:
        try:
            _node_key(n).public_key().verify(bytes.fromhex(meta["signatures"].get(n, "")), payload)
            out[n] = True
        except Exception:  # noqa: BLE001
            out[n] = False
    return out


def inclusion_proof(evidence_id: str) -> dict:
    r = db.query_one("SELECT r.source_record_id, r.file_name, r.run_id, r.raw, r.content_sha256 FROM raw_records r "
                     "LEFT JOIN events e USING (source_record_id) LEFT JOIN criminal_history h USING (source_record_id) "
                     "WHERE e.evidence_id=%s OR h.evidence_id=%s", (evidence_id, evidence_id))
    if not r:
        return {"evidenceId": evidence_id, "result": "NOT_FOUND"}
    blk = db.query_one("SELECT block_index, metadata FROM ledger_blocks WHERE event_type='ANCHOR' AND metadata->>'run_id'=%s "
                       "AND metadata->>'file'=%s ORDER BY block_index DESC LIMIT 1", (r["run_id"], r["file_name"]))
    if not blk:
        return {"evidenceId": evidence_id, "result": "NOT_ANCHORED"}
    rows = db.query("SELECT source_record_id, content_sha256 FROM raw_records WHERE run_id=%s AND file_name=%s "
                    "ORDER BY source_record_id", (r["run_id"], r["file_name"]))
    idx = next(i for i, x in enumerate(rows) if x["source_record_id"] == r["source_record_id"])
    recomputed = canonical_hash(r["raw"])            # hash of the record as it is stored now
    leaves = [_leaf(x["content_sha256"]) for x in rows]
    leaves[idx] = _leaf(recomputed)
    levels = merkle_levels(leaves)
    path, i = [], idx
    for lvl in levels[:-1]:
        lv = lvl + [lvl[-1]] if len(lvl) % 2 else lvl
        sib = i ^ 1
        path.append({"position": "left" if sib < i else "right", "hash": lv[sib].hex()})
        i //= 2
    # verify the path independently
    h = _leaf(recomputed)
    for step in path:
        h = _parent(bytes.fromhex(step["hash"]), h) if step["position"] == "left" else _parent(h, bytes.fromhex(step["hash"]))
    meta = blk["metadata"]
    sigs = _verify_sigs(meta)
    ok = h.hex() == meta["merkleRoot"]
    out = {"evidenceId": evidence_id, "sourceRecordId": r["source_record_id"], "file": r["file_name"], "leafHash": recomputed,
           "path": path, "computedRoot": h.hex(), "anchoredRoot": meta["merkleRoot"], "anchorBlock": blk["block_index"],
           "batchRecords": meta["records"], "signatures": sigs, "quorumMet": sum(sigs.values()) >= QUORUM,
           "result": "INCLUDED" if ok and sum(sigs.values()) >= QUORUM else "PROOF_FAILED",
           "note": "Proves the record is unchanged since it was anchored in a batch endorsed by the agency nodes. "
                   "It does not establish the authenticity or lawful collection of the original evidence."}
    append("VERIFY", evidence_id, recomputed, "investigator", {"type": "merkle_inclusion", "result": out["result"]})
    return out


def status() -> dict:
    chain = verify_chain()
    anchors = []
    for b in db.query("SELECT block_index, ts, metadata FROM ledger_blocks WHERE event_type='ANCHOR' ORDER BY block_index"):
        sigs = _verify_sigs(b["metadata"])
        anchors.append({"block": b["block_index"], "ts": b["ts"].isoformat(), "file": b["metadata"]["file"],
                        "records": b["metadata"]["records"], "merkleRoot": b["metadata"]["merkleRoot"],
                        "validSignatures": sum(sigs.values()), "quorumMet": sum(sigs.values()) >= QUORUM})
    counts = {r["event_type"]: r["n"] for r in db.query("SELECT event_type, count(*) n FROM ledger_blocks GROUP BY 1")}
    return {"chain": chain, "anchors": anchors, "blockTypes": counts, "nodes": node_public_keys(), "quorum": f"{QUORUM}-of-{len(NODES)}",
            "mode": "local permissioned test ledger (all node keys on one machine — prototype)"}
