import json
from dataclasses import replace
from datetime import date

import pytest

from app.services.digital_twin.builder import build_twin
from app.services.digital_twin.state import GoalProgress, MonthFlow, UserData
from app.services.financial.goals import allocate_surplus
from app.services.financial.health_score import (
    SPECS,
    explain_change,
    grade_for,
    interpolate,
    methodology,
    score_twin,
)
from app.utils.dates import add_months
from app.utils.money import inr, pct

AS_OF = date(2026, 4, 10)


def steady_months(net_positive: bool = True, n: int = 6) -> list[MonthFlow]:
    discretionary = 10_000 if net_positive else 200_000
    return [
        MonthFlow(f"2025-{m:02d}", 100_000, 40_000, discretionary, 0, 0) for m in range(1, n + 1)
    ]


def twin(**overrides):
    """A neutral twin; tests override only the fields that matter to them."""
    base = build_twin(UserData(today=AS_OF))
    defaults = dict(
        monthly_income=100_000.0,
        monthly_expenses=60_000.0,
        essential_expenses=40_000.0,
        discretionary_expenses=20_000.0,
        debt_payments=0.0,
        investment_contributions=0.0,
        net_cash_flow=40_000.0,
        savings_ratio=0.40,
        debt_to_income=0.0,
        emergency_months=6.0,
        emergency_fund=240_000.0,
        investment_rate=0.15,
        investment_allocation={"fd": 0.5, "sip_equity": 0.3, "gold": 0.2},
        recent_months=steady_months(),
        goals=[],
        discretionary_by_category={"Food & Dining": 12_000.0, "Shopping": 8_000.0},
    )
    return replace(base, **(defaults | overrides))


def goal(id, priority, target=120_000, current=0, monthly=10_000, months=12, status="active"):
    target_date = add_months(AS_OF, months) if months else None
    return GoalProgress(id, f"G{id}", target, current, 0, target - current, monthly, target_date,
                        priority, status)  # fmt: skip


# ---------------- curves and specification ----------------


def test_weights_sum_to_100():
    assert sum(s.weight for s in SPECS.values()) == 100


@pytest.mark.parametrize(
    "key,x,expected",
    [
        ("savings", 0.20, 80),  # 50/30/20 rule target
        ("savings", 0.15, 65),  # midway 50 -> 80
        ("savings", -0.5, 0),  # clamped below
        ("savings", 0.9, 100),  # clamped above
        ("emergency_fund", 3, 70),
        ("emergency_fund", 2, 50),
        ("debt", 0.36, 50),
        ("debt", 0.43, 35),
        ("debt", 0.8, 0),
        ("spending", 0.30, 100),
        ("spending", 0.40, 75),
    ],
)
def test_curve_anchors(key, x, expected):
    assert interpolate(x, SPECS[key].anchors) == pytest.approx(expected)


@pytest.mark.parametrize(
    "score,grade",
    [(85, "A"), (84.9, "B"), (70, "B"), (69.9, "C"), (55, "C"), (40, "D"), (39.9, "E")],
)
def test_grade_boundaries(score, grade):
    assert grade_for(score)[0] == grade


# ---------------- scoring ----------------


def test_healthy_profile_scores_excellent():
    result = score_twin(twin())
    assert result.grade == "A"
    assert not result.weaknesses
    assert result.recommendations == []
    assert "goals" in [c.key for c in result.components if c.score is None]


def test_weighted_total_matches_hand_calculation():
    t = twin(
        savings_ratio=0.20,  # 80
        emergency_months=3.0,  # 70
        debt_to_income=0.36,  # 50
        debt_payments=36_000.0,
        investment_rate=0.10,  # 0.7*70 + 0.3*70 (2 types) = 70
        investment_allocation={"fd": 0.5, "gold": 0.5},
        discretionary_expenses=50_000.0,  # 50% of income -> 50
    )  # cash flow: 6/6 positive, constant spending -> 100; goals: excluded
    result = score_twin(t)
    expected = (20 * 80 + 20 * 70 + 20 * 50 + 15 * 100 + 10 * 70 + 5 * 50) / 90
    assert result.score == pytest.approx(expected)
    assert sum(c.effective_weight for c in result.components) == pytest.approx(1.0)
    assert result.component("goals").effective_weight == 0
    assert sum(c.points for c in result.components) == pytest.approx(result.score)


def test_no_data_gives_no_score():
    empty = build_twin(UserData(today=AS_OF))
    result = score_twin(empty)
    assert result.score is None and result.grade == "N/A"
    assert len(result.notes) == 7


def test_zero_income_with_spending_and_debt():
    t = twin(monthly_income=0.0, savings_ratio=None, debt_to_income=None, investment_rate=None,
             debt_payments=5_000.0)  # fmt: skip
    result = score_twin(t)
    assert result.component("savings").score == 0
    assert result.component("debt").score == 0
    assert result.component("investments").score is None
    assert result.component("spending").score is None


def test_insufficient_emergency_fund_is_weak_with_concrete_gap():
    t = twin(emergency_months=1.0, emergency_fund=40_000.0, cash_balance=10_000.0)
    result = score_twin(t)
    assert result.component("emergency_fund").score == pytest.approx(30)
    assert any(w.startswith("Emergency fund") for w in result.weaknesses)
    rec = next(r for r in result.recommendations if r.component == "emergency_fund")
    assert inr(3 * 40_000 - 40_000) in rec.action  # needs ₹80,000 more
    assert "earmarking" not in rec.action  # cash can't cover it


