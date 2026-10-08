"""Inputs and output of the Digital Twin builder. Plain dataclasses: no Flask, no SQLAlchemy."""

from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd

# ---------------------------------------------------------------- inputs


@dataclass(frozen=True)
class ProfileData:
    declared_monthly_income: float = 0.0
    opening_balance: float = 0.0
    opening_balance_date: date = date(2000, 1, 1)
    emergency_fund: float = 0.0
    monthly_essential_expenses: float = 0.0
    monthly_discretionary_expenses: float = 0.0


@dataclass(frozen=True)
class InvestmentData:
    asset_type: str
    current_value: float
    monthly_contribution: float = 0.0
    expected_annual_return: float = 0.0


@dataclass(frozen=True)
class LoanData:
    principal: float
    outstanding: float
    annual_interest_rate: float
    emi: float
    tenure_months: int
    start_date: date


@dataclass(frozen=True)
class GoalData:
    id: int
    name: str
    target_amount: float
    current_amount: float = 0.0
    target_date: date | None = None
    priority: int = 3
    monthly_contribution: float = 0.0
    status: str = "active"


TRANSACTION_COLUMNS = ["date", "amount", "type", "category", "kind", "merchant", "description"]


def empty_transactions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.Series(dtype="datetime64[ns]"),
            "amount": pd.Series(dtype=float),
            **{c: pd.Series(dtype=object) for c in TRANSACTION_COLUMNS[2:]},
        }
    )


@dataclass
class UserData:
    """Everything the twin is derived from. `transactions.kind` is the category kind
    (income / essential / discretionary / debt / investment)."""

    transactions: pd.DataFrame = field(default_factory=empty_transactions)
    profile: ProfileData = field(default_factory=ProfileData)
    investments: list[InvestmentData] = field(default_factory=list)
    loans: list[LoanData] = field(default_factory=list)
    goals: list[GoalData] = field(default_factory=list)
    today: date = field(default_factory=date.today)  # "now" for anchoring stored balances


# ---------------------------------------------------------------- output


@dataclass(frozen=True)
class MonthFlow:
    month: str  # YYYY-MM
    income: float
    essential: float
    discretionary: float
    debt: float
    investment: float

    @property
    def expenses(self) -> float:
        return self.essential + self.discretionary

    @property
    def net(self) -> float:
        return self.income - self.essential - self.discretionary - self.debt - self.investment


@dataclass(frozen=True)
class GoalProgress:
    id: int
    name: str
    target_amount: float
    current_amount: float
    progress_pct: float
    remaining: float
    monthly_contribution: float
    target_date: date | None
    priority: int
    status: str


@dataclass(frozen=True)
class TwinState:
    as_of: date
    window_months: int  # complete months averaged; 0 = declared profile values used
    window_start: date | None
    window_end: date | None
    months_of_history: int
    # Monthly flows (averages over the window)
    monthly_income: float
    monthly_expenses: float  # essential + discretionary consumption
    essential_expenses: float
    discretionary_expenses: float
    debt_payments: float  # EMIs
    investment_contributions: float  # SIPs etc.
    expenses_by_category: dict[str, float]
    net_cash_flow: float  # income - expenses - debt - investments
    disposable_income: float  # income - essential - debt
    burn_rate_daily: float  # (expenses + debt) per day
    # Balances
    cash_balance: float
    emergency_fund: float
    investments_value: float
    investment_allocation: dict[str, float]  # asset_type -> share of portfolio
    total_debt: float
    goals_saved: float
    net_worth: float
    # Ratios (None when undefined, e.g. zero income)
    savings_ratio: float | None  # (income - expenses - debt) / income; investing counts as saving
    expense_ratio: float | None  # expenses / income
    debt_to_income: float | None  # debt payments / income
    emergency_months: float | None  # emergency fund / (essential + debt payments)
    investment_rate: float | None  # investment contributions / income
    # Detail
    recent_months: list[MonthFlow]  # up to 6 complete months, oldest first
    goals: list[GoalProgress]
    sources: dict[str, str]  # metric -> observed | declared | holdings
    notes: list[str]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["recent_months"] = [
            {**asdict(m), "expenses": round(m.expenses, 2), "net": round(m.net, 2)}
            for m in self.recent_months
        ]
        return _round(data)


def _round(value):
    if isinstance(value, float):
        return round(value, 4) if abs(value) < 10 else round(value, 2)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    return value
