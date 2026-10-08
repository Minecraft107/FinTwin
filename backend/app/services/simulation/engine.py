"""Deterministic month-by-month financial projection. Pure: same inputs, same outputs.

Each month m = 1..H (month 1 = the calendar month after `today`):
    income, essential, discretionary  <- baseline averages, adjusted by active changes
    EMIs      <- every loan amortised: interest = outstanding × r/12, principal = EMI − interest
    net       = income + one-time inflows − essential − discretionary − EMIs − SIPs
                − one-time outflows
    investments = investments × (1 + return/12) + SIP
    cash     += net
    goals     <- funded from the month's recurring surplus, in priority order, capped by each
                 goal's planned contribution and by cash above a one-month buffer of outgoings
                 (so goal saving never drains the account)
    if cash < 0: draw from the emergency fund; anything left negative is a *shortfall*
"""

import copy
import math
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.services.financial.formulas import emi as emi_formula
from app.services.simulation.scenarios import (
    Change,
    ExpenseChange,
    ExtraSavings,
    GoalDelay,
    IncomeChange,
    LargePurchase,
    NewLoan,
    OneTimeIncome,
    SipChange,
)
from app.utils.dates import add_months, months_between


@dataclass
class LoanState:
    name: str
    outstanding: float
    annual_rate: float
    emi: float

    def pay(self) -> float:
        if self.outstanding <= 0.005:
            return 0.0
        interest = self.outstanding * self.annual_rate / 12
        payment = min(self.emi, self.outstanding + interest)
        self.outstanding = max(self.outstanding + interest - payment, 0.0)
        return payment


@dataclass
class GoalState:
    id: int
    name: str
    target: float
    current: float
    planned: float
    priority: int
    target_date: date | None
    status: str = "active"
    completed: str | None = None  # YYYY-MM when the target is reached


@dataclass(frozen=True)
class Baseline:
    """Starting point, taken from the Digital Twin (see service.baseline_from)."""

    today: date
    income: float
    essential: float
    discretionary: float
    sip: float
    untracked_emi: float  # observed EMIs with no matching loan record: kept constant
    cash: float
    emergency_fund: float
    investments: float
    investment_return: float  # annual, value-weighted across holdings
    loans: list[LoanState] = field(default_factory=list)
    goals: list[GoalState] = field(default_factory=list)


@dataclass(frozen=True)
class Month:
    month: str
    income: float
    essential: float
    discretionary: float
    emi: float
    sip: float
    one_time_out: float
    one_time_in: float
    net_cash_flow: float
    goal_contributions: float
    cash: float
    emergency_fund: float
    emergency_drawn: float
    investments: float
    debt: float
    goals_saved: float
    net_worth: float
    shortfall: float
    goal_balances: dict[int, float]

    @property
    def recurring_surplus(self) -> float:
        return self.income - self.essential - self.discretionary - self.emi - self.sip


@dataclass
class Projection:
    months: list[Month]
    goals: list[GoalState]
    notes: list[str]

    def at(self, k: int) -> Month:
        return self.months[min(k, len(self.months)) - 1]


def month_index(today: date, d: date | None) -> int:
    """1-based projection month for a date; dates in the current or past months -> month 1."""
    if d is None:
        return 1
    return max(months_between(today, d), 1)