def test_idle_cash_is_pointed_out_for_emergency_gap():
    t = twin(emergency_months=1.0, emergency_fund=40_000.0, cash_balance=500_000.0)
    rec = next(r for r in score_twin(t).recommendations if r.component == "emergency_fund")
    assert "earmarking ₹80,000" in rec.action


def test_high_debt_is_weak():
    result = score_twin(twin(debt_to_income=0.55, debt_payments=55_000.0))
    assert result.component("debt").score == pytest.approx(10)
    assert result.component("debt").status == "weak"


def test_goal_funding_by_priority():
    goals = [goal(1, priority=1), goal(2, priority=2), goal(3, priority=3, months=0)]  # no date
    result = score_twin(twin(goals=goals, net_cash_flow=10_000.0))
    # 10k surplus funds goal 1 fully (ratio 1, weight 5), goal 2 not at all (ratio 0, weight 4)
    assert result.component("goals").score == pytest.approx(100 * 5 / 9)


def test_reached_goal_counts_as_funded_not_excluded():
    reached = goal(1, priority=1, target=100_000, current=100_000)
    open_goal = goal(2, priority=2)  # 10k/month required, 0 surplus -> 0%
    result = score_twin(twin(goals=[reached, open_goal], net_cash_flow=0.0))
    assert result.component("goals").score == pytest.approx(100 * 5 / 9)
    only_reached = score_twin(twin(goals=[reached])).component("goals")
    assert only_reached.score == 100 and "1 goal(s) already reached" in only_reached.explanation


def test_anomalies_reduce_spending_score_when_assessed():
    assert score_twin(twin()).component("spending").score == 100
    assert score_twin(twin(), recent_high_alerts=2).component("spending").score == pytest.approx(
        0.7 * 100 + 0.3 * 30
    )


def test_cash_flow_needs_three_months_and_lists_negative_months():
    assert score_twin(twin(recent_months=steady_months(n=2))).component("cash_flow").score is None
    months = steady_months()[:3] + steady_months(net_positive=False)[3:]
    component = score_twin(twin(recent_months=months)).component("cash_flow")
    assert "3 of the last 6 months" in component.explanation
    assert "2025-04" in component.explanation


def test_recommendations_ordered_by_potential_points():
    t = twin(savings_ratio=0.05, emergency_months=0.5, investment_rate=0.02)
    recs = score_twin(t).recommendations
    points = [r.potential_points for r in recs]
    assert points == sorted(points, reverse=True)
    assert recs[0].component in ("emergency_fund", "savings")
    savings = next(r for r in recs if r.component == "savings")
    assert "Food & Dining" in savings.action


def test_result_is_json_serializable():
    payload = score_twin(twin(goals=[goal(1, 1)])).to_dict()
    json.dumps(payload)
    assert payload["components"][0]["status"] in ("strong", "fair", "weak")


# ---------------- change explanation ----------------


def test_explain_change_attributes_points():
    before = score_twin(twin(savings_ratio=0.25, emergency_months=3.0))
    after = score_twin(
        replace(twin(savings_ratio=0.12, emergency_months=2.0), as_of=date(2026, 5, 1))
    )
    change = explain_change(after, before)
    assert change["delta"] < 0
    assert change["summary"].startswith("Your score fell by")
    assert "savings ratio moved from 25.0% to 12.0%" in change["summary"]
    assert change["drivers"][0]["component"] == "savings"  # largest point loss first
    assert sum(d["points_change"] for d in change["drivers"]) == pytest.approx(
        change["delta"], abs=0.1
    )


def test_explain_change_unchanged_and_missing():
    result = score_twin(twin())
    assert "essentially unchanged" in explain_change(result, result)["summary"]
    empty = score_twin(build_twin(UserData(today=AS_OF)))
    assert explain_change(result, empty) is None


def test_methodology_mirrors_specs():
    m = methodology()
    assert [c["key"] for c in m["components"]] == list(SPECS)
    assert m["components"][0]["anchors"][2] == {"value": 0.20, "score": 80}


# ---------------- helpers ----------------


def test_allocate_surplus_skips_finished_and_paused_goals():
    goals = [goal(1, 1, current=120_000), goal(2, 2, status="paused"), goal(3, 3)]
    funding = allocate_surplus(goals, 4_000, AS_OF)
    assert [f.goal_id for f in funding] == [3]
    assert funding[0].fundable_monthly == 4_000
    assert allocate_surplus(goals, -5_000, AS_OF)[0].fundable_monthly == 0


@pytest.mark.parametrize(
    "amount,text",
    [
        (130000, "₹1,30,000"),
        (999, "₹999"),
        (1000, "₹1,000"),
        (12345678, "₹1,23,45,678"),
        (-2500.4, "-₹2,500"),
        (0, "₹0"),
    ],  # fmt: skip
)
def test_inr_indian_grouping(amount, text):
    assert inr(amount) == text


def test_pct():
    assert pct(0.1684) == "16.8%" and pct(None) == "n/a"
