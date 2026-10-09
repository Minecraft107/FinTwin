"""The whole pipeline on awkward 'today' dates: leap day, month ends, year boundaries."""

import json
from datetime import date

import pytest

from app.extensions import db
from app.models import User
from app.repositories.user_data import load_user_data
from app.seed.demo import seed_demo
from app.services.analytics.risk_service import detect_risks
from app.services.digital_twin.builder import build_twin
from app.services.digital_twin.service import anomaly_flags, refresh_snapshots, scored
from app.services.financial.goal_planner import plan_goals
from app.services.forecasting.service import forecast_cash_flow, forecast_expenses
from app.services.simulation.scenarios import Scenario
from app.services.simulation.service import run_scenario
from app.utils.dates import last_complete_month_end

SCENARIO = Scenario.model_validate(
    {
        "changes": [
            {"type": "large_purchase", "amount": 150_000},
            {"type": "new_loan", "principal": 500_000, "annual_rate": 0.1, "tenure_months": 36},
            {"type": "income_change", "pct": -20, "duration_months": 6},
        ],
        "horizon_months": 60,
        "inflation_pct": 6,
    }
)


def strict_json(payload) -> None:
    json.dumps(payload, allow_nan=False, default=str)  # browsers reject NaN / Infinity


@pytest.mark.parametrize(
    "today",
    [
        date(2024, 2, 29),
        date(2025, 1, 1),
        date(2025, 1, 31),
        date(2025, 3, 31),
        date(2025, 12, 31),
        date(2026, 2, 28),
    ],  # fmt: skip
    ids=str,
)
def test_pipeline_on_edge_dates(app, today):
    seed_demo(today=today)
    user_id = db.session.scalar(db.select(User.id))
    data = load_user_data(user_id, today=today)

    twin = build_twin(data)
    # as_of means "end of that day", so on a month's last day that month counts as complete
    assert twin.window_months == 3 and twin.window_end == last_complete_month_end(today)
    assert twin.monthly_income > 0 and twin.notes == []
    flags = anomaly_flags(data)
    strict_json(scored(twin, flags).to_dict())

    expenses = forecast_expenses(data, horizon=6)
    assert expenses["status"] == "ok" and len(expenses["forecast"]) == 6
    strict_json(expenses)
    strict_json(forecast_cash_flow(data, horizon=12))

    result = run_scenario(data, SCENARIO)
    assert len(result["timeline"]) == 60
    strict_json(result)
    strict_json(plan_goals(twin, annual_return=0.07))

    alerts, _ = detect_risks(data, flags)
    assert all(a.severity for a in alerts)
    assert refresh_snapshots(user_id, data, flags) >= 23  # one per complete month (+ today)
