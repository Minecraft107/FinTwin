from datetime import date

from pydantic import Field, model_validator

from app.models.enums import AssetType, GoalStatus, LoanType
from app.schemas.common import InModel, OutModel

MAX = 1e11


class InvestmentIn(InModel):
    name: str = Field(min_length=1, max_length=120)
    asset_type: AssetType
    invested_amount: float = Field(default=0, ge=0, le=MAX)
    current_value: float = Field(default=0, ge=0, le=MAX)
    monthly_contribution: float = Field(default=0, ge=0, le=MAX)
    expected_annual_return: float = Field(default=0.0, ge=-1, le=1)


class InvestmentUpdate(InModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    asset_type: AssetType | None = None
    invested_amount: float | None = Field(default=None, ge=0, le=MAX)
    current_value: float | None = Field(default=None, ge=0, le=MAX)
    monthly_contribution: float | None = Field(default=None, ge=0, le=MAX)
    expected_annual_return: float | None = Field(default=None, ge=-1, le=1)


class InvestmentOut(OutModel):
    id: int
    name: str
    asset_type: AssetType
    invested_amount: float
    current_value: float
    monthly_contribution: float
    expected_annual_return: float


class LoanIn(InModel):
    name: str = Field(min_length=1, max_length=120)
    loan_type: LoanType
    principal: float = Field(gt=0, le=MAX)
    outstanding: float | None = Field(default=None, ge=0, le=MAX)  # default: principal
    annual_interest_rate: float = Field(ge=0, le=1)
    emi: float | None = Field(default=None, gt=0, le=MAX)  # default: computed from terms
    tenure_months: int = Field(gt=0, le=600)
    start_date: date

    @model_validator(mode="after")
    def _outstanding_le_principal(self):
        if self.outstanding is not None and self.outstanding > self.principal:
            raise ValueError("outstanding cannot exceed principal")
        return self


class LoanUpdate(InModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    loan_type: LoanType | None = None
    principal: float | None = Field(default=None, gt=0, le=MAX)
    outstanding: float | None = Field(default=None, ge=0, le=MAX)
    annual_interest_rate: float | None = Field(default=None, ge=0, le=1)
    emi: float | None = Field(default=None, gt=0, le=MAX)
    tenure_months: int | None = Field(default=None, gt=0, le=600)
    start_date: date | None = None


class LoanOut(OutModel):
    id: int
    name: str
    loan_type: LoanType
    principal: float
    outstanding: float
    annual_interest_rate: float
    emi: float
    tenure_months: int
    start_date: date


class GoalIn(InModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: float = Field(gt=0, le=MAX)
    current_amount: float = Field(default=0, ge=0, le=MAX)
    target_date: date | None = None
    priority: int = Field(default=3, ge=1, le=5)
    monthly_contribution: float = Field(default=0, ge=0, le=MAX)
    status: GoalStatus = GoalStatus.ACTIVE


class GoalUpdate(InModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: float | None = Field(default=None, gt=0, le=MAX)
    current_amount: float | None = Field(default=None, ge=0, le=MAX)
    target_date: date | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    monthly_contribution: float | None = Field(default=None, ge=0, le=MAX)
    status: GoalStatus | None = None


class GoalOut(OutModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    target_date: date | None
    priority: int
    monthly_contribution: float
    status: GoalStatus
