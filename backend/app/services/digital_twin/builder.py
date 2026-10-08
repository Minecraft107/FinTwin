"""Builds the Financial Digital Twin: a derived financial state computed from raw data.

Pure function of (UserData, as_of). Rules:
- Flows are averaged over the last `window` *complete* calendar months up to `as_of`
  (a partial current month would understate spending).
- Observed transaction values are preferred; with no complete month of history the
  user's declared profile values are used. `sources` records which was used per metric.
- Balances are anchored to today's stored values (loans, investments); for a past `as_of`
  they are worked back with the amortization / compounding formulas.
"""

from dataclasses import replace
from datetime import date

import pandas as pd

from app.services.digital_twin.state import (
    GoalProgress,
    MonthFlow,
    TwinState,
    UserData,
)
from app.services.financial.formulas import outstanding_after, value_months_ago
from app.utils.dates import add_months, last_complete_month_end, month_end, months_between

DEFAULT_WINDOW = 3
RECENT_MONTHS = 6
DAYS_PER_MONTH = 30.44
KINDS = ["income", "essential", "discretionary", "debt", "investment"]


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None


def monthly_flows(txns: pd.DataFrame) -> pd.DataFrame:
    """Sum of amounts per calendar month (PeriodIndex) and category kind."""
    if txns.empty:
        return pd.DataFrame(columns=KINDS, dtype=float)
    table = txns.assign(month=txns["date"].dt.to_period("M")).pivot_table(
        index="month", columns="kind", values="amount", aggfunc="sum", fill_value=0.0
    )
    return table.reindex(columns=KINDS, fill_value=0.0).astype(float)


def balance_unset(data: UserData) -> bool:
    """No starting balance was ever given (₹0 dated after the first transaction): imported
    history would otherwise be ignored, so the account is assumed to start at ₹0 with it."""
    txns, profile = data.transactions, data.profile
    return (
        profile.opening_balance == 0
        and not txns.empty
        and profile.opening_balance_date > txns["date"].min().date()
    )


def cash_balance(data: UserData, as_of: date) -> float:
    """Opening balance (start of opening date) moved by every transaction since/before it."""
    txns, profile = data.transactions, data.profile
    if txns.empty:
        return profile.opening_balance
    signed = txns["amount"].where(txns["type"] == "income", -txns["amount"])
    dates = txns["date"].dt.date
    opening = txns["date"].min().date() if balance_unset(data) else profile.opening_balance_date
    if as_of >= opening:
        return profile.opening_balance + float(signed[(dates >= opening) & (dates <= as_of)].sum())
    return profile.opening_balance - float(signed[(dates > as_of) & (dates < opening)].sum())


def _loan_at(loan, as_of: date, today: date) -> tuple[float, float]:
    """(outstanding, emi) at `as_of`, anchored to the stored outstanding for today."""
    if loan.start_date > as_of:
        return 0.0, 0.0
    outstanding = loan.outstanding
    if as_of < today:

        def scheduled(d: date) -> float:
            return outstanding_after(
                loan.principal, loan.annual_interest_rate, loan.tenure_months,
                months_between(loan.start_date, d),
            )  # fmt: skip

        repaid_since = scheduled(as_of) - scheduled(today)
        outstanding = min(max(outstanding + repaid_since, 0.0), loan.principal)
    return outstanding, (loan.emi if outstanding > 0 else 0.0)


