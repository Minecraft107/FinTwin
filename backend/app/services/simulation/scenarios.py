"""What-If scenario definitions: validated, typed changes (one discriminated union)."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.common import InModel

MAX = 1e10


class _AmountOrPct(InModel):
    amount: float | None = Field(default=None, ge=-MAX, le=MAX)  # rupees per month (+/-)
    pct: float | None = Field(default=None, ge=-100, le=500)  # percent change (+/-)
    start_date: dt.date | None = None  # None = from the first projected month
    duration_months: int | None = Field(default=None, ge=1, le=120)  # None = permanent

    @model_validator(mode="after")
    def _exactly_one(self):
        if (self.amount is None) == (self.pct is None):
            raise ValueError("give exactly one of 'amount' or 'pct'")
        return self


class LargePurchase(InModel):
    type: Literal["large_purchase"]
    amount: float = Field(gt=0, le=MAX)
    date: dt.date | None = None
    label: str | None = Field(default=None, max_length=80)
    financed_by_loan: bool = False
    loan_annual_rate: float = Field(default=0.12, ge=0, le=0.6)
    loan_tenure_months: int = Field(default=24, ge=1, le=360)


class IncomeChange(_AmountOrPct):
    type: Literal["income_change"]


class ExpenseChange(_AmountOrPct):
    type: Literal["expense_change"]
    kind: Literal["essential", "discretionary"] = "discretionary"


class SipChange(InModel):
    type: Literal["sip_change"]
    amount: float = Field(ge=-MAX, le=MAX)  # monthly change, may be negative
    start_date: dt.date | None = None


class NewLoan(InModel):
    type: Literal["new_loan"]
    principal: float = Field(gt=0, le=MAX)
    annual_rate: float = Field(ge=0, le=0.6)
    tenure_months: int = Field(ge=1, le=360)
    start_date: dt.date | None = None
    disbursed_to_cash: bool = True  # False: the money is spent immediately (e.g. on a car)
    label: str | None = Field(default=None, max_length=80)


class ExtraSavings(InModel):
    type: Literal["extra_savings"]
    amount: float = Field(gt=0, le=MAX)  # saved by spending this much less (discretionary)
    start_date: dt.date | None = None


class GoalDelay(InModel):
    type: Literal["goal_delay"]
    goal_id: int
    months: int = Field(ge=1, le=120)


class OneTimeIncome(InModel):
    type: Literal["one_time_income"]
    amount: float = Field(gt=0, le=MAX)
    date: dt.date | None = None
    label: str | None = Field(default=None, max_length=80)


Change = Annotated[
    LargePurchase | IncomeChange | ExpenseChange | SipChange | NewLoan | ExtraSavings
    | GoalDelay | OneTimeIncome,
    Field(discriminator="type"),
]  # fmt: skip


class Scenario(InModel):
    name: str | None = Field(default=None, max_length=120)
    changes: list[Change] = Field(min_length=1, max_length=10)
    horizon_months: int = Field(default=24, ge=6, le=60)
    inflation_pct: float = Field(default=0.0, ge=0, le=20)  # annual, applied to spending
