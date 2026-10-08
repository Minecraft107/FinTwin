"""Forecasting models over a month × category spending matrix.

Every model has the same signature: (matrix, horizon) -> DataFrame(horizon months × categories).
Baselines are applied per category; the global XGBoost model is trained offline (ml/) on a
synthetic population and forecasts recursively, feeding its own predictions back as lags.
"""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from app.services.ml.artifacts import load_artifact
from app.services.ml.features import feature_row

Forecaster = Callable[[pd.DataFrame, int], pd.DataFrame]


def _future_index(matrix: pd.DataFrame, horizon: int) -> pd.PeriodIndex:
    return pd.period_range(matrix.index[-1] + 1, periods=horizon, freq="M")


def _per_series(fn: Callable[[np.ndarray, int], np.ndarray]) -> Forecaster:
    def forecast(matrix: pd.DataFrame, horizon: int) -> pd.DataFrame:
        values = {c: fn(matrix[c].to_numpy(), horizon) for c in matrix.columns}
        return pd.DataFrame(values, index=_future_index(matrix, horizon)).clip(lower=0)

    return forecast


def naive(y: np.ndarray, horizon: int) -> np.ndarray:
    return np.repeat(y[-1], horizon)


def moving_average(y: np.ndarray, horizon: int, window: int = 3) -> np.ndarray:
    return np.repeat(y[-window:].mean(), horizon)


def seasonal_naive(y: np.ndarray, horizon: int) -> np.ndarray:
    """Same month last year (captures festive spikes, annual premiums)."""
    return np.array([y[len(y) - 12 + (h % 12)] for h in range(horizon)])


def _holt_path(y: np.ndarray, alpha: float, beta: float, phi: float) -> tuple[float, float, float]:
    """One-step-ahead SSE plus final level/trend for damped-trend Holt smoothing."""
    level, trend, sse = y[0], y[1] - y[0], 0.0
    for value in y[1:]:
        prediction = level + phi * trend
        sse += (value - prediction) ** 2
        new_level = alpha * value + (1 - alpha) * prediction
        trend = beta * (new_level - level) + (1 - beta) * phi * trend
        level = new_level
    return sse, level, trend


HOLT_GRID = list(product((0.2, 0.4, 0.6, 0.8), (0.05, 0.2), (0.85, 0.95)))


def holt_damped(y: np.ndarray, horizon: int) -> np.ndarray:
    """Damped-trend exponential smoothing; parameters picked by in-sample one-step SSE."""
    _, level, trend, phi = min(
        ((*_holt_path(y, a, b, p), p) for a, b, p in HOLT_GRID), key=lambda r: r[0]
    )
    damping = np.cumsum([phi**k for k in range(1, horizon + 1)])
    return level + damping * trend


def xgb_forecaster(model) -> Forecaster:
    """Wrap a trained regressor (predicting scaled next-month spend) as a recursive forecaster."""

    def forecast(matrix: pd.DataFrame, horizon: int) -> pd.DataFrame:
        return _xgb_recursive(model, matrix, horizon)

    return forecast


def xgboost_global(matrix: pd.DataFrame, horizon: int) -> pd.DataFrame:
    model = load_artifact("forecaster")
    if model is None:
        raise RuntimeError("XGBoost forecaster artifact is not available")
    return _xgb_recursive(model, matrix, horizon)


def _xgb_recursive(model, matrix: pd.DataFrame, horizon: int) -> pd.DataFrame:
    history = {c: list(matrix[c].to_numpy()) for c in matrix.columns}
    index = _future_index(matrix, horizon)
    out = {c: [] for c in matrix.columns}
    for target in index:
        active = [c for c in matrix.columns if any(history[c])]
        if active:
            rows, scales = zip(
                *(feature_row(np.array(history[c]), target, c) for c in active), strict=True
            )
            predictions = model.predict(np.array(rows, dtype=float)) * np.array(scales)
            predicted = dict(zip(active, np.maximum(predictions, 0.0), strict=True))
        else:
            predicted = {}
        for c in matrix.columns:
            value = float(predicted.get(c, 0.0))
            out[c].append(value)
            history[c].append(value)
    return pd.DataFrame(out, index=index)


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    min_history: int  # months of history needed to produce a forecast
    forecast: Forecaster
    needs_artifact: bool = False


# Ordered simplest-first: on equal backtest error the simpler model wins.
MODELS = [
    ModelSpec("naive", "Last month (naive)", 1, _per_series(naive)),
    ModelSpec("moving_average", "3-month moving average", 3, _per_series(moving_average)),
    ModelSpec("seasonal_naive", "Same month last year", 12, _per_series(seasonal_naive)),
    ModelSpec("holt", "Damped-trend exponential smoothing", 6, _per_series(holt_damped)),
    ModelSpec("xgboost", "XGBoost (global model)", 3, xgboost_global, needs_artifact=True),
]
MODELS_BY_KEY = {m.key: m for m in MODELS}
