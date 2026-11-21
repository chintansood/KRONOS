"""GraphSAGE link prediction on the person projection (pure PyTorch).

Objective   : predict whether two persons share a recorded relationship (communication or a
              shared identifier) — i.e. link prediction on the person projection graph.
Features    : per-person activity profile (log counts per source, #cases, recorded-role flags,
              flagged-transaction count, night-activity share). No identifiers, no names.
Split       : 15% of edges held out as test positives; equal number of random non-edges as
              negatives; message passing uses training edges only (no leakage).
Baselines   : Adamic–Adar, Jaccard, preferential attachment on the same training graph.
Metrics     : ROC-AUC and average precision on the held-out split.
Limitations : synthetic data; labels are recorded relationships, not ground-truth criminal ties;
              a predicted link is only a candidate until supported by evidence.
"""
from __future__ import annotations

import json
import random

import networkx as nx
import numpy as np
import torch

torch.sparse.check_sparse_tensor_invariants.disable()
from sklearn.metrics import average_precision_score, roc_auc_score

from ... import db
from ...config import settings
from ..multimodal.financial import flagged_ids
from ..store import events
from .analytics import person_projection

REPORT = settings.models_dir / "gnn_report.json"


def features(nodes: list[str]) -> np.ndarray:
    df = events()
    flagged = set(flagged_ids())
    roles = {}
    for r in db.query("SELECT person_id, role FROM person_case_roles"):
        roles.setdefault(r["person_id"], set()).add(r["role"])
    X = []
    by = {pid: g for pid, g in df[df.person_id.notna()].groupby("person_id")}
    for n in nodes:
        g = by.get(n)
        cnt = lambda m: 0 if g is None else int((g.modality == m).sum())
        night = 0.0 if g is None or g.ts.isna().all() else float(((g.ts.dt.hour >= 23) | (g.ts.dt.hour < 5)).mean())
        rs = roles.get(n, set())
        X.append([np.log1p(cnt(m)) for m in ("CDR", "SOCIAL", "LOCATION", "FINANCIAL")] +
                 [0 if g is None else g.case_id.nunique(),
                  float(bool(rs & {"ACCUSED", "PRINCIPAL_ACCUSED"})), float("COMPLAINANT" in rs or "VICTIM" in rs),
                  float("WITNESS" in rs), np.log1p(0 if g is None else int(g.evidence_id.isin(flagged).sum())), night])
    X = np.array(X, dtype=np.float32)
    return (X - X.mean(0)) / (X.std(0) + 1e-6)


class SAGE(torch.nn.Module):
    def __init__(self, d_in, d_h=48):
        super().__init__()
        self.l1s, self.l1n = torch.nn.Linear(d_in, d_h), torch.nn.Linear(d_in, d_h)
        self.l2s, self.l2n = torch.nn.Linear(d_h, d_h), torch.nn.Linear(d_h, d_h)
        self.dec = torch.nn.Sequential(torch.nn.Linear(d_h, d_h), torch.nn.ReLU(), torch.nn.Linear(d_h, 1))

    def score(self, h, a, b):        # Hadamard-product MLP decoder
        return self.dec(h[a] * h[b]).squeeze(-1)

    def forward(self, X, A):   # A: row-normalised sparse adjacency (mean aggregator)
        h = torch.relu(self.l1s(X) + self.l1n(torch.sparse.mm(A, X)))
        h = torch.nn.functional.dropout(h, 0.2, self.training)
        return self.l2s(h) + self.l2n(torch.sparse.mm(A, h))


def _adj(n, edges):
    if not edges:
        return torch.sparse_coo_tensor(torch.zeros((2, 0), dtype=torch.long), torch.zeros(0), (n, n))
    e = np.array(edges + [(b, a) for a, b in edges]).T
    deg = np.bincount(e[0], minlength=n).astype(np.float32)
    vals = 1.0 / np.maximum(deg[e[0]], 1)
    return torch.sparse_coo_tensor(torch.tensor(e), torch.tensor(vals), (n, n)).coalesce()


