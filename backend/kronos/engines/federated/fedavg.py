"""Federated learning SIMULATION for multi-agency collaboration.

Each agency (AGY-CHD, AGY-PB, AGY-HR, AGY-DL) keeps its own transaction records. Agencies train
a local logistic-regression anomaly model and send only weight updates, signed with HMAC-SHA256
(per-agency key), optionally norm-clipped and noised. The coordinator verifies signatures,
aggregates (FedAvg weighted by sample count, or coordinate-wise median for robustness) and
redistributes a versioned global model.

This is a single-process simulation on synthetic data. It is NOT a production deployment and
federated learning does NOT by itself guarantee privacy: updates can leak information (use
secure aggregation + differential privacy in production) and malicious agencies can poison the
model (use robust aggregation, update validation and audit).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from ...config import settings
from ..multimodal.financial import _features, _txns

FEATS = ["log_amt", "hour", "is_cash", "round", "rel_amt", "s_24h", "pair_seq"]
REPORT = settings.models_dir / "federated_report.json"


def _data(gt: dict):
    t = _features(_txns())
    y_ids = {x["evidence_id"] for x in gt.get("fin_anomalies", [])}
    X = t[FEATS].astype(float).values
    X = np.hstack([X, np.ones((len(X), 1))])
    y = t.evidence_id.isin(y_ids).astype(float).values
    return t, X, y


def _sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def _local_train(w, X, y, epochs=30, lr=0.1, l2=1e-3):
    pos_w = (len(y) - y.sum()) / max(1.0, y.sum())          # class re-weighting
    sw = np.where(y == 1, pos_w, 1.0)
    for _ in range(epochs):
        p = _sigmoid(X @ w)
        g = X.T @ ((p - y) * sw) / sw.sum() + l2 * w
        w = w - lr * g
    return w


def _sign(key: bytes, payload: bytes) -> str:
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _eval(w, X, y):
    if len(set(y)) < 2:
        return {"rocAuc": None, "averagePrecision": None}
    s = _sigmoid(X @ w)
    return {"rocAuc": round(float(roc_auc_score(y, s)), 4), "averagePrecision": round(float(average_precision_score(y, s)), 4)}


def run(gt: dict, rounds: int = 25, aggregator: str = "fedavg", clip: float | None = 5.0, noise_std: float = 0.0,
        poisoned_agency: str | None = None, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    t, X, y = _data(gt)
    mu, sd = X[:, :-1].mean(0), X[:, :-1].std(0) + 1e-9
    X[:, :-1] = (X[:, :-1] - mu) / sd
    test = rng.random(len(X)) < 0.25
    agencies = sorted(a for a in t.agency_id.dropna().unique())
    parts = {a: np.where((t.agency_id.values == a) & ~test)[0] for a in agencies}
    keys = {a: secrets.token_bytes(32) for a in agencies}
    d = X.shape[1]
    # baselines
    central = _local_train(np.zeros(d), X[~test], y[~test], epochs=30 * rounds)
    local_only = {a: _eval(_local_train(np.zeros(d), X[ix], y[ix], epochs=30 * rounds), X[test], y[test]) for a, ix in parts.items()}
    # federated rounds
    w = np.zeros(d)
    history, rejected = [], []
    for r in range(1, rounds + 1):
        updates = []
        for a, ix in parts.items():
            if len(ix) == 0:
                continue
            yl = y[ix].copy()
            if a == poisoned_agency:
                yl = 1 - yl                              # label-flipping attack (simulation)
            wl = _local_train(w.copy(), X[ix], yl)
            delta = wl - w
            if clip:
                n = np.linalg.norm(delta)
                delta = delta * min(1.0, clip / max(n, 1e-12))
            if noise_std:
                delta = delta + rng.normal(0, noise_std, size=d)
            payload = json.dumps({"agency": a, "round": r, "delta": delta.round(8).tolist(), "n": int(len(ix))}).encode()
            updates.append((a, payload, _sign(keys[a], payload)))
        # coordinator: verify signatures, then aggregate
        good = []
        for a, payload, sig in updates:
            if hmac.compare_digest(sig, _sign(keys[a], payload)):
                m = json.loads(payload)
                good.append((np.array(m["delta"]), m["n"]))
            else:
                rejected.append({"round": r, "agency": a})
        deltas = np.array([g for g, _ in good]); ns = np.array([n for _, n in good], dtype=float)
        agg = np.median(deltas, axis=0) if aggregator == "median" else (deltas * ns[:, None]).sum(0) / ns.sum()
        w = w + agg
        version = hashlib.sha256(w.round(8).tobytes()).hexdigest()[:12]
        history.append({"round": r, "modelVersion": f"global-v{r}-{version}", **_eval(w, X[test], y[test])})
    report = {
        "simulation": True,
        "task": "transaction anomaly classification (labels from synthetic ground truth)",
        "agencies": {a: {"trainingSamples": int(len(ix)), "positives": int(y[ix].sum())} for a, ix in parts.items()},
        "testSamples": int(test.sum()), "rounds": rounds, "aggregator": aggregator, "clipNorm": clip, "noiseStd": noise_std,
        "poisonedAgency": poisoned_agency,
        "results": {"federatedGlobal": history[-1], "centralised": _eval(central, X[test], y[test]), "localOnly": local_only},
        "history": history, "rejectedUpdates": rejected,
        "updateSecurity": "HMAC-SHA256 signed updates with per-agency keys; only weight deltas leave an agency.",
        "risks": ["Gradient/weight updates can leak information about local data (membership/attribute inference); "
                  "production needs secure aggregation and differential privacy.",
                  "Model poisoning by a malicious or compromised agency; mitigate with robust aggregation (median/trimmed mean), "
                  "update norm checks and audit trails.",
                  "Non-IID data across agencies can bias the global model.",
                  "This is a simulation in one process; it does not demonstrate network security, key management or governance."],
    }
    REPORT.write_text(json.dumps(report, indent=1))
    return report


def report() -> dict:
    return json.loads(REPORT.read_text()) if REPORT.exists() else {}
