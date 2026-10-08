"""Digital Twin builder on hand-built data, where every expected number is computed by hand."""

import json
from datetime import date

import pandas as pd
import pytest

from app.services.digital_twin.builder import build_twin, cash_balance, monthly_snapshot_dates
from app.services.digital_twin.state import (
    GoalData,
    InvestmentData,
    LoanData,
    ProfileData,
    UserData,
)
from app.services.financial.formulas import outstanding_after

KIND = {
    "Salary": ("income", "income"),
    "Housing": ("expense", "essential"),
    "Groceries": ("expense", "essential"),
    "Shopping": ("expense", "discretionary"),
    "EMI/Debt": ("expense", "debt"),
    "Investment": ("expense", "investment"),
}
TODAY = date(2026, 4, 10)


def frame(rows: list[tuple[str, float, str]]) -> pd.DataFrame:
    """rows: (ISO date, amount, category)."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime([r[0] for r in rows]),
            "amount": [float(r[1]) for r in rows],
            "type": [KIND[r[2]][0] for r in rows],
            "category": [r[2] for r in rows],
            "kind": [KIND[r[2]][1] for r in rows],
            "merchant": None,
            "description": "x",
        }
    )


def month_rows(month: str, income=100_000, essential=40_000, discretionary=20_000, debt=0, inv=0):
    rows = [(f"{month}-01", income, "Salary"), (f"{month}-05", essential, "Housing")]
    rows.append((f"{month}-15", discretionary, "Shopping"))
    if debt:
        rows.append((f"{month}-05", debt, "EMI/Debt"))
    if inv:
        rows.append((f"{month}-10", inv, "Investment"))
    return [r for r in rows if r[1]]


def data(rows, **kwargs) -> UserData:
    return UserData(transactions=frame(rows), today=TODAY, **kwargs)


Q1 = month_rows("2026-01") + month_rows("2026-02") + month_rows("2026-03")


def test_net_cash_flow_income_minus_expenses():
    twin = build_twin(data(Q1))
    assert twin.monthly_income == 100_000
    assert twin.monthly_expenses == 60_000
    assert twin.net_cash_flow == 40_000
    assert twin.savings_ratio == pytest.approx(0.40)
    assert twin.expense_ratio == pytest.approx(0.60)
    assert twin.window_months == 3
    assert (twin.window_start, twin.window_end) == (date(2026, 1, 1), date(2026, 3, 31))
    assert twin.sources["income"] == "observed"


def test_partial_current_month_is_excluded_from_averages():
    rows = Q1 + [("2026-04-05", 500_000, "Shopping")]
    twin = build_twin(data(rows))
    assert twin.monthly_expenses == 60_000
    assert twin.cash_balance == pytest.approx(3 * 40_000 - 500_000)  # but balance reflects it


def test_debt_and_investments():
    rows = [
        r for m in ("2026-01", "2026-02", "2026-03") for r in month_rows(m, debt=10_000, inv=5_000)
    ]
    twin = build_twin(data(rows, profile=ProfileData(emergency_fund=150_000)))
    assert twin.net_cash_flow == 100_000 - 60_000 - 10_000 - 5_000
    assert twin.savings_ratio == pytest.approx(0.30)  # investing counts as saving
    assert twin.debt_to_income == pytest.approx(0.10)
    assert twin.investment_rate == pytest.approx(0.05)
    assert twin.disposable_income == 100_000 - 40_000 - 10_000
    assert twin.emergency_months == pytest.approx(150_000 / (40_000 + 10_000))
    assert twin.burn_rate_daily == pytest.approx(70_000 / 30.44)


def test_zero_income_gives_undefined_ratios_and_negative_flow():
    rows = [r for r in Q1 if r[2] != "Salary"]
    twin = build_twin(data(rows))
    assert twin.monthly_income == 0
    assert twin.net_cash_flow == -60_000
    assert twin.savings_ratio is None and twin.debt_to_income is None
    assert twin.expense_ratio is None


def test_zero_expenses():
    rows = [r for r in Q1 if r[2] == "Salary"]
    twin = build_twin(data(rows, profile=ProfileData(emergency_fund=10_000)))
    assert twin.net_cash_flow == 100_000
    assert twin.savings_ratio == 1.0
    assert twin.emergency_months is None  # no essential costs -> coverage undefined


def test_negative_cash_flow():
    rows = [
        r for m in ("2026-01", "2026-02", "2026-03") for r in month_rows(m, discretionary=80_000)
    ]
    twin = build_twin(data(rows))
    assert twin.net_cash_flow == -20_000
    assert twin.savings_ratio == pytest.approx(-0.20)


def test_no_history_falls_back_to_declared_profile():
    profile = ProfileData(
        declared_monthly_income=80_000,
        monthly_essential_expenses=30_000,
        monthly_discretionary_expenses=10_000,
    )
    twin = build_twin(UserData(profile=profile, today=TODAY))
    assert twin.window_months == 0 and twin.months_of_history == 0
    assert twin.monthly_income == 80_000 and twin.net_cash_flow == 40_000
    assert twin.sources["income"] == "declared"
    assert "declared profile" in twin.notes[0]
    assert twin.recent_months == []


def test_only_current_partial_month_counts_as_no_history():
    twin = build_twin(data([("2026-04-01", 100_000, "Salary")]))
    assert twin.window_months == 0
    assert twin.sources["income"] == "declared"


def test_short_history_uses_available_months_with_note():
    twin = build_twin(data(month_rows("2026-03")))
    assert twin.window_months == 1
    assert twin.monthly_income == 100_000
    assert "only 1 complete month" in twin.notes[0]


def test_empty_month_inside_window_counts_as_zero():
    rows = month_rows("2026-01") + month_rows("2026-03")
    twin = build_twin(data(rows))
    assert twin.window_months == 3
    assert twin.monthly_income == pytest.approx(200_000 / 3)


def test_historical_as_of_ignores_later_transactions():
    twin = build_twin(data(Q1), as_of=date(2026, 2, 28))
    assert twin.window_months == 2
    assert twin.months_of_history == 2
    assert twin.window_end == date(2026, 2, 28)


def test_cash_balance_before_and_after_opening_date():
    rows = Q1
    profile = ProfileData(opening_balance=50_000, opening_balance_date=date(2026, 2, 1))
    d = data(rows, profile=profile)
    # From 1 Feb: Feb and Mar each +40k
    assert cash_balance(d, date(2026, 3, 31)) == 50_000 + 80_000
    # Before the opening date, later January flows are worked backwards:
    # after 3 Jan come -40k (5 Jan) and -20k (15 Jan), so the balance then was 50k + 60k.
    assert cash_balance(d, date(2026, 1, 3)) == 110_000
    assert cash_balance(d, date(2025, 12, 31)) == 50_000 - 40_000


def test_loan_outstanding_anchored_to_stored_value():
    loan = LoanData(
        principal=600_000, outstanding=400_000, annual_interest_rate=0.10, emi=11_115.5,
        tenure_months=72, start_date=date(2024, 4, 1),
    )  # fmt: skip
    d = data(Q1, loans=[loan])
    assert build_twin(d).total_debt == 400_000
    past = build_twin(d, as_of=date(2025, 4, 30)).total_debt
    expected_repaid = outstanding_after(600_000, 0.10, 72, 12) - outstanding_after(
        600_000, 0.10, 72, 24
    )
    assert past == pytest.approx(400_000 + expected_repaid)
    assert build_twin(d, as_of=date(2024, 3, 31)).total_debt == 0  # loan not yet taken


def test_debt_payments_fall_back_to_scheduled_emi():
    loan = LoanData(500_000, 300_000, 0.09, 10_000, 60, date(2025, 1, 1))
    twin = build_twin(data(Q1, loans=[loan]))
    assert twin.debt_payments == 10_000
    assert twin.sources["debt_payments"] == "holdings"


def test_investments_value_allocation_and_duplicates():
    invs = [
        InvestmentData("fd", 50_000),
        InvestmentData("fd", 50_000),  # identical holdings must both count
        InvestmentData("sip_equity", 100_000, monthly_contribution=5_000),
    ]
    twin = build_twin(data(Q1, investments=invs))
    assert twin.investments_value == 200_000
    assert twin.investment_allocation == {"fd": 0.5, "sip_equity": 0.5}
    past = build_twin(data(Q1, investments=invs), as_of=date(2026, 1, 31))
    assert past.investments_value == pytest.approx(100_000 + 100_000 - 3 * 5_000)


def test_goals_progress_and_net_worth():
    goals = [
        GoalData(2, "Trip", 100_000, 25_000, priority=2),
        GoalData(1, "Car", 800_000, 200_000, priority=1),
        GoalData(3, "Paused", 50_000, 10_000, status="paused"),
    ]
    profile = ProfileData(emergency_fund=90_000)
    loan = LoanData(100_000, 60_000, 0.0, 5_000, 20, date(2025, 1, 1))
    twin = build_twin(data(Q1, goals=goals, profile=profile, loans=[loan]))
    assert [g.name for g in twin.goals] == ["Car", "Trip", "Paused"]
    assert twin.goals[0].progress_pct == pytest.approx(25.0)
    assert twin.goals[0].remaining == 600_000
    assert twin.goals_saved == 225_000
    assert twin.net_worth == pytest.approx(twin.cash_balance + 90_000 + 225_000 - 60_000)


def test_expenses_by_category_are_monthly_averages():
    twin = build_twin(data(Q1))
    assert twin.expenses_by_category == {"Housing": 40_000, "Shopping": 20_000}


def test_recent_months_and_serialization():
    twin = build_twin(data(Q1))
    assert [m.month for m in twin.recent_months] == ["2026-01", "2026-02", "2026-03"]
    assert twin.recent_months[0].net == 40_000
    payload = twin.to_dict()
    json.dumps(payload)  # fully JSON-serializable
    assert payload["as_of"] == "2026-04-10"
    assert payload["recent_months"][0]["expenses"] == 60_000


def test_monthly_snapshot_dates():
    assert monthly_snapshot_dates(data(Q1 + [("2026-04-02", 1, "Shopping")])) == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
    ]
    assert monthly_snapshot_dates(UserData(today=TODAY)) == []
