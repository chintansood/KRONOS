"""Financial transaction analysis.

Detectors (each independently configurable):
  * Isolation Forest   – multivariate outliers over amount/time/behaviour features
  * IQR                – amount above Q3 + k·IQR of the sender's own history (or channel baseline)
  * Rapid pass-through – money received and forwarded onward within a short window (possible layering)
  * Structuring        – repeated transfers just below a reporting threshold
  * Repeated pairs     – recurring sender→receiver relationships (often benign: salary, rent)
An anomaly is an investigative indicator, not evidence of laundering or any offence.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ...config import settings
from ..store import cached, data_version, events

BENIGN_PURPOSES = ("salary", "rent", "bill", "bonus", "property", "registered sale deed", "air ticket", "groceries",
                   "fuel", "pharmacy", "food delivery")


def _txns() -> pd.DataFrame:
    df = events()
    t = df[(df.modality == "FINANCIAL")].copy()
    t["sender"] = t.entity_id_1
    t["receiver"] = t.entity_id_2
    t["purpose"] = t.extra.map(lambda x: (x or {}).get("purpose") or "")
    t["s_name"] = t.extra.map(lambda x: (x or {}).get("sender_name"))
    t["r_name"] = t.extra.map(lambda x: (x or {}).get("receiver_name"))
    return t


def _features(t: pd.DataFrame) -> pd.DataFrame:
    t = t[t.amount.notna() & t.ts.notna()].copy()
    t["log_amt"] = np.log1p(t.amount.astype(float))
    t["hour"] = t.ts.dt.hour + t.ts.dt.minute / 60
    t["is_cash"] = t.event_type.isin(["CASH_DEPOSIT", "CASH_WITHDRAWAL"]).astype(int)
    t["round"] = (t.amount % 1000 == 0).astype(int)
    med = t.groupby("account_number").log_amt.transform("median")
    t["rel_amt"] = t.log_amt - med
    t = t.sort_values("ts")
    t["pair"] = t.account_number.fillna("") + ">" + t.counterpart_account.fillna("")
    t["pair_seq"] = t.groupby("pair").cumcount()
    t["s_24h"] = 0
    for acct, g in t.groupby("account_number"):
        s = pd.Series(1, index=g.ts).rolling("24h").sum().values
        t.loc[g.index, "s_24h"] = s
    return t


def _ref(r) -> dict:
    return {"transactionId": r.source_record_id.replace("SRC-", ""), "evidenceId": r.evidence_id,
            "sourceRecordId": r.source_record_id, "caseId": r.case_id,
            "timestamp": r.ts.strftime("%Y-%m-%d %H:%M"), "amount": float(r.amount), "channel": r.event_type,
            "senderAccount": r.account_number, "receiverAccount": r.counterpart_account,
            "sender": r.sender, "receiver": r.receiver, "senderName": r.s_name, "receiverName": r.r_name,
            "purpose": r.purpose}


def analyse(use_iforest=None, use_iqr=None) -> dict:
    use_iforest = settings.fin_use_isolation_forest if use_iforest is None else use_iforest
    use_iqr = settings.fin_use_iqr if use_iqr is None else use_iqr
    t = _features(_txns())
    flags: dict[str, dict] = {}

    def flag(r, method, score, reason, deviation=None):
        f = flags.setdefault(r.evidence_id, {**_ref(r), "methods": [], "reasons": [], "scores": {}})
        if method not in f["methods"]:
            f["methods"].append(method)
            f["reasons"].append(reason)
            f["scores"][method] = round(float(score), 3)
            if deviation is not None:
                f["deviation"] = deviation

    # --- Isolation Forest -------------------------------------------------------------
    if use_iforest and len(t) > 50:
        X = t[["log_amt", "hour", "is_cash", "round", "rel_amt", "s_24h", "pair_seq"]].astype(float).values
        model = IsolationForest(n_estimators=300, contamination=settings.fin_iforest_contamination, random_state=7)
        pred = model.fit_predict(X)
        score = -model.score_samples(X)
        for (idx, r), p, s in zip(t.iterrows(), pred, score):
            if p == -1:
                why = []
                if r.rel_amt > 1.5: why.append(f"amount ≈{math.exp(r.rel_amt):.0f}× this account's median")
                if r.s_24h >= 4: why.append(f"{int(r.s_24h)} transactions from this account within 24 h")
                if r.is_cash: why.append("cash channel")
                if r.hour < 6: why.append("unusual hour")
                flag(r, "ISOLATION_FOREST", s, "Isolation Forest outlier" + (": " + "; ".join(why) if why else
                                                                            " (combination of features)"))
    # --- IQR --------------------------------------------------------------------------
    if use_iqr:
        k = settings.fin_iqr_k
        for key, g in list(t.groupby("account_number")) + [("__channel__" + c, g) for c, g in t.groupby("event_type")]:
            if len(g) < 8:
                continue
            q1, q3 = g.log_amt.quantile([0.25, 0.75])
            fence = q3 + k * (q3 - q1)
            for _, r in g[g.log_amt > fence].iterrows():
                if key.startswith("__channel__") and r.evidence_id in flags and "IQR" in flags[r.evidence_id]["methods"]:
                    continue
                base = "channel baseline" if key.startswith("__channel__") else "sender's own history"
                flag(r, "IQR", r.log_amt - fence,
                     f"Amount ₹{r.amount:,.0f} exceeds upper fence ₹{math.expm1(fence):,.0f} (Q3 + {k}·IQR, {base})",
                     deviation=round(float(r.amount / max(1.0, math.expm1(fence))), 2))
    # --- Rapid pass-through (possible layering) ---------------------------------------
    win = pd.Timedelta(minutes=settings.fin_rapid_window_min)
    by_sender = {a: g for a, g in t.groupby("account_number")}
    by_holder = {a: g for a, g in t.groupby("sender")}
    chains = []
    for _, r in t.iterrows():
        nxt = pd.concat([by_sender.get(r.counterpart_account, t.iloc[0:0]), by_holder.get(r.receiver, t.iloc[0:0])])
        if nxt.empty:
            continue
        nxt = nxt[(nxt.ts > r.ts) & (nxt.ts <= r.ts + win) & (nxt.amount.between(0.8 * r.amount, 1.02 * r.amount))
                  & (nxt.evidence_id != r.evidence_id)].drop_duplicates("evidence_id")
        for _, n in nxt.iterrows():
            mins = (n.ts - r.ts).total_seconds() / 60
            reason = (f"₹{r.amount:,.0f} received by {r.receiver} and ₹{n.amount:,.0f} sent onward "
                      f"{mins:.0f} min later ({r.evidence_id} → {n.evidence_id})")
            flag(r, "RAPID_PASS_THROUGH", 1.0, reason)
            flag(n, "RAPID_PASS_THROUGH", 1.0, reason)
            chains.append({"in": r.evidence_id, "out": n.evidence_id, "via": r.receiver, "minutes": round(mins, 1),
                           "amountIn": float(r.amount), "amountOut": float(n.amount), "caseId": r.case_id})
        # split pass-through: one inflow forwarded to several accounts within the window
        outs = by_sender.get(r.counterpart_account)
        if outs is not None and r.amount >= 50000:
            o = outs[(outs.ts > r.ts) & (outs.ts <= r.ts + win) & (outs.evidence_id != r.evidence_id)]
            if o.counterpart_account.nunique() >= 2 and o.amount.sum() >= 0.5 * r.amount:
                reason = (f"₹{r.amount:,.0f} received and {o.amount.sum() / r.amount:.0%} of it split to "
                          f"{o.counterpart_account.nunique()} accounts within {settings.fin_rapid_window_min // 60} h")
                flag(r, "RAPID_PASS_THROUGH", 1.0, reason)
                for _, n in o.iterrows():
                    flag(n, "RAPID_PASS_THROUGH", 1.0, reason)
                    chains.append({"in": r.evidence_id, "out": n.evidence_id, "via": r.receiver,
                                   "minutes": round((n.ts - r.ts).total_seconds() / 60, 1), "amountIn": float(r.amount),
                                   "amountOut": float(n.amount), "caseId": r.case_id})
    # --- Structuring --------------------------------------------------------------------
    thr, mn = settings.fin_structuring_threshold, settings.fin_structuring_min_count
    structuring = []
    near = t[(t.amount < thr) & (t.amount >= 0.75 * thr)]
    for (s, rcv), g in near.groupby(["sender", "receiver"]):
        g = g.sort_values("ts")
        for i in range(len(g)):
            w = g[(g.ts >= g.ts.iloc[i]) & (g.ts <= g.ts.iloc[i] + pd.Timedelta(days=14))]
            if len(w) >= mn:
                total = w.amount.sum()
                for _, r in w.iterrows():
                    flag(r, "STRUCTURING", len(w),
                         f"{len(w)} transfers {s} → {rcv} within 14 days, each just below ₹{thr:,.0f} (total ₹{total:,.0f})")
                structuring.append({"sender": s, "receiver": rcv, "count": int(len(w)), "total": float(total),
                                    "evidenceIds": list(w.evidence_id), "caseIds": sorted(set(w.case_id))})
                break
    # --- Fan-in: many distinct individuals paying one personal account in a short window --
    fan_in = []
    inbound = t[t.receiver.fillna("").str.startswith("P") & t.sender.fillna("").str.startswith("P")
                & (t.amount >= 5000) & ~t.purpose.str.lower().str.contains("rent|salary|bill")]
    for rcv, g in inbound.groupby("counterpart_account"):
        g = g.sort_values("ts")
        for i in range(len(g)):
            w = g[(g.ts >= g.ts.iloc[i]) & (g.ts <= g.ts.iloc[i] + pd.Timedelta(days=14))]
            if w.sender.nunique() >= 3:
                for _, r in w.iterrows():
                    flag(r, "FAN_IN", w.sender.nunique(),
                         f"Account {rcv} received ₹{w.amount.sum():,.0f} from {w.sender.nunique()} different individuals "
                         f"within 14 days")
                fan_in.append({"account": rcv, "senders": sorted(w.sender.unique()), "count": int(len(w)),
                               "total": float(w.amount.sum()), "evidenceIds": list(w.evidence_id),
                               "caseIds": sorted(set(w.case_id))})
                break
    # --- Repeated pairs ------------------------------------------------------------------
    pairs = []
    for (s, rcv), g in t.groupby(["sender", "receiver"]):
        if len(g) >= 5 and s and rcv:
            purposes = g.purpose.str.lower().value_counts()
            top = purposes.index[0] if len(purposes) else ""
            benign = any(b in top for b in BENIGN_PURPOSES)
            pairs.append({"sender": s, "receiver": rcv, "count": int(len(g)), "total": float(g.amount.sum()),
                          "first": g.ts.min().strftime("%Y-%m-%d"), "last": g.ts.max().strftime("%Y-%m-%d"),
                          "dominantPurpose": top, "assessment": "consistent with routine payments" if benign else
                          "recurring relationship — review context", "evidenceIds": list(g.evidence_id[:20])})
    # alternative explanations from stated purpose
    for f in flags.values():
        p = (f.get("purpose") or "").lower()
        if any(b in p for b in BENIGN_PURPOSES):
            f["alternativeExplanation"] = f"Stated purpose '{f['purpose']}' may be a legitimate explanation; verify supporting documents."
        f["anomalyScore"] = round(min(1.0, 0.25 * len(f["methods"]) + 0.1 * sum(1 for m in f["methods"] if m in ("STRUCTURING", "RAPID_PASS_THROUGH", "FAN_IN"))), 2)
    out = sorted(flags.values(), key=lambda f: (-len(f["methods"]), -f["amount"]))
    return {"config": {"isolationForest": use_iforest, "iforestContamination": settings.fin_iforest_contamination,
                       "iqr": use_iqr, "iqrK": settings.fin_iqr_k, "rapidWindowMin": settings.fin_rapid_window_min,
                       "structuringThreshold": thr, "structuringMinCount": mn},
            "flagged": out, "chains": chains, "structuring": structuring, "fanIn": fan_in, "repeatedPairs": pairs,
            "disclaimer": "Flags are investigative indicators, not findings of money laundering or any offence."}


def analysis() -> dict:
    return cached("financial:v2", analyse)


def flagged_ids() -> dict[str, dict]:
    return {f["evidenceId"]: f for f in analysis()["flagged"]}


def account_summary(case_id=None, person_id=None) -> list[dict]:
    t = _txns()
    if case_id:
        t = t[t.case_id == case_id]
    flagged = flagged_ids()
    acc = defaultdict(lambda: {"in": 0.0, "out": 0.0, "n": 0, "counterparties": set(), "holders": set(),
                               "flagged": 0, "names": set()})
    for _, r in t.iterrows():
        amt = float(r.amount) if pd.notna(r.amount) else 0.0
        if r.account_number:
            a = acc[r.account_number]; a["out"] += amt; a["n"] += 1; a["counterparties"].add(r.counterpart_account)
            if r.sender: a["holders"].add(r.sender)
            if r.s_name: a["names"].add(r.s_name)
            a["flagged"] += r.evidence_id in flagged
        if r.counterpart_account:
            a = acc[r.counterpart_account]; a["in"] += amt; a["n"] += 1; a["counterparties"].add(r.account_number)
            if r.receiver: a["holders"].add(r.receiver)
            if r.r_name: a["names"].add(r.r_name)
            a["flagged"] += r.evidence_id in flagged
    out = []
    for k, a in acc.items():
        if person_id and person_id not in a["holders"]:
            continue
        out.append({"account": k, "holders": sorted(a["holders"]), "names": sorted(a["names"]), "totalIn": round(a["in"], 2),
                    "totalOut": round(a["out"], 2), "transactions": a["n"], "counterparties": len(a["counterparties"]),
                    "flaggedTransactions": a["flagged"],
                    "sharedHolders": len(a["holders"]) > 1})
    return sorted(out, key=lambda x: -(x["totalIn"] + x["totalOut"]))


def evaluate(ground_truth: dict) -> dict:
    """Precision/recall per detector against generator ground truth (synthetic data only)."""
    truth = {x["evidence_id"] for x in ground_truth.get("fin_anomalies", [])}
    res = {}
    fl = analysis()["flagged"]
    for m in ("ISOLATION_FOREST", "IQR", "RAPID_PASS_THROUGH", "STRUCTURING", "FAN_IN", "ANY"):
        got = {f["evidenceId"] for f in fl if m == "ANY" or m in f["methods"]}
        tp = len(got & truth)
        res[m] = {"flagged": len(got), "truePositives": tp,
                  "precision": round(tp / len(got), 3) if got else None,
                  "recall": round(tp / len(truth), 3) if truth else None}
    res["groundTruthAnomalies"] = len(truth)
    return res
