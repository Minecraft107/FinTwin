"""Spending anomaly detection. Pure functions over the transactions DataFrame.

Transaction level (two independent detectors, combined):
- Robust rule: log-amount robust z-score within the transaction's own category
  (median / MAD), z >= 3.5 and at least 3x the category median.
- Isolation Forest (unsupervised, fitted per user) on [log amount, category z, weekday,
  day of month]; only used with >= 60 expense transactions.
  Both agree -> HIGH (CRITICAL if >= 50% of typical monthly income); rule only -> MEDIUM;
  forest only (and z >= 2.5) -> LOW.
- Duplicates: same date, amount and description (reference numbers kept).

Month level:
- Abnormal month: total spending >= 2 sd above the previous 6 months and, once a year of
  history exists, >= 25% above the same month last year (so festive Octobers or annual
  premium months are not reported as anomalies year after year).
- Category drift: a category's last month vs the 3 before (spike), or its last 3 months vs
  the 3 before (sustained trend).
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.models.enums import Severity
from app.services.ml.categorizer import duplicate_text
from app.utils.money import inr

RULE_Z = 3.5
RULE_MIN_MULTIPLE = 3.0
FOREST_ONLY_Z = 2.5
MIN_CATEGORY_TXNS = 8
MIN_FOREST_TXNS = 60
FOREST_CONTAMINATION = 0.02
MAD_TO_SIGMA = 1.4826
MIN_LOG_SPREAD = 0.1  # floor for MAD on log scale (very regular categories, e.g. fixed bills)
SEASONAL_MARGIN = 1.25
SEVERITY_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}


@dataclass(frozen=True)
class TransactionFlag:
    transaction_id: int
    date: date
    category: str
    description: str
    amount: float
    category_median: float
    z: float
    by_rule: bool
    by_forest: bool
    duplicate: bool
    severity: Severity

    @property
    def high(self) -> bool:
        return SEVERITY_RANK[self.severity] >= SEVERITY_RANK[Severity.HIGH]


def _spending(txns: pd.DataFrame, as_of: date) -> pd.DataFrame:
    df = txns[
        (txns["type"] == "expense")
        & txns["kind"].isin(["essential", "discretionary"])
        & (txns["date"].dt.date <= as_of)
    ].copy()
    if "id" not in df.columns:
        df["id"] = df.index
    return df


def _category_z(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Robust z of log(amount) within each category; NaN for categories with too few rows."""
    log_amount = np.log(df["amount"])
    z = pd.Series(np.nan, index=df.index)
    medians = pd.Series(np.nan, index=df.index)
    for _, idx in df.groupby("category").groups.items():
        if len(idx) < MIN_CATEGORY_TXNS:
            continue
        values = log_amount.loc[idx]
        median = values.median()
        spread = max((values - median).abs().median() * MAD_TO_SIGMA, MIN_LOG_SPREAD)
        z.loc[idx] = (values - median) / spread
        medians.loc[idx] = float(np.exp(median))
    return z, medians


def detect_transaction_anomalies(
    txns: pd.DataFrame, as_of: date, monthly_income: float = 0.0, use_forest: bool = True
) -> list[TransactionFlag]:
    df = _spending(txns, as_of)
    if df.empty:
        return []
    z, medians = _category_z(df)
    rule = (z >= RULE_Z) & (df["amount"] >= RULE_MIN_MULTIPLE * medians)

    forest = pd.Series(False, index=df.index)
    if use_forest and len(df) >= MIN_FOREST_TXNS:
        features = np.column_stack(
            [
                np.log(df["amount"]),
                z.fillna(0.0),
                df["date"].dt.weekday,
                df["date"].dt.day / 31,
            ]
        )
        model = IsolationForest(
            n_estimators=200, contamination=FOREST_CONTAMINATION, random_state=0
        )
        forest = pd.Series(model.fit_predict(features) == -1, index=df.index)

    keys = [
        (d, round(a, 2), duplicate_text(desc))
        for d, a, desc in zip(df["date"], df["amount"], df["description"], strict=True)
    ]
    duplicate = pd.Series(pd.Series(keys, index=df.index).duplicated(keep="first"), index=df.index)

    flags = []
    for idx in df.index:
        by_rule, by_forest, dup = bool(rule[idx]), bool(forest[idx]), bool(duplicate[idx])
        zi = float(z[idx]) if not np.isnan(z[idx]) else 0.0
        amount = float(df.at[idx, "amount"])
        if by_rule and by_forest:
            severity = Severity.HIGH
            if monthly_income and amount >= 0.5 * monthly_income:
                severity = Severity.CRITICAL
        elif by_rule or dup:
            severity = Severity.MEDIUM
        elif by_forest and zi >= FOREST_ONLY_Z:
            severity = Severity.LOW
        else:
            continue
        flags.append(
            TransactionFlag(
                transaction_id=int(df.at[idx, "id"]),
                date=df.at[idx, "date"].date(),
                category=str(df.at[idx, "category"]),
                description=str(df.at[idx, "description"]),
                amount=amount,
                category_median=float(medians[idx]) if not np.isnan(medians[idx]) else 0.0,
                z=zi,
                by_rule=by_rule,
                by_forest=by_forest,
                duplicate=dup,
                severity=severity,
            )
        )
    return flags