def project(
    base: Baseline, changes: list[Change], horizon: int, inflation_pct: float = 0.0
) -> Projection:
    notes: list[str] = []
    h = horizon + 1  # arrays are indexed 1..horizon
    income_mult, income_add = [1.0] * h, [0.0] * h
    mult = {"essential": [1.0] * h, "discretionary": [1.0] * h}
    add = {"essential": [0.0] * h, "discretionary": [0.0] * h}
    sip_add, out_once, in_once = [0.0] * h, [0.0] * h, [0.0] * h
    new_loans: dict[int, list[tuple[LoanState, float]]] = {}
    goals = copy.deepcopy(base.goals)
    loans = copy.deepcopy(base.loans)

    def window(start: date | None, duration: int | None) -> range | None:
        first = month_index(base.today, start)
        if first > horizon:
            notes.append(f"A change starting {start} is beyond the {horizon}-month horizon.")
            return None
        last = horizon if duration is None else min(first + duration - 1, horizon)
        return range(first, last + 1)

    for change in changes:
        if isinstance(change, (IncomeChange, ExpenseChange)):
            months = window(change.start_date, change.duration_months)
            for m in months or ():
                if isinstance(change, IncomeChange):
                    if change.pct is not None:
                        income_mult[m] *= 1 + change.pct / 100
                    else:
                        income_add[m] += change.amount
                elif change.pct is not None:
                    mult[change.kind][m] *= 1 + change.pct / 100
                else:
                    add[change.kind][m] += change.amount
        elif isinstance(change, ExtraSavings):
            for m in window(change.start_date, None) or ():
                add["discretionary"][m] -= change.amount
        elif isinstance(change, SipChange):
            for m in window(change.start_date, None) or ():
                sip_add[m] += change.amount
        elif isinstance(change, (LargePurchase, OneTimeIncome)):
            m = month_index(base.today, change.date)
            if m > horizon:
                notes.append(f"An event on {change.date} is beyond the {horizon}-month horizon.")
                continue
            if isinstance(change, OneTimeIncome):
                in_once[m] += change.amount
            elif change.financed_by_loan:
                emi = emi_formula(change.amount, change.loan_annual_rate, change.loan_tenure_months)
                loan = LoanState(
                    change.label or "Purchase loan", change.amount, change.loan_annual_rate, emi
                )
                new_loans.setdefault(m, []).append((loan, 0.0))
            else:
                out_once[m] += change.amount
        elif isinstance(change, NewLoan):
            m = month_index(base.today, change.start_date)
            if m > horizon:
                notes.append(f"A loan starting {change.start_date} is beyond the horizon.")
                continue
            emi = emi_formula(change.principal, change.annual_rate, change.tenure_months)
            loan = LoanState(change.label or "New loan", change.principal, change.annual_rate, emi)
            new_loans.setdefault(m, []).append(
                (loan, change.principal if change.disbursed_to_cash else 0.0)
            )
        elif isinstance(change, GoalDelay):
            goal = next((g for g in goals if g.id == change.goal_id), None)
            if goal and goal.target_date:
                goal.target_date = add_months(goal.target_date, change.months)

    cash, ef, investments = base.cash, base.emergency_fund, base.investments
    start = pd.Period(base.today, "M")
    months: list[Month] = []
    for m in range(1, horizon + 1):
        period = str(start + m)
        inflation = (1 + inflation_pct / 100) ** (m / 12)
        income = max(base.income * income_mult[m] + income_add[m], 0.0)
        essential = max(
            base.essential * inflation * mult["essential"][m] + add["essential"][m], 0.0
        )
        discretionary = max(
            base.discretionary * inflation * mult["discretionary"][m] + add["discretionary"][m], 0.0
        )
        emi = sum(loan.pay() for loan in loans) + base.untracked_emi
        for loan, disbursed in new_loans.get(m, []):  # first EMI falls due the month after
            loans.append(loan)
            in_once[m] += disbursed
        sip = max(base.sip + sip_add[m], 0.0)
        net = income + in_once[m] - essential - discretionary - emi - sip - out_once[m]
        investments = investments * (1 + base.investment_return / 12) + sip
        cash += net

        buffer = essential + discretionary + emi
        surplus = income - essential - discretionary - emi - sip
        available = min(max(surplus, 0.0), max(cash - buffer, 0.0))
        contributed = 0.0
        for goal in sorted(goals, key=lambda g: (g.priority, g.id)):
            if goal.status != "active" or goal.completed:
                continue
            amount = min(goal.planned, goal.target - goal.current, available)
            if amount <= 0:
                continue
            goal.current += amount
            available -= amount
            contributed += amount
            if goal.current >= goal.target - 0.005:
                goal.completed = period
        cash -= contributed

        drawn = 0.0
        if cash < 0 and ef > 0:
            drawn = min(-cash, ef)
            ef -= drawn
            cash += drawn
        debt = sum(loan.outstanding for loan in loans)
        goals_saved = sum(g.current for g in goals if g.status != "paused")
        months.append(
            Month(
                month=period, income=income, essential=essential, discretionary=discretionary,
                emi=emi, sip=sip, one_time_out=out_once[m], one_time_in=in_once[m],
                net_cash_flow=net, goal_contributions=contributed, cash=cash, emergency_fund=ef,
                emergency_drawn=drawn, investments=investments, debt=debt, goals_saved=goals_saved,
                net_worth=cash + ef + investments + goals_saved - debt, shortfall=max(-cash, 0.0),
                goal_balances={g.id: g.current for g in goals},
            )
        )  # fmt: skip
    return Projection(months, goals, notes)


def months_to_save(amount: float, monthly_surplus: float) -> int | None:
    """How many months of the current surplus it takes to save `amount` (None if never)."""
    if monthly_surplus <= 0:
        return None
    return math.ceil(amount / monthly_surplus)
