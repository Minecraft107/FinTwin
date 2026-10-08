"""Expense and cash-flow forecasting with per-user, evidence-based model selection.

Every eligible model is scored by a rolling-origin backtest on the user's own recent months
(one-step-ahead error on total spending). Champion-challenger rule: when the global XGBoost
model is available it is the champion, and a baseline replaces it only if its backtest MAE
is below CHALLENGER_MARGIN × XGBoost's, i.e. strong evidence that the synthetic-trained model
does not fit this user. Without XGBoost the lowest-MAE baseline wins. (Offline evaluation in
ml/ measures exactly this rule; see docs/ml.md.)

Uncertainty is an empirical ~80% band from the backtest residuals, widening with horizon.
"""

import logging
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.digital_twin.builder import build_twin, cash_balance
from app.services.digital_twin.state import UserData
from app.services.forecasting.models import MODELS, MODELS_BY_KEY, ModelSpec
from app.services.ml.artifacts import load_artifact
from app.services.ml.features import category_month_matrix
from app.utils.dates import last_complete_month_end, months_between
from app.utils.money import inr

logger = logging.getLogger(__name__)

CHALLENGER_MARGIN = 0.8
Z80 = 1.2816  # two-sided 80% normal quantile
HEURISTIC_BAND = 0.20  # used only when there is too little history to backtest
# A 3-6 point backtest can show ~zero error on a very steady history; never claim more
# certainty than ±5% of recent monthly spending per step.
MIN_SIGMA_SHARE = 0.05


@dataclass(frozen=True)
class Backtest:
    model: ModelSpec
    mae: float
    rmse: float
    mape: float | None


def backtest_origins(months: int) -> int:
    """More origins give a steadier comparison; short histories can only afford 3."""
    return 6 if months >= 12 else 3


def backtest(model: ModelSpec, matrix: pd.DataFrame, origins: int) -> Backtest:
    errors, actuals = [], []
    for k in range(origins, 0, -1):
        train, actual = matrix.iloc[:-k], float(matrix.iloc[-k].sum())
        predicted = float(model.forecast(train, 1).iloc[0].sum())
        errors.append(predicted - actual)
        actuals.append(actual)
    errors_arr = np.array(errors)
    mape = (
        float(np.mean(np.abs(errors_arr) / np.array(actuals)))
        if all(a > 0 for a in actuals)
        else None
    )
    return Backtest(
        model,
        float(np.abs(errors_arr).mean()),
        float(np.sqrt((errors_arr**2).mean())),
        mape,
    )


def select_model(
    candidates: list[ModelSpec], matrix: pd.DataFrame
) -> tuple[Backtest | None, list[Backtest]]:
    """Champion-challenger selection (see module docstring). Shared with the offline
    evaluation so the reported accuracy is the accuracy of this exact rule."""
    origins = backtest_origins(len(matrix))
    results = []
    for model in candidates:
        if len(matrix) < model.min_history + origins:
            continue
        try:
            results.append(backtest(model, matrix, origins))
        except Exception:
            logger.exception("Backtest failed for %s", model.key)
    if not results:
        return None, []
    best = min(results, key=lambda b: b.mae)  # list order breaks ties toward simpler models
    champion = next((b for b in results if b.model.key == "xgboost"), None)
    if champion and best is not champion and best.mae >= CHALLENGER_MARGIN * champion.mae:
        best = champion
    return best, results


def _available_models() -> list[ModelSpec]:
    has_xgb = load_artifact("forecaster") is not None
    return [m for m in MODELS if has_xgb or not m.needs_artifact]


def _confidence(months: int, mape: float | None) -> str:
    if months >= 12 and mape is not None and mape < 0.10:
        return "high"
    if months >= 6 and mape is not None and mape < 0.20:
        return "medium"
    return "low"


@dataclass(frozen=True)
class ExpenseForecast:
    matrix: pd.DataFrame  # history used (complete months)
    forecast: pd.DataFrame  # horizon × category
    model: ModelSpec | None
    sigma: float | None  # one-step RMSE of total spending
    band: list[tuple[float, float]]  # (lower, upper) per horizon step
    backtests: list[Backtest]
    confidence: str
    notes: list[str]