def build_twin(
    data: UserData, as_of: date | None = None, window: int = DEFAULT_WINDOW
) -> TwinState:
    as_of = as_of or data.today
    txns = data.transactions[data.transactions["date"].dt.date <= as_of]
    profile = data.profile
    notes: list[str] = []

    # ---------------- history span and averaging window ----------------
    last_complete = last_complete_month_end(as_of)
    flows = monthly_flows(txns)
    if flows.empty:
        span = 0
    else:
        first_month = flows.index.min().to_timestamp().date()
        span = max(months_between(first_month, last_complete) + 1, 0)
    n = min(window, span)
    window_periods = pd.period_range(end=pd.Period(last_complete, "M"), periods=n, freq="M")
    averages = flows.reindex(window_periods, fill_value=0.0).mean() if n else None
    recent_periods = pd.period_range(
        end=pd.Period(last_complete, "M"), periods=min(RECENT_MONTHS, span), freq="M"
    )
    recent = flows.reindex(recent_periods, fill_value=0.0)

    # ---------------- flows: observed or declared ----------------
    sources: dict[str, str] = {}
    if n:
        income = float(averages["income"])
        essential = float(averages["essential"])
        discretionary = float(averages["discretionary"])
        sources.update(income="observed", essential="observed", discretionary="observed")
        if n < window:
            notes.append(f"Averages use only {n} complete month(s) of history; more data will "
                         "make them more reliable.")  # fmt: skip
    else:
        income = profile.declared_monthly_income
        essential = profile.monthly_essential_expenses
        discretionary = profile.monthly_discretionary_expenses
        sources.update(income="declared", essential="declared", discretionary="declared")
        notes.append("No complete month of transactions yet; using your declared profile values.")

    loans = [_loan_at(loan, as_of, data.today) for loan in data.loans]
    scheduled_emi = sum(emi for _, emi in loans)
    observed_debt = float(averages["debt"]) if n else 0.0
    if observed_debt > 0 or (n and scheduled_emi == 0):
        debt_payments, sources["debt_payments"] = observed_debt, "observed"
    else:
        debt_payments, sources["debt_payments"] = scheduled_emi, "holdings"

    months_back = months_between(as_of, data.today)
    holdings = [
        (
            inv.asset_type,
            value_months_ago(
                inv.current_value, inv.monthly_contribution, inv.expected_annual_return, months_back
            ),
        )
        for inv in data.investments
    ]
    planned_contrib = sum(inv.monthly_contribution for inv in data.investments)
    observed_inv = float(averages["investment"]) if n else 0.0
    if observed_inv > 0 or (n and planned_contrib == 0):
        invest, sources["investment_contributions"] = observed_inv, "observed"
    else:
        invest, sources["investment_contributions"] = planned_contrib, "holdings"

    by_category: dict[str, float] = {}
    discretionary_by_category: dict[str, float] = {}
    if n:
        window_txns = txns[
            (txns["type"] == "expense") & (txns["date"].dt.to_period("M").isin(window_periods))
        ]
        averages_by = (window_txns.groupby("category")["amount"].sum() / n).sort_values(
            ascending=False
        )
        by_category = averages_by.to_dict()
        discretionary_names = set(
            window_txns.loc[window_txns["kind"] == "discretionary", "category"]
        )
        discretionary_by_category = {
            c: v for c, v in by_category.items() if c in discretionary_names
        }

    # ---------------- balances ----------------
    investments_value = sum(value for _, value in holdings)
    allocation: dict[str, float] = {}
    for asset_type, value in holdings:
        allocation[asset_type] = allocation.get(asset_type, 0.0) + value
    allocation = (
        {k: v / investments_value for k, v in allocation.items()} if investments_value else {}
    )

    total_debt = sum(outstanding for outstanding, _ in loans)
    active_goals = [g for g in data.goals if g.status != "paused"]
    goals_saved = sum(g.current_amount for g in active_goals)
    cash = cash_balance(data, as_of)
    if balance_unset(data):
        notes.append("No starting bank balance is set, so cash is the net of your recorded "
                     "transactions from ₹0. Set your real balance in Profile.")  # fmt: skip
    if as_of < data.today:
        notes.append("Emergency fund and goal balances use today's values (no history is stored).")

    goals = [
        GoalProgress(
            id=g.id,
            name=g.name,
            target_amount=g.target_amount,
            current_amount=g.current_amount,
            progress_pct=min(g.current_amount / g.target_amount, 1.0) * 100,
            remaining=max(g.target_amount - g.current_amount, 0.0),
            monthly_contribution=g.monthly_contribution,
            target_date=g.target_date,
            priority=g.priority,
            status=g.status,
        )
        for g in sorted(data.goals, key=lambda g: (g.priority, g.id))
    ]

    return derive(
        TwinState(
            as_of=as_of,
            window_months=n,
            window_start=window_periods[0].to_timestamp().date() if n else None,
            window_end=last_complete if n else None,
            months_of_history=span,
            monthly_income=income,
            essential_expenses=essential,
            discretionary_expenses=discretionary,
            debt_payments=debt_payments,
            investment_contributions=invest,
            expenses_by_category=by_category,
            discretionary_by_category=discretionary_by_category,
            cash_balance=cash,
            emergency_fund=profile.emergency_fund,
            investments_value=investments_value,
            investment_allocation=allocation,
            total_debt=total_debt,
            goals_saved=goals_saved,
            recent_months=[
                MonthFlow(str(p), *(float(recent.loc[p, k]) for k in KINDS)) for p in recent.index
            ],
            goals=goals,
            sources=sources,
            notes=notes,
            **_UNDERIVED,
        )
    )


# Placeholders for the fields `derive` computes, so there is one copy of each formula.
_UNDERIVED = dict.fromkeys(
    ("monthly_expenses", "net_cash_flow", "disposable_income", "burn_rate_daily", "net_worth",
     "savings_ratio", "expense_ratio", "debt_to_income", "emergency_months", "investment_rate"),
    0.0,
)  # fmt: skip


def derive(t: TwinState) -> TwinState:
    """Recompute every derived field from the base flows and balances. Used by the builder
    and by the simulator, so a simulated future state is scored with identical formulas."""
    income, essential, discretionary = (
        t.monthly_income,
        t.essential_expenses,
        t.discretionary_expenses,
    )
    debt, invest = t.debt_payments, t.investment_contributions
    expenses = essential + discretionary
    return replace(
        t,
        monthly_expenses=expenses,
        net_cash_flow=income - expenses - debt - invest,
        disposable_income=income - essential - debt,
        burn_rate_daily=(expenses + debt) / DAYS_PER_MONTH,
        net_worth=t.cash_balance
        + t.emergency_fund
        + t.investments_value
        + t.goals_saved
        - t.total_debt,
        savings_ratio=_ratio(income - expenses - debt, income),
        expense_ratio=_ratio(expenses, income),
        debt_to_income=_ratio(debt, income),
        emergency_months=_ratio(t.emergency_fund, essential + debt),
        investment_rate=_ratio(invest, income),
    )


def monthly_snapshot_dates(data: UserData) -> list[date]:
    """Month-ends of every complete month with history, up to today."""
    if data.transactions.empty:
        return []
    first = data.transactions["date"].min().date().replace(day=1)
    last = last_complete_month_end(data.today)
    dates, d = [], month_end(first)
    while d <= last:
        dates.append(d)
        d = month_end(add_months(d.replace(day=1), 1))
    return dates
