import math
from dataclasses import replace
from datetime import date

import pytest

from app.extensions import db
from app.models import User
from app.seed.demo import seed_demo
from app.services.financial.formulas import future_value, months_to_target, required_payment
from app.services.financial.goal_planner import plan_goals
from tests.conftest import ApiClient, register
from tests.test_health_score import goal, twin

AS_OF = date(2026, 4, 10)


# ---------------- formulas ----------------


def test_spec_example_car_goal():
    # Target ₹8,00,000, saved ₹2,00,000, 24 months -> (8L - 2L) / 24 = ₹25,000/month.
    assert required_payment(800_000, 200_000, 0.0, 24) == pytest.approx(25_000)
    assert months_to_target(800_000, 200_000, 25_000, 0.0) == 24


@pytest.mark.parametrize("rate", [0.06, 0.12])
def test_required_payment_with_returns_round_trips(rate):
    payment = required_payment(800_000, 200_000, rate, 24)
    assert payment < 25_000  # returns do part of the work
    assert future_value(200_000, payment, rate, 24) == pytest.approx(800_000)
    assert months_to_target(800_000, 200_000, payment, rate) == 24


def test_months_to_target_edges():
    assert months_to_target(100, 100, 0, 0) == 0  # already there
    assert months_to_target(100_000, 0, 0, 0) is None  # never without saving
    assert months_to_target(100_000, 50_000, 0, 0.12) == math.ceil(math.log(2) / math.log(1.01))
    assert months_to_target(100_000, 0, 30_000, 0) == 4  # ceil(3.33)


def test_required_payment_zero_when_growth_alone_suffices():
    assert required_payment(100_000, 99_000, 0.12, 12) == 0


# ---------------- planner ----------------


def plans(goals, surplus=40_000.0, **kwargs):
    t = replace(twin(goals=goals, net_cash_flow=surplus), as_of=AS_OF)
    return {p["goal_id"]: p for p in plan_goals(t, **kwargs)}


def car(**kw):
    """The spec example: ₹8L target, ₹2L saved, due in 24 months."""
    fields = dict(target=800_000, current=200_000, monthly=25_000, months=24)
    return goal(1, 1, **(fields | kw))


def test_on_track_when_surplus_funds_the_requirement():
    p = plans([car()])[1]
    assert p["status"] == "on_track"
    assert p["required_monthly"] == pytest.approx(25_000)
    assert p["fundable_monthly"] == 25_000 and p["shortfall_monthly"] == 0
    assert p["completion_at_fundable"] == "2028-04"
    assert p["options"] == []
    assert "on track" in p["explanation"]


def test_at_risk_when_plan_is_enough_but_surplus_is_not():
    p = plans([car()], surplus=10_000)[1]
    assert p["status"] == "at_risk"
    assert p["fundable_monthly"] == 10_000
    assert p["shortfall_monthly"] == pytest.approx(15_000)
    assert p["completion_at_fundable"] == "2031-04"  # 6L / 10k = 60 months
    assert p["shortfall_at_target_date"] == pytest.approx(600_000 - 240_000)
    types = [o["type"] for o in p["options"]]
    assert types == ["free_up_spending", "extend_target_date", "reduce_target"]


def test_off_track_when_plan_is_too_small():
    p = plans([car(monthly=15_000)])[1]
    assert p["status"] == "off_track"
    assert p["options"][0]["type"] == "increase_contribution"
    assert "+₹10,000" in p["options"][0]["text"]


def test_priorities_share_the_surplus():
    goals = [car(), goal(2, 2, target=100_000, monthly=20_000, months=10)]
    result = plans(goals, surplus=30_000)
    assert result[1]["fundable_monthly"] == 25_000
    assert result[2]["fundable_monthly"] == 5_000 and result[2]["surplus_capacity"] == 5_000
    assert result[2]["status"] == "at_risk"


def test_no_target_date_achieved_and_paused():
    goals = [
        goal(1, 1, months=0),  # no target date
        goal(2, 2, target=50_000, current=50_000),
        goal(3, 3, status="paused"),
    ]
    result = plans(goals)
    assert result[1]["status"] == "no_target_date" and result[1]["required_monthly"] is None
    assert result[1]["completion_at_fundable"] == "2027-04"  # 1.2L at 10k/month
    assert result[2]["status"] == "achieved"
    assert result[3]["status"] == "paused" and result[3]["fundable_monthly"] == 0


