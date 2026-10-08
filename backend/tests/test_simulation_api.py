from datetime import date

import pytest

from app.extensions import db
from app.models import SimulationResult, User
from app.seed.demo import seed_demo
from app.services.digital_twin.builder import build_twin
from app.services.digital_twin.state import GoalData, InvestmentData, ProfileData, UserData
from app.services.simulation.engine import project
from app.services.simulation.scenarios import Scenario
from app.services.simulation.service import baseline_from, run_scenario, simulated_twin
from tests.conftest import ApiClient, register
from tests.test_forecasting import monthly_rows
from tests.test_twin_builder import frame

TODAY = date(2026, 10, 8)


def user_data(**kwargs) -> UserData:
    """6 months: income 1,00,000, Groceries 40,000 (essential), Shopping 20,000."""
    rows = []
    for row in monthly_rows([40_000] * 6, date(2026, 4, 1)):
        rows.append(row)
    rows += [(f"2026-0{m}-20", 20_000, "Shopping") for m in range(4, 10)]
    profile = ProfileData(
        opening_balance=200_000, opening_balance_date=date(2026, 10, 1), emergency_fund=150_000
    )
    return UserData(transactions=frame(rows), profile=profile, today=TODAY, **kwargs)


def scenario(*changes, **kwargs) -> Scenario:
    return Scenario.model_validate({"changes": list(changes), **kwargs})


# ---------------- service ----------------


def test_baseline_from_twin_and_holdings():
    invs = [
        InvestmentData("fd", 100_000, 0, 0.07),
        InvestmentData("sip_equity", 300_000, 5_000, 0.11),
    ]
    data = user_data(investments=invs)
    base = baseline_from(data, build_twin(data))
    assert (base.income, base.essential, base.discretionary) == (100_000, 40_000, 20_000)
    assert base.cash == 200_000 and base.emergency_fund == 150_000
    assert base.investment_return == pytest.approx((100_000 * 0.07 + 300_000 * 0.11) / 400_000)
    assert base.sip == 5_000  # no SIP transactions -> planned contribution from holdings


def test_simulated_twin_uses_identical_formulas():
    data = user_data()
    twin = build_twin(data)
    proj = project(baseline_from(data, twin), [], 12)
    future = simulated_twin(twin, proj, 12)
    assert future.as_of == date(2027, 10, 31)
    assert future.cash_balance == proj.at(12).cash
    assert future.savings_ratio == pytest.approx(0.40)
    assert future.emergency_months == pytest.approx(150_000 / 40_000)
    assert len(future.recent_months) == 6


def test_affordable_purchase_is_low_risk_with_saving_time():
    out = run_scenario(user_data(), scenario({"type": "large_purchase", "amount": 130_000}))
    assert out["risk_level"] == "LOW"
    assert out["impact"]["cash_change"] == -130_000
    assert out["impact"]["health_score_change"] == pytest.approx(0, abs=0.5)
    assert "about 4 month(s)" in out["recommendation"]  # 1,30,000 / 40,000 surplus
    assert out["current_state"]["cash_balance"] == 200_000


def test_unaffordable_purchase_is_critical():
    out = run_scenario(user_data(), scenario({"type": "large_purchase", "amount": 500_000}))
    assert out["risk_level"] == "CRITICAL"
    assert out["impact"]["first_shortfall_month"] == "2026-11"
    assert out["impact"]["max_shortfall"] == pytest.approx(500_000 - 240_000 - 150_000)
    assert any("Money runs out" in f for f in out["risk_factors"])


def test_income_loss_raises_risk_and_lowers_score():
    out = run_scenario(user_data(), scenario({"type": "income_change", "pct": -50}))
    assert out["impact"]["monthly_cash_flow_change"] == -50_000
    assert out["impact"]["health_score_change"] < -15
    assert out["risk_level"] in ("HIGH", "CRITICAL")
    assert out["simulated_state"]["savings_ratio"] == pytest.approx(-0.2)


def test_extra_savings_reaches_goal_sooner():
    # Planned 50,000/month exceeds the 40,000 surplus, so saving more speeds the goal up.
    # (With a fully funded plan the extra would stay in cash: goals get their planned amount.)
    goals = [GoalData(1, "Car", 600_000, 0, date(2028, 10, 1), 1, 50_000)]
    out = run_scenario(
        user_data(goals=goals),
        scenario(
            {"type": "extra_savings", "amount": 10_000},
            {"type": "goal_delay", "goal_id": 1, "months": 2},
        ),
    )
    goal = out["goals"][0]
    assert goal["delay_months"] < 0  # sooner
    assert goal["target_date"] == "2028-12"
    assert out["impact"]["health_score_change"] >= 0
    assert out["risk_level"] == "LOW"
    assert "sooner" in out["explanation"]


