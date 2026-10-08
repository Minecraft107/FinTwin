"""Simulation engine against hand calculations.

Baseline: income 1,00,000; essential 40,000; discretionary 20,000; SIP 10,000
-> recurring surplus 30,000/month. Cash 2,00,000; emergency fund 1,20,000.
"""

from dataclasses import replace
from datetime import date

import pytest

from app.services.financial.formulas import emi
from app.services.simulation.engine import (
    Baseline,
    GoalState,
    LoanState,
    month_index,
    months_to_save,
    project,
)
from app.services.simulation.scenarios import Scenario

TODAY = date(2026, 10, 8)
BASE = Baseline(
    today=TODAY, income=100_000, essential=40_000, discretionary=20_000, sip=10_000,
    untracked_emi=0, cash=200_000, emergency_fund=120_000, investments=0, investment_return=0,
)  # fmt: skip


def run(changes: list[dict], base: Baseline = BASE, horizon: int = 24, inflation: float = 0.0):
    scenario = Scenario.model_validate(
        {"changes": changes or [{"type": "extra_savings", "amount": 1}]}
    )
    return project(base, list(scenario.changes) if changes else [], horizon, inflation)


def test_no_change_accumulates_surplus():
    p = run([])
    assert p.months[0].month == "2026-11"
    assert p.at(1).cash == 230_000
    assert p.at(12).cash == 200_000 + 12 * 30_000
    assert p.at(12).investments == 12 * 10_000
    assert p.at(12).net_worth == p.at(12).cash + 120_000 + 120_000


def test_large_purchase_from_cash():
    p = run([{"type": "large_purchase", "amount": 130_000}])
    assert p.at(1).cash == 200_000 + 30_000 - 130_000
    assert p.at(12).cash == 560_000 - 130_000
    assert p.at(1).one_time_out == 130_000


def test_purchase_beyond_cash_draws_emergency_fund():
    p = run([{"type": "large_purchase", "amount": 260_000}])
    m = p.at(1)
    assert (m.cash, m.emergency_drawn, m.emergency_fund, m.shortfall) == (0, 30_000, 90_000, 0)


def test_purchase_beyond_cash_and_emergency_fund_is_a_shortfall():
    p = run([{"type": "large_purchase", "amount": 400_000}])
    assert p.at(1).shortfall == 50_000  # 2,30,000 - 4,00,000 + 1,20,000
    assert p.at(2).shortfall == 20_000  # recovers by the 30,000 surplus
    assert p.at(3).shortfall == 0 and p.at(3).cash == 10_000


def test_income_cut_20_percent():
    p = run([{"type": "income_change", "pct": -20}])
    assert p.at(1).income == 80_000
    assert p.at(12).cash == 200_000 + 12 * 10_000


def test_new_loan_disbursed_then_amortised():
    p = run([{"type": "new_loan", "principal": 500_000, "annual_rate": 0.12, "tenure_months": 60}])
    payment = emi(500_000, 0.12, 60)
    assert payment == pytest.approx(11_122.22, abs=0.01)
    assert p.at(1).emi == 0  # first EMI the month after disbursement
    assert p.at(1).cash == 200_000 + 30_000 + 500_000
    assert p.at(1).debt == 500_000
    assert p.at(2).emi == pytest.approx(payment)
    assert p.at(2).debt == pytest.approx(500_000 * 1.01 - payment)


def test_financed_purchase_has_no_upfront_cost_and_loan_ends():
    p = run([{"type": "large_purchase", "amount": 100_000, "financed_by_loan": True,
              "loan_annual_rate": 0.0, "loan_tenure_months": 10}])  # fmt: skip
    assert p.at(1).one_time_out == 0 and p.at(1).cash == 230_000
    assert [p.at(m).emi for m in (2, 11, 12)] == [10_000, 10_000, 0]
    assert p.at(11).debt == 0


def test_sip_increase_grows_investments_with_returns():
    base = replace(BASE, investment_return=0.12)
    p = run([{"type": "sip_change", "amount": 5_000}], base)
    assert p.at(1).investments == 15_000
    assert p.at(2).investments == pytest.approx(15_000 * 1.01 + 15_000)
    assert p.at(1).cash == 200_000 + 25_000