def test_overdue_goal():
    p = plans([car(months=-2)])[1]
    assert p["status"] == "overdue"
    assert p["required_monthly"] == pytest.approx(600_000)  # everything is due now


def test_sensitivity_table():
    rows = plans([car(monthly=15_000)], surplus=18_000)[1]["sensitivity"]
    assert [r["monthly"] for r in rows] == [10_000, 13_000, 15_000, 17_000, 20_000]
    assert [r["months_to_complete"] for r in rows] == [60, 47, 40, 36, 30]
    assert [r["affordable"] for r in rows] == [True, True, True, True, False]
    assert all(r["meets_target_date"] is False for r in rows)


def test_returns_lower_the_requirement():
    p = plans([car()], annual_return=0.06)[1]
    assert p["required_monthly"] == pytest.approx(required_payment(800_000, 200_000, 0.06, 24))
    assert p["annual_return_assumed"] == 0.06


def test_extra_surplus_and_overrides():
    base = plans([car()], surplus=10_000)[1]
    better = plans([car()], surplus=10_000, extra_surplus=15_000)[1]
    assert base["status"] == "at_risk" and better["status"] == "on_track"
    later = plans([car()], surplus=10_000, overrides={1: {"target_date": date(2031, 4, 10)}})[1]
    assert later["required_monthly"] == pytest.approx(10_000)
    assert later["status"] == "on_track"


# ---------------- API ----------------


@pytest.fixture
def demo(app, client) -> ApiClient:
    seed_demo()
    user = db.session.scalar(db.select(User))
    res = client.post(
        "/api/auth/login", json={"email": user.email, "password": app.config["DEMO_PASSWORD"]}
    )
    return ApiClient(client, res.get_json()["data"]["access_token"])


def test_demo_plans(demo):
    body = demo.get("/api/goals/plan").get_json()
    names = [p["name"] for p in body["data"]]
    assert names == ["Buy a car", "Europe trip", "Higher studies fund"]  # priority order
    car_plan = body["data"][0]
    assert car_plan["required_monthly"] == pytest.approx(25_000, abs=1_100)  # 6L over ~24 months
    assert car_plan["status"] == "off_track"
    assert car_plan["fundable_monthly"] == pytest.approx(body["meta"]["monthly_surplus"])
    assert body["data"][1]["fundable_monthly"] == 0  # the car takes the whole surplus


def test_single_plan_and_validation(demo):
    goal_id = demo.get("/api/goals").get_json()["data"][0]["id"]
    assert (
        demo.get(f"/api/goals/{goal_id}/plan?annual_return=0.07").get_json()["data"][
            "annual_return_assumed"
        ]
        == 0.07
    )
    assert demo.get(f"/api/goals/{goal_id}/plan?annual_return=0.5").status_code == 400
    assert demo.get("/api/goals/99999/plan").status_code == 404


def test_simulate_goal_changes(demo):
    goals = demo.get("/api/goals").get_json()["data"]
    car_id = goals[0]["id"]
    res = demo.post(f"/api/goals/{car_id}/simulate", json={"target_date": "2033-10-01"})
    data = res.get_json()["data"]
    assert data["simulated"]["required_monthly"] < data["current"]["required_monthly"]
    # Demoting the car below the trip lets the trip take its planned ₹6,000 first
    # (equal priorities are funded in creation order).
    res = demo.post(f"/api/goals/{car_id}/simulate", json={"priority": 3})
    data = res.get_json()["data"]
    affected = {a["name"]: a for a in data["other_goals_affected"]}
    assert affected["Europe trip"]["fundable_before"] == 0
    assert affected["Europe trip"]["fundable_after"] == 6_000
    assert data["simulated"]["fundable_monthly"] == pytest.approx(
        data["current"]["fundable_monthly"] - 6_000
    )
    # Nothing was saved.
    assert demo.get("/api/goals").get_json()["data"][1]["priority"] == 2


def test_simulate_validation_and_privacy(demo, client):
    goal_id = demo.get("/api/goals").get_json()["data"][0]["id"]
    assert demo.post(f"/api/goals/{goal_id}/simulate", json={"priority": 9}).status_code == 400
    assert demo.post(f"/api/goals/{goal_id}/simulate", json={"colour": "red"}).status_code == 400
    other = register(client, email="other@example.com")
    assert other.post(f"/api/goals/{goal_id}/simulate", json={}).status_code == 404
    assert other.get("/api/goals/plan").get_json()["data"] == []