def test_response_contract():
    out = run_scenario(
        user_data(), scenario({"type": "sip_change", "amount": 5_000}, horizon_months=12)
    )
    assert {"current_state", "simulated_state", "baseline_state", "impact", "risk_level",
            "recommendation", "explanation", "assumptions", "timeline", "goals",
            "disclaimer"} <= set(out)  # fmt: skip
    assert len(out["timeline"]) == 12
    assert {"cash_change", "savings_change", "health_score_change", "goal_delay"} <= set(
        out["impact"]
    )
    assert (
        out["timeline"][0]["scenario"]["investments"]
        == out["timeline"][0]["baseline"]["investments"] + 5_000
    )


# ---------------- API ----------------


@pytest.fixture
def demo(app, client) -> ApiClient:
    seed_demo()
    user = db.session.scalar(db.select(User))
    res = client.post(
        "/api/auth/login", json={"email": user.email, "password": app.config["DEMO_PASSWORD"]}
    )
    return ApiClient(client, res.get_json()["data"]["access_token"])


def test_what_if_accepts_single_change_body(demo):
    body = {"type": "large_purchase", "amount": 130_000, "date": "2027-01-01"}
    res = demo.post("/api/simulation/what-if", json=body)
    data = res.get_json()["data"]
    assert res.status_code == 200
    assert data["scenario"]["changes"][0]["type"] == "large_purchase"
    assert data["impact"]["cash_change"] == -130_000
    assert data["risk_level"] in ("LOW", "MEDIUM")


@pytest.mark.parametrize(
    "body",
    [
        {"type": "teleport"},
        {"changes": []},
        {"type": "income_change", "pct": 10, "amount": 5},
        {"type": "goal_delay", "goal_id": 99_999, "months": 3},
        {"changes": [{"type": "sip_change", "amount": 1}], "horizon_months": 120},
    ],
)
def test_what_if_validation(demo, body):
    assert demo.post("/api/simulation/what-if", json=body).status_code == 400


def test_saved_scenario_lifecycle(demo):
    body = {"name": "New laptop", "changes": [{"type": "large_purchase", "amount": 130_000}]}
    created = demo.post("/api/simulation/scenarios", json=body)
    assert created.status_code == 201
    sid = created.get_json()["data"]["scenario"]["id"]
    assert created.get_json()["data"]["scenario"]["latest_result"]["cash_change_12m"] == -130_000

    listed = demo.get("/api/simulation/scenarios").get_json()["data"]
    assert [s["name"] for s in listed] == ["New laptop"]

    detail = demo.get(f"/api/simulation/scenarios/{sid}").get_json()["data"]
    assert detail["result"]["impact"]["cash_change"] == -130_000
    assert len(detail["result"]["timeline"]) == 24

    assert demo.post(f"/api/simulation/scenarios/{sid}/run").status_code == 201
    assert db.session.scalar(db.select(db.func.count(SimulationResult.id))) == 2

    assert demo.delete(f"/api/simulation/scenarios/{sid}").status_code == 204
    assert db.session.scalar(db.select(db.func.count(SimulationResult.id))) == 0  # cascade


def test_saved_scenario_needs_a_name(demo):
    res = demo.post(
        "/api/simulation/scenarios", json={"changes": [{"type": "sip_change", "amount": 1}]}
    )
    assert res.status_code == 400


def test_scenarios_are_private(demo, client):
    sid = demo.post(
        "/api/simulation/scenarios",
        json={"name": "x", "changes": [{"type": "sip_change", "amount": 1_000}]},
    ).get_json()["data"]["scenario"]["id"]
    other = register(client, email="other@example.com")
    assert other.get(f"/api/simulation/scenarios/{sid}").status_code == 404
    assert other.delete(f"/api/simulation/scenarios/{sid}").status_code == 404
    assert other.get("/api/simulation/scenarios").get_json()["data"] == []


def test_new_user_can_simulate_from_declared_profile(api):
    api.put("/api/financial-profile", json={"declared_monthly_income": 60_000,
                                            "monthly_essential_expenses": 30_000,
                                            "opening_balance": 50_000})  # fmt: skip
    data = api.post(
        "/api/simulation/what-if", json={"type": "large_purchase", "amount": 100_000}
    ).get_json()["data"]
    assert data["impact"]["first_shortfall_month"] is not None
    assert data["risk_level"] == "CRITICAL"
    assert "declared profile values" in data["assumptions"][0]
