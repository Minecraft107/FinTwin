from datetime import date

from pydantic import Field

from app.models.enums import EmploymentType, RiskTolerance
from app.schemas.common import InModel, OutModel


def optional_amount():
    return Field(default=None, ge=0, le=1e11)


class ProfileUpdate(InModel):
    declared_monthly_income: float | None = optional_amount()
    opening_balance: float | None = optional_amount()
    opening_balance_date: date | None = None
    emergency_fund: float | None = optional_amount()
    monthly_essential_expenses: float | None = optional_amount()
    monthly_discretionary_expenses: float | None = optional_amount()
    risk_tolerance: RiskTolerance | None = None
    dependents: int | None = Field(default=None, ge=0, le=20)
    employment_type: EmploymentType | None = None


class ProfileOut(OutModel):
    declared_monthly_income: float
    opening_balance: float
    opening_balance_date: date
    emergency_fund: float
    monthly_essential_expenses: float
    monthly_discretionary_expenses: float
    risk_tolerance: RiskTolerance
    dependents: int
    employment_type: EmploymentType
