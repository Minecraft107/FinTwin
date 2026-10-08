from datetime import date

import joblib
import numpy as np
import pandas as pd
import pytest
from xgboost import XGBRegressor

from app.extensions import db
from app.models import ForecastResult, User
from app.seed.demo import seed_demo
from app.services.digital_twin.state import LoanData, UserData
from app.services.forecasting import models as fm
from app.services.forecasting.service import (
    backtest_origins,
    forecast_cash_flow,
    forecast_expenses,
    select_model,
)
from app.services.ml.features import (
    FEATURE_NAMES,
    FORECAST_CATEGORIES,
    category_month_matrix,
    feature_row,
    training_rows,
)
from tests.conftest import ApiClient
from tests.test_twin_builder import frame

TODAY = date(2026, 10, 8)


def matrix(
    values: list[float], category: str = "Groceries", start: str = "2024-01"
) -> pd.DataFrame:
    index = pd.period_range(start, periods=len(values), freq="M")
    m = pd.DataFrame(0.0, index=index, columns=FORECAST_CATEGORIES)
    m[category] = values
    return m


def monthly_rows(amounts: list[float], start: date, category="Groceries", income=100_000):
    rows = []
    for i, amount in enumerate(amounts):
        month = pd.Period(start, "M") + i
        rows.append((f"{month}-01", income, "Salary"))
        rows.append((f"{month}-10", amount, category))
    return rows


# ---------------- baselines ----------------


def test_baselines_on_known_series():
    y = np.array([10.0, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130])
    assert list(fm.naive(y, 2)) == [130, 130]
    assert list(fm.moving_average(y, 1)) == [120]
    assert list(fm.seasonal_naive(y, 3)) == [20, 30, 40]  # same months one year earlier


def test_holt_follows_trend_and_damps():
    trend = np.arange(1, 13) * 1_000.0
    path = fm.holt_damped(trend, 3)
    assert 12_000 < path[0] < 13_500
    assert path[0] < path[1] < path[2]
    assert path[2] - path[1] < path[1] - path[0]  # damped
    flat = fm.holt_damped(np.full(12, 5_000.0), 3)
    assert np.allclose(flat, 5_000)


def test_forecasts_never_negative():
    falling = matrix([10_000, 6_000, 2_000, 100, 50, 10, 5, 1])
    for model in fm.MODELS[:4]:
        if len(falling) >= model.min_history:
            assert (model.forecast(falling, 3) >= 0).all().all()


# ---------------- features ----------------


def test_category_matrix_excludes_emis_and_investments():
    rows = [
        ("2026-01-05", 1_000, "Groceries"),
        ("2026-03-05", 500, "Shopping"),
        ("2026-03-06", 9_999, "EMI/Debt"),
        ("2026-03-07", 5_000, "Investment"),
        ("2026-04-02", 700, "Groceries"),  # after `end`
    ]
    m = category_month_matrix(frame(rows), pd.Period("2026-03", "M"))
    assert list(m.index.astype(str)) == ["2026-01", "2026-02", "2026-03"]
    assert m.loc["2026-02"].sum() == 0  # empty month zero-filled
    assert m.to_numpy().sum() == 1_500
    assert "EMI/Debt" not in m.columns


def test_feature_row_is_scale_free():
    small, scale_small = feature_row(
        np.array([100.0, 200, 300]), pd.Period("2026-11", "M"), "Shopping"
    )
    big, scale_big = feature_row(
        np.array([1_000.0, 2_000, 3_000]), pd.Period("2026-11", "M"), "Shopping"
    )
    assert scale_big == 10 * scale_small
    assert np.allclose(small[:3], big[:3])  # lags identical after scaling
    assert np.isnan(small[FEATURE_NAMES.index("lag12")])
    assert small[FEATURE_NAMES.index("festive")] == 1.0


def test_training_rows_skip_series_without_prior_spend():
    m = matrix([0, 0, 0, 0, 2_000, 2_000], category="Education")
    X, y = training_rows(m)
    assert len(X) == 1  # only the month after the first spend has a defined scale
    assert y[0] == pytest.approx(2_000 / 400)  # scale = mean of the last 6 months (0,0,0,0,2000)


# ---------------- model selection ----------------


def fake(key: str, value: float) -> fm.ModelSpec:
    def forecast(m: pd.DataFrame, horizon: int) -> pd.DataFrame:
        index = pd.period_range(m.index[-1] + 1, periods=horizon, freq="M")
        out = pd.DataFrame(0.0, index=index, columns=m.columns)
        out["Groceries"] = value
        return out

    return fm.ModelSpec(key, key, 1, forecast)


def test_selection_prefers_lowest_error_and_simplest_on_ties():
    trend = matrix([1_000.0 + 100 * i for i in range(12)])
    best, results = select_model(fm.MODELS[:4], trend)
    assert best.model.key == "holt"
    assert {r.model.key for r in results} == {"naive", "moving_average", "holt"}  # 12 < 12+6
    flat = matrix([5_000.0] * 12)
    assert select_model(fm.MODELS[:4], flat)[0].model.key == "naive"


@pytest.mark.parametrize("baseline_value,expected", [(5_000, "baseline"), (5_900, "xgboost")])
def test_champion_challenger_margin(baseline_value, expected):
    m = matrix([5_000.0] * 12)  # actual every month = 5,000
    xgb = fake("xgboost", 6_000)  # MAE 1,000
    baseline = fake("baseline", baseline_value)  # MAE 0 (wins) or 900 (< 20% better: keep xgb)
    assert select_model([baseline, xgb], m)[0].model.key == expected


def test_backtest_origins_grow_with_history():
    assert backtest_origins(8) == 3 and backtest_origins(12) == 6