def forecast_expense_matrix(data: UserData, horizon: int) -> ExpenseForecast | None:
    end = pd.Period(last_complete_month_end(data.today), "M")
    matrix = category_month_matrix(data.transactions, end)
    months = len(matrix)
    if months == 0:
        return None
    notes = []
    best, backtests = select_model(_available_models(), matrix)
    if best:
        model = best.model
        sigma = max(best.rmse, MIN_SIGMA_SHARE * float(matrix.sum(axis=1).tail(3).mean()))
        confidence = _confidence(months, best.mape)
    else:
        model = next(m for m in reversed(MODELS[:2]) if months >= m.min_history)
        sigma, confidence = None, "low"
        notes.append(
            f"Only {months} complete month(s) of history: no backtest was possible, so the "
            "range shown is a ±20% rule of thumb. More history will improve accuracy."
        )
    try:
        forecast = model.forecast(matrix, horizon)
    except Exception:
        logger.exception("Forecast failed for %s; falling back to moving average", model.key)
        model = MODELS_BY_KEY["moving_average" if months >= 3 else "naive"]
        forecast = model.forecast(matrix, horizon)
        notes.append("The selected model failed; a simpler fallback model was used.")
    totals = forecast.sum(axis=1).to_numpy()
    if sigma is not None:
        band = [
            (max(t - Z80 * sigma * math.sqrt(h), 0.0), t + Z80 * sigma * math.sqrt(h))
            for h, t in enumerate(totals.tolist(), start=1)
        ]
    else:
        band = [(t * (1 - HEURISTIC_BAND), t * (1 + HEURISTIC_BAND)) for t in totals.tolist()]
    if months < 12:
        notes.append("Less than a year of history: seasonal patterns (festivals, annual "
                     "premiums) cannot be learned yet.")  # fmt: skip
    return ExpenseForecast(matrix, forecast, model, sigma, band, backtests, confidence, notes)


def _history_points(matrix: pd.DataFrame, months: int = 12) -> list[dict]:
    totals = matrix.sum(axis=1).tail(months)
    return [{"month": str(p), "value": round(float(v), 2)} for p, v in totals.items()]


def _model_info(ef: ExpenseForecast) -> dict:
    return {
        "selected": ef.model.key,
        "label": ef.model.label,
        "backtest": [
            {
                "model": b.model.key,
                "label": b.model.label,
                "mae": round(b.mae, 2),
                "rmse": round(b.rmse, 2),
                "mape": None if b.mape is None else round(b.mape, 4),
            }
            for b in sorted(ef.backtests, key=lambda b: b.mae)
        ],
        "backtest_origins": backtest_origins(len(ef.matrix)) if ef.backtests else 0,
        "selection_rule": "XGBoost unless a baseline's backtest error is at least 20% lower"
        if any(b.model.key == "xgboost" for b in ef.backtests)
        else "lowest backtest error",
    }


INSUFFICIENT = {
    "status": "insufficient_data",
    "message": "Forecasts need at least one complete month of transactions. If more "
    "historical data is available, prediction confidence will improve.",
}


def forecast_expenses(data: UserData, horizon: int = 3) -> dict:
    ef = forecast_expense_matrix(data, horizon)
    if ef is None:
        return INSUFFICIENT | {"horizon": horizon}
    totals = ef.forecast.sum(axis=1)
    recent_avg = ef.matrix.tail(3).mean()
    first = ef.forecast.iloc[0]
    categories = sorted(
        (
            {
                "category": c,
                "forecast": round(float(first[c]), 2),
                "recent_average": round(float(recent_avg[c]), 2),
                "change_pct": round((first[c] - recent_avg[c]) / recent_avg[c] * 100, 1)
                if recent_avg[c] > 0
                else None,
            }
            for c in ef.forecast.columns
            if first[c] > 0 or recent_avg[c] > 0
        ),
        key=lambda r: r["forecast"],
        reverse=True,
    )
    first_month = str(totals.index[0])
    lower, upper = ef.band[0]
    mae = next((b.mae for b in ef.backtests if b.model is ef.model), None)
    explanation = (
        f"Spending for {first_month} is estimated at {inr(totals.iloc[0])} "
        f"(likely range {inr(lower)}–{inr(upper)}), based on your last {len(ef.matrix)} "
        f"complete month(s). Model: {ef.model.label}"
    )
    explanation += (
        f" (average miss {inr(mae)} when it predicted your last "
        f"{backtest_origins(len(ef.matrix))} months)."
        if mae is not None
        else "."
    )
    movers = [c for c in categories if c["change_pct"] is not None and abs(c["change_pct"]) >= 20]
    if movers:
        top = max(movers, key=lambda c: abs(c["forecast"] - c["recent_average"]))
        direction = "higher" if top["change_pct"] > 0 else "lower"
        explanation += (
            f" {top['category']} is expected to be {abs(top['change_pct']):.0f}% {direction} "
            "than its recent average."
        )
    return {
        "status": "ok",
        "horizon": horizon,
        "model": _model_info(ef),
        "confidence": ef.confidence,
        "history": _history_points(ef.matrix),
        "forecast": [
            {
                "month": str(p),
                "value": round(float(t), 2),
                "lower": round(lo, 2),
                "upper": round(hi, 2),
            }  # fmt: skip
            for (p, t), (lo, hi) in zip(totals.items(), ef.band, strict=True)
        ],
        "categories": categories,
        "explanation": explanation,
        "notes": ef.notes,
        "disclaimer": "Forecasts are statistical estimates based on your past spending, "
        "not guarantees.",
    }