def train(seed: int = 7, epochs: int = 300) -> dict:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    P = person_projection()
    P = P.subgraph([n for n in P if P.degree(n) > 0]).copy()
    nodes = sorted(P); ix = {n: i for i, n in enumerate(nodes)}
    E = [(ix[u], ix[v]) for u, v in P.edges()]
    random.shuffle(E)
    k = int(0.15 * len(E))
    test_pos, train_pos = E[:k], E[k:]
    eset = set(E) | {(b, a) for a, b in E}
    def neg(m):
        out = set()
        while len(out) < m:
            a, b = random.randrange(len(nodes)), random.randrange(len(nodes))
            if a != b and (a, b) not in eset and (b, a) not in out:
                out.add((a, b))
        return list(out)
    test_neg = neg(len(test_pos))
    deg = np.bincount(np.array(train_pos).ravel(), minlength=len(nodes)).astype(np.float32)
    Xf = np.hstack([features(nodes), np.log1p(deg)[:, None]])   # structural feature from TRAIN edges only
    X = torch.tensor(Xf)
    A = _adj(len(nodes), train_pos)
    model = SAGE(X.shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)
    tp = torch.tensor(train_pos)
    for ep in range(epochs):
        model.train(); opt.zero_grad()
        h = model(X, A)
        tn = torch.tensor(neg(len(train_pos)))
        pos = model.score(h, tp[:, 0], tp[:, 1])
        ng = model.score(h, tn[:, 0], tn[:, 1])
        loss = torch.nn.functional.binary_cross_entropy_with_logits(
            torch.cat([pos, ng]), torch.cat([torch.ones_like(pos), torch.zeros_like(ng)]))
        loss.backward(); opt.step()
    model.eval()
    with torch.no_grad():
        h = model(X, A)
    pairs = test_pos + test_neg
    y = [1] * len(test_pos) + [0] * len(test_neg)
    pa = torch.tensor(pairs)
    with torch.no_grad():
        gnn_s = torch.sigmoid(model.score(h, pa[:, 0], pa[:, 1])).tolist()
    Gt = nx.Graph(); Gt.add_nodes_from(range(len(nodes))); Gt.add_edges_from(train_pos)
    base = {
        "adamicAdar": [s for _, _, s in nx.adamic_adar_index(Gt, pairs)],
        "jaccard": [s for _, _, s in nx.jaccard_coefficient(Gt, pairs)],
        "preferentialAttachment": [s for _, _, s in nx.preferential_attachment(Gt, pairs)],
    }
    res = {"GraphSAGE": {"rocAuc": round(roc_auc_score(y, gnn_s), 4), "averagePrecision": round(average_precision_score(y, gnn_s), 4)}}
    for k2, s in base.items():
        res[k2] = {"rocAuc": round(roc_auc_score(y, s), 4), "averagePrecision": round(average_precision_score(y, s), 4)}
    # candidate links among non-adjacent pairs (full graph message passing for inference)
    with torch.no_grad():
        h_full = model(X, _adj(len(nodes), E))
        allp = torch.tensor([(a, b) for a in range(len(nodes)) for b in range(a + 1, len(nodes)) if (a, b) not in eset])
        S = torch.sigmoid(model.score(h_full, allp[:, 0], allp[:, 1])).numpy()
    cands = [(float(s_), nodes[int(a)], nodes[int(b)]) for (a, b), s_ in zip(allp.tolist(), S) if s_ > 0.9]
    cands.sort(reverse=True)
    torch.save(model.state_dict(), settings.models_dir / "graphsage.pt")
    best_base = max((k2 for k2 in res if k2 != "GraphSAGE"), key=lambda k2: res[k2]["rocAuc"])
    verdict = ("GraphSAGE outperforms the best heuristic baseline" if res["GraphSAGE"]["rocAuc"] > res[best_base]["rocAuc"]
               else f"GraphSAGE does NOT outperform the {best_base} baseline on this data; prefer the baseline for ranking")
    report = {
        "comparison": verdict,
        "model": "GraphSAGE (2 layers, mean aggregator, 48-d, Hadamard-MLP decoder), pure PyTorch",
        "task": "link prediction on person projection graph",
        "graph": {"nodes": len(nodes), "edges": len(E), "trainEdges": len(train_pos), "testPositives": len(test_pos),
                  "testNegatives": len(test_neg)},
        "nodeFeatures": ["log #CDR", "log #messages", "log #location", "log #transactions", "#cases", "recorded accused",
                         "recorded complainant/victim", "recorded witness", "log #flagged transactions", "night-activity share", "log degree (training edges only)"],
        "edgeDefinition": "direct communication, mention, or shared phone/device/SIM/account/company/FIR",
        "negativeSampling": "uniform random non-edges, re-sampled each epoch (1:1)",
        "epochs": epochs, "seed": seed, "metrics": res,
        "topCandidateLinks": [{"persons": [a, b], "score": round(s, 4),
                               "status": "MODEL CANDIDATE — not a verified relationship"} for s, a, b in cands[:25]],
        "limitations": ["Trained and evaluated on synthetic data only; real-world performance is unknown.",
                        "Labels are recorded relationships in the data, not verified criminal associations.",
                        "Edges built from shared identifiers make some links trivially predictable; compare with baselines.",
                        "Predicted links must be corroborated by evidence before use."],
    }
    REPORT.write_text(json.dumps(report, indent=1))
    return report


def report() -> dict:
    if REPORT.exists():
        return json.loads(REPORT.read_text())
    return train()
