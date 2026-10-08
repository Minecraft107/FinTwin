"""Evaluate anomaly detection against the generator's injected, labelled anomalies.

Detection is unsupervised (nothing is trained on labels); the labels are used only to score.
Transaction level: positives are injected large purchases and duplicate charges.
Month level: positives are months containing injected unusual spending (a travel-heavy
month or a large one-off purchase); scored overall and on months with >= 12 months of
history (where the seasonal same-month-last-year check can apply).

Caveat (stated in docs/ml.md): synthetic spending also has natural heavy tails (lognormal
amounts, festive spikes, annual premiums), so some "false positives" are genuinely unusual
but unlabelled transactions — precision is a pessimistic estimate in that sense, and recall
an optimistic one because injected anomalies are fairly pronounced.
"""

import pandas as pd

import ml  # noqa: F401
from app.models.enums import Severity
from app.services.analytics.anomalies import (
    abnormal_months,
    detect_transaction_anomalies,
    monthly_spending,
)

TXN_LABELS = {"large_purchase", "duplicate"}


def _prf(predicted: set, actual: set) -> dict:
    tp = len(predicted & actual)
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(actual) if actual else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "flagged": len(predicted),
        "true_positives": tp,
        "labelled": len(actual),
    }


def evaluate(population: pd.DataFrame) -> dict:
    end = population["date"].max().date()
    last_month = pd.Period(end, "M")
    variants = {k: set() for k in ("production", "rule", "forest", "rule_and_forest", "duplicate")}
    labels = set(population.loc[population["anomaly"].isin(TXN_LABELS), "id"])
    labels_by_type = {t: set(population.loc[population["anomaly"] == t, "id"]) for t in TXN_LABELS}
    month_pred, month_actual, mature = set(), set(), set()

    for user_id, frame in population.groupby("user_id"):
        income = (
            frame.loc[frame["type"] == "income", "amount"].sum()
            / frame["date"].dt.to_period("M").nunique()
        )
        for f in detect_transaction_anomalies(frame, end, income):
            if f.severity != Severity.LOW:
                variants["production"].add(f.transaction_id)
            if f.by_rule:
                variants["rule"].add(f.transaction_id)
            if f.by_forest:
                variants["forest"].add(f.transaction_id)
            if f.by_rule and f.by_forest:
                variants["rule_and_forest"].add(f.transaction_id)
            if f.duplicate:
                variants["duplicate"].add(f.transaction_id)

        monthly = monthly_spending(frame, last_month)
        evaluable = set(monthly.index[6:])  # abnormal_months needs 6 prior months
        mature |= {(user_id, m) for m in monthly.index[12:]}
        labelled_months = set(
            frame.loc[
                frame["anomaly"].isin(["abnormal_month", "large_purchase"]), "date"
            ].dt.to_period("M")
        )
        month_actual |= {(user_id, m) for m in labelled_months & evaluable}
        month_pred |= {(user_id, m) for m, _ in abnormal_months(monthly)}

    production = variants["production"]
    return {
        "protocol": "Unsupervised per-user detection on the synthetic population; injected "
        "anomalies used only as ground truth",
        "users": int(population["user_id"].nunique()),
        "transactions": len(population),
        "transaction_level": {
            "production (MEDIUM+ alerts)": _prf(production, labels),
            "robust rule only": _prf(variants["rule"], labels_by_type["large_purchase"]),
            "isolation forest only": _prf(variants["forest"], labels_by_type["large_purchase"]),
            "rule AND forest (HIGH)": _prf(
                variants["rule_and_forest"], labels_by_type["large_purchase"]
            ),
            "duplicate detector": _prf(variants["duplicate"], labels_by_type["duplicate"]),
        },
        "recall_by_type": {
            t: round(len(production & ids) / len(ids), 4) if ids else None
            for t, ids in labels_by_type.items()
        },
        "month_level": {
            "all evaluable months": _prf(month_pred, month_actual),
            "months with 12+ months of history": _prf(month_pred & mature, month_actual & mature),
        },
    }