def recent_high_count(flags: list[TransactionFlag], as_of: date, days: int = 30) -> int:
    """HIGH/CRITICAL transaction anomalies in the `days` before `as_of` (health-score input)."""
    start = as_of - timedelta(days=days)
    return sum(1 for f in flags if f.high and start < f.date <= as_of)


def monthly_spending(txns: pd.DataFrame, last_month: pd.Period) -> pd.DataFrame:
    df = _spending(txns, last_month.to_timestamp(how="end").date())
    if df.empty:
        return pd.DataFrame()
    table = df.assign(month=df["date"].dt.to_period("M")).pivot_table(
        index="month", columns="category", values="amount", aggfunc="sum"
    )
    index = pd.period_range(table.index.min(), last_month, freq="M")
    return table.reindex(index).fillna(0.0)


def abnormal_months(monthly: pd.DataFrame, min_prior: int = 6) -> list[tuple[pd.Period, float]]:
    """(month, z) for months whose total spending is >= 2 sd above the previous 6 months and,
    with a year of history, >= SEASONAL_MARGIN x the same month last year."""
    totals = monthly.sum(axis=1)
    out = []
    for i in range(min_prior, len(totals)):
        prior = totals.iloc[i - min_prior : i]
        spread = max(prior.std(), 0.05 * prior.mean())
        z = (totals.iloc[i] - prior.mean()) / spread if spread else 0.0
        seasonal = i >= 12 and totals.iloc[i] < SEASONAL_MARGIN * totals.iloc[i - 12]
        if z >= 2 and not seasonal:
            out.append((totals.index[i], float(z)))
    return out


@dataclass(frozen=True)
class Drift:
    category: str
    kind: str  # "spike" | "trend"
    recent: float  # last month, or average of the last 3
    baseline: float  # average of the comparison window
    change: float  # fraction, 0.46 = +46%
    severity: Severity


def category_drift(monthly: pd.DataFrame, min_increase: float = 2_000) -> list[Drift]:
    drifts = []
    if len(monthly) < 4:
        return drifts
    for category in monthly.columns:
        series = monthly[category]
        found = None
        if len(series) >= 6:
            recent, baseline = series.iloc[-3:].mean(), series.iloc[-6:-3].mean()
            if baseline > 0 and recent - baseline >= min_increase and recent / baseline >= 1.25:
                change = recent / baseline - 1
                severity = Severity.HIGH if change >= 0.75 else Severity.MEDIUM
                found = Drift(category, "trend", recent, baseline, change, severity)
        if found is None:
            recent, baseline = series.iloc[-1], series.iloc[-4:-1].mean()
            if baseline > 0 and recent - baseline >= min_increase and recent / baseline >= 1.30:
                change = recent / baseline - 1
                severity = Severity.HIGH if change >= 0.75 else Severity.MEDIUM
                found = Drift(category, "spike", recent, baseline, change, severity)
        if found:
            drifts.append(found)
    return drifts


def describe_flag(flag: TransactionFlag) -> tuple[str, str, str]:
    """(title, explanation, recommended action) for a transaction anomaly."""
    if flag.duplicate and not flag.by_rule:
        return (
            f"Possible duplicate charge: {inr(flag.amount)}",
            f"Two identical {flag.category} charges of {inr(flag.amount)} "
            f"('{flag.description}') were recorded on {flag.date.isoformat()}.",
            "Check your statement; if you were charged twice, request a refund from the merchant.",
        )
    multiple = flag.amount / flag.category_median if flag.category_median else None
    detectors = " and ".join(
        name
        for name, hit in (("statistical rule", flag.by_rule), ("Isolation Forest", flag.by_forest))
        if hit
    )
    explanation = f"{inr(flag.amount)} on {flag.date.isoformat()} ('{flag.description}')"
    if multiple:
        explanation += (
            f" is {multiple:.1f}× your typical {flag.category} transaction "
            f"({inr(flag.category_median)})"
        )
    explanation += f". Flagged by: {detectors}."
    return (
        f"Unusually large {flag.category} expense",
        explanation,
        "If this was planned, no action is needed. If not, verify it, and consider planning "
        "large purchases ahead so they don't disrupt monthly cash flow.",
    )