# ---------------- service ----------------


def test_no_history_is_insufficient():
    out = forecast_expenses(UserData(today=TODAY), 3)
    assert out["status"] == "insufficient_data"
    assert "more historical data" in out["message"]


def test_short_history_uses_heuristic_band():
    data = UserData(transactions=frame(monthly_rows([5_000, 6_000], date(2026, 8, 1))), today=TODAY)
    out = forecast_expenses(data, 2)
    assert out["status"] == "ok"
    assert out["model"]["backtest"] == [] and out["confidence"] == "low"
    first = out["forecast"][0]
    assert first["lower"] == pytest.approx(first["value"] * 0.8)
    assert any("rule of thumb" in n for n in out["notes"])


def test_long_history_band_widens_with_horizon():
    rng = np.random.default_rng(0)
    amounts = list(20_000 + rng.normal(0, 1_500, 24))
    data = UserData(transactions=frame(monthly_rows(amounts, date(2024, 10, 1))), today=TODAY)
    out = forecast_expenses(data, 3)
    widths = [p["upper"] - p["lower"] for p in out["forecast"]]
    assert widths[0] < widths[1] < widths[2]
    assert all(p["lower"] >= 0 for p in out["forecast"])
    assert out["model"]["selected"] in {"naive", "moving_average", "seasonal_naive", "holt"}
    assert out["history"][-1]["month"] == "2026-09"
    assert out["forecast"][0]["month"] == "2026-10"


def test_cash_flow_uses_median_income_and_ends_emis():
    rows = monthly_rows([30_000] * 6, date(2026, 4, 1))
    rows.append(("2026-06-15", 200_000, "Salary"))  # one-off bonus must not repeat
    loan = LoanData(principal=60_000, outstanding=10_000, annual_interest_rate=0.0, emi=5_000,
                    tenure_months=12, start_date=date(2025, 11, 1))  # fmt: skip
    data = UserData(transactions=frame(rows), loans=[loan], today=TODAY)
    out = forecast_cash_flow(data, 3)
    points = out["forecast"]
    assert points[0]["income"] == 100_000
    assert [p["emi"] for p in points] == [5_000, 0, 0]  # 12-month tenure ends in Oct 2026
    assert points[1]["cash_balance"] == pytest.approx(
        points[0]["cash_balance"] + points[1]["net_cash_flow"]
    )
    assert (
        points[2]["cash_upper"] - points[2]["cash_lower"]
        > points[0]["cash_upper"] - points[0]["cash_lower"]
    )


# ---------------- XGBoost artifact ----------------


@pytest.fixture
def tiny_xgb(app, tmp_path):
    rng = np.random.default_rng(1)
    X = rng.normal(1, 0.2, size=(200, len(FEATURE_NAMES)))
    model = XGBRegressor(n_estimators=10, max_depth=2).fit(X, X[:, 0])
    joblib.dump(model, tmp_path / "forecaster_xgb.joblib")
    app.config["MODEL_DIR"] = str(tmp_path)
    return model


def test_xgb_forecaster_is_recursive_and_non_negative(tiny_xgb):
    m = matrix([10_000.0, 12_000, 11_000, 13_000])
    out = fm.xgb_forecaster(tiny_xgb)(m, 3)
    assert out.shape == (3, len(FORECAST_CATEGORIES))
    assert (out >= 0).all().all()
    assert out["Shopping"].sum() == 0  # no history -> no forecast


def test_missing_artifact_excludes_xgboost(app):
    with pytest.raises(RuntimeError):
        fm.xgboost_global(matrix([1.0, 2, 3]), 1)


# ---------------- API ----------------


@pytest.fixture
def demo(app, client) -> ApiClient:
    seed_demo()
    user = db.session.scalar(db.select(User))
    res = client.post(
        "/api/auth/login", json={"email": user.email, "password": app.config["DEMO_PASSWORD"]}
    )
    return ApiClient(client, res.get_json()["data"]["access_token"])


def test_expense_forecast_api_without_model(demo):
    data = demo.get("/api/forecast/expenses?horizon=3").get_json()["data"]
    assert data["status"] == "ok" and len(data["forecast"]) == 3
    assert "xgboost" not in {b["model"] for b in data["model"]["backtest"]}
    assert data["explanation"].startswith("Spending for")
    saved = db.session.scalar(db.select(ForecastResult))
    assert saved.model_name == data["model"]["selected"] and len(saved.points) == 3


def test_expense_forecast_api_with_model(demo, tiny_xgb):
    data = demo.get("/api/forecast/expenses").get_json()["data"]
    assert "xgboost" in {b["model"] for b in data["model"]["backtest"]}
    assert "20% lower" in data["model"]["selection_rule"]


def test_cash_flow_api_and_validation(demo):
    data = demo.get("/api/forecast/cash-flow?horizon=12").get_json()["data"]
    assert len(data["forecast"]) == 12
    assert demo.get("/api/forecast/cash-flow?horizon=13").status_code == 400
    assert demo.get("/api/forecast/expenses?horizon=0").status_code == 400
    assert db.session.scalar(db.select(db.func.count(ForecastResult.id))) == 1


def test_new_user_forecast_is_insufficient(api):
    assert api.get("/api/forecast/expenses").get_json()["data"]["status"] == "insufficient_data"


def test_ml_status(api, app, tmp_path):
    app.config["MODEL_DIR"] = str(tmp_path)
    (tmp_path / "metrics").mkdir()
    (tmp_path / "metrics" / "forecaster.json").write_text('{"total_level": {}}')
    data = api.get("/api/ml/status").get_json()["data"]
    assert data["artifacts"]["forecaster"]["available"] is False
    assert data["metrics"]["forecaster"] == {"total_level": {}}