def _scheduled_emis(data: UserData, month: pd.Period) -> float:
    total = 0.0
    for loan in data.loans:
        paid = months_between(loan.start_date, month.to_timestamp().date())
        if 0 <= paid < loan.tenure_months and loan.outstanding > 0:
            total += loan.emi
    return total


def forecast_cash_flow(data: UserData, horizon: int = 6) -> dict:
    ef = forecast_expense_matrix(data, horizon)
    if ef is None:
        return INSUFFICIENT | {"horizon": horizon}
    twin = build_twin(data)
    income_history = (
        data.transactions[data.transactions["type"] == "income"]
        .assign(month=lambda d: d["date"].dt.to_period("M"))
        .groupby("month")["amount"]
        .sum()
        .reindex(ef.matrix.index, fill_value=0.0)
    )
    # Median of recent months: robust to one-off bonuses and freelance spikes.
    income = float(income_history.tail(3).median())
    sips = twin.investment_contributions
    uses_loans = bool(data.loans)
    start_balance = cash_balance(data, ef.matrix.index[-1].to_timestamp(how="end").date())
    balance = start_balance
    cumulative_var = 0.0
    points = []
    for h, (period, row) in enumerate(ef.forecast.iterrows(), start=1):
        expenses = float(row.sum())
        emi = _scheduled_emis(data, period) if uses_loans else twin.debt_payments
        net = income - expenses - emi - sips
        balance += net
        lower, upper = ef.band[h - 1]
        step_sigma = ef.sigma if ef.sigma is not None else expenses * HEURISTIC_BAND / Z80
        cumulative_var += step_sigma**2
        spread = Z80 * math.sqrt(cumulative_var)
        points.append(
            {
                "month": str(period),
                "income": round(income, 2),
                "expenses": round(expenses, 2),
                "emi": round(emi, 2),
                "investments": round(sips, 2),
                "net_cash_flow": round(net, 2),
                "net_lower": round(income - upper - emi - sips, 2),
                "net_upper": round(income - lower - emi - sips, 2),
                "cash_balance": round(balance, 2),
                "cash_lower": round(balance - spread, 2),
                "cash_upper": round(balance + spread, 2),
            }
        )
    negative = [p["month"] for p in points if p["net_cash_flow"] < 0]
    explanation = (
        f"Projected monthly cash flow is about {inr(points[0]['net_cash_flow'])}: income of "
        f"{inr(income)} (median of recent months) minus forecast spending, EMIs and SIPs. "
        f"Your cash balance is projected to reach {inr(points[-1]['cash_balance'])} by "
        f"{points[-1]['month']} (likely range {inr(points[-1]['cash_lower'])}–"
        f"{inr(points[-1]['cash_upper'])})."
    )
    if negative:
        explanation += f" Cash flow is projected to be negative in {', '.join(negative)}."
    notes = list(ef.notes)
    notes.append("Income is projected at its recent median, so one-off bonuses are not "
                 "assumed to repeat.")  # fmt: skip
    return {
        "status": "ok",
        "horizon": horizon,
        "model": _model_info(ef),
        "confidence": ef.confidence,
        "starting_balance": round(start_balance, 2),
        "starting_balance_as_of": str(ef.matrix.index[-1].to_timestamp(how="end").date()),
        "history": [
            {
                "month": str(p),
                "income": round(float(income_history[p]), 2),
                "expenses": round(float(ef.matrix.loc[p].sum()), 2),
            }  # fmt: skip
            for p in ef.matrix.index[-12:]
        ],
        "forecast": points,
        "explanation": explanation,
        "notes": notes,
        "disclaimer": "Projections are estimates that assume your recent patterns continue.",
    }