@pytest.mark.parametrize("amount,surplus", [(15_000, 45_000), (30_000, 50_000)])
def test_extra_savings_cuts_discretionary_but_not_below_zero(amount, surplus):
    p = run([{"type": "extra_savings", "amount": amount}])
    assert p.at(1).recurring_surplus == surplus


def test_temporary_expense_change():
    p = run(
        [{"type": "expense_change", "amount": 10_000, "kind": "essential", "duration_months": 3}]
    )
    assert [p.at(m).recurring_surplus for m in (1, 3, 4)] == [20_000, 20_000, 30_000]


def test_percentage_expense_change():
    assert run([{"type": "expense_change", "pct": 50}]).at(1).discretionary == 30_000


def test_one_time_income_in_its_month():
    p = run([{"type": "one_time_income", "amount": 50_000, "date": "2027-01-15"}])
    assert [p.at(m).one_time_in for m in (2, 3, 4)] == [0, 50_000, 0]
    assert p.at(3).cash == 200_000 + 3 * 30_000 + 50_000


def test_existing_loan_stops_when_repaid():
    base = replace(BASE, loans=[LoanState("Old", 20_000, 0.0, 10_000)])
    p = run([], base)
    assert [p.at(m).emi for m in (1, 2, 3)] == [10_000, 10_000, 0]


def test_goals_funded_in_priority_order():
    goals = [
        GoalState(2, "Trip", 100_000, 0, 20_000, 2, date(2028, 1, 1)),
        GoalState(1, "Car", 100_000, 0, 20_000, 1, date(2028, 1, 1)),
    ]
    p = run([], replace(BASE, goals=goals))
    assert p.at(1).goal_balances == {2: 10_000, 1: 20_000}  # 30k surplus: car first
    assert p.at(1).cash == 200_000  # surplus moved to goals
    car = next(g for g in p.goals if g.id == 1)
    assert car.completed == "2027-03"  # 5 × 20,000
    assert p.at(6).goal_balances[2] == 5 * 10_000 + 20_000  # trip gets 20k after the car is done


def test_goals_keep_a_one_month_cash_buffer():
    goals = [GoalState(1, "Car", 500_000, 0, 50_000, 1, None)]
    p = run([], replace(BASE, cash=50_000, goals=goals))
    # Month 1: cash 80,000; buffer = 60,000 of outgoings -> only 20,000 can go to the goal.
    assert p.at(1).goal_balances[1] == 20_000
    assert p.at(1).cash == 60_000


def test_goal_delay_moves_target_date():
    goals = [GoalState(1, "Car", 100_000, 0, 10_000, 1, date(2027, 6, 1))]
    p = run([{"type": "goal_delay", "goal_id": 1, "months": 6}], replace(BASE, goals=goals))
    assert p.goals[0].target_date == date(2027, 12, 1)


def test_event_beyond_horizon_is_ignored_with_note():
    p = run([{"type": "large_purchase", "amount": 50_000, "date": "2031-01-01"}], horizon=12)
    assert p.at(12).cash == 560_000
    assert "beyond the 12-month horizon" in p.notes[0]


def test_inflation_raises_spending():
    p = run([], inflation=12)
    assert p.at(12).essential == pytest.approx(40_000 * 1.12)


def test_deterministic():
    changes = [{"type": "income_change", "pct": -10}, {"type": "large_purchase", "amount": 1e5}]
    assert run(changes).months == run(changes).months


def test_helpers():
    assert month_index(TODAY, None) == 1
    assert month_index(TODAY, date(2026, 10, 20)) == 1  # current month -> first projected month
    assert month_index(TODAY, date(2027, 1, 1)) == 3
    assert months_to_save(130_000, 7_720) == 17
    assert months_to_save(1, 0) is None


@pytest.mark.parametrize(
    "change",
    [
        {"type": "income_change"},  # neither amount nor pct
        {"type": "income_change", "pct": 10, "amount": 5},  # both
        {"type": "large_purchase", "amount": -1},
        {"type": "teleport"},
        {"type": "new_loan", "principal": 1, "annual_rate": 2, "tenure_months": 12},
    ],
)
def test_invalid_changes_rejected(change):
    with pytest.raises(ValueError):
        Scenario.model_validate({"changes": [change]})
