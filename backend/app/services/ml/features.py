"""Feature engineering shared by offline training (ml/) and online inference, so the two
can never diverge. Everything works on a month × category matrix of consumption spending."""

import numpy as np
import pandas as pd

from app.models.enums import CategoryKind
from app.seed.categories import CATEGORIES

# Consumption categories only: EMIs and SIPs are scheduled, not forecast statistically.
FORECAST_CATEGORIES = [
    name
    for name, kind, *_ in CATEGORIES
    if kind in (CategoryKind.ESSENTIAL, CategoryKind.DISCRETIONARY)
]
CATEGORY_CODE = {name: i for i, name in enumerate(FORECAST_CATEGORIES)}
FESTIVE_MONTHS = (10, 11)
LAGS = (1, 2, 3, 6, 12)
FEATURE_NAMES = [
    *(f"lag{k}" for k in LAGS),
    "mean3",
    "mean6",
    "std3",
    "month_sin",
    "month_cos",
    "festive",
    "category",
]


def category_month_matrix(txns: pd.DataFrame, end: pd.Period) -> pd.DataFrame:
    """Monthly consumption spend per category, from the first month with data to `end`
    (inclusive), zero-filled. Rows: PeriodIndex (M); columns: FORECAST_CATEGORIES."""
    spend = txns[txns["kind"].isin(["essential", "discretionary"])]
    if spend.empty:
        return pd.DataFrame(columns=FORECAST_CATEGORIES, dtype=float)
    months = spend["date"].dt.to_period("M")
    spend = spend[months <= end]
    if spend.empty:
        return pd.DataFrame(columns=FORECAST_CATEGORIES, dtype=float)
    table = spend.assign(month=spend["date"].dt.to_period("M")).pivot_table(
        index="month", columns="category", values="amount", aggfunc="sum"
    )
    index = pd.period_range(table.index.min(), end, freq="M")
    return table.reindex(index=index, columns=FORECAST_CATEGORIES).fillna(0.0).astype(float)


def scale_of(history: np.ndarray) -> float:
    """Per-series scale so one global model can serve users with very different incomes."""
    recent = history[-6:]
    for candidate in (
        recent.mean() if len(recent) else 0.0,
        history.mean() if len(history) else 0.0,
    ):
        if candidate > 0:
            return float(candidate)
    return 1.0


def feature_row(history: np.ndarray, target: pd.Period, category: str) -> tuple[list[float], float]:
    """Features (scaled by the series' own recent level) for predicting `target` from
    `history` (values strictly before `target`, oldest first). Returns (features, scale)."""
    scale = scale_of(history)
    h = history / scale

    def lag(k: int) -> float:
        return float(h[-k]) if len(h) >= k else np.nan

    angle = 2 * np.pi * (target.month - 1) / 12
    row = [
        *(lag(k) for k in LAGS),
        float(h[-3:].mean()),
        float(h[-6:].mean()),
        float(h[-3:].std()),
        float(np.sin(angle)),
        float(np.cos(angle)),
        float(target.month in FESTIVE_MONTHS),
        float(CATEGORY_CODE[category]),
    ]
    return row, scale


def training_rows(
    matrix: pd.DataFrame, min_history: int = 3
) -> tuple[list[list[float]], list[float]]:
    """(X, y) for every (category, month) with at least `min_history` prior months.
    y is the scaled target, matching what the model predicts at inference time."""
    X, y = [], []
    values = matrix.to_numpy()
    for j, category in enumerate(matrix.columns):
        series = values[:, j]
        if not series.any():
            continue
        for t in range(min_history, len(series)):
            if not series[:t].any():
                # No spend yet: the scale is undefined (would fall back to 1 and turn a first
                # ₹2,000 purchase into a target of 2,000x). Inference skips these series too.
                continue
            row, scale = feature_row(series[:t], matrix.index[t], category)
            X.append(row)
            y.append(series[t] / scale)
    return X, y
