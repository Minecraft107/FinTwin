from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import Money, TimestampMixin, enum_column, user_fk
from app.models.enums import AssetType, GoalStatus, LoanType


class Investment(TimestampMixin, db.Model):
    __tablename__ = "investments"
    __table_args__ = (
        CheckConstraint(
            "invested_amount >= 0 AND current_value >= 0 AND monthly_contribution >= 0",
            name="non_negative_amounts",
        ),
        CheckConstraint(
            "expected_annual_return >= -1 AND expected_annual_return <= 1", name="return_range"
        ),
    )

    user_id: Mapped[int] = user_fk()
    name: Mapped[str] = mapped_column(String(120))
    asset_type: Mapped[AssetType] = mapped_column(enum_column(AssetType, "asset_type"))
    invested_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    current_value: Mapped[Decimal] = mapped_column(Money, default=0)
    monthly_contribution: Mapped[Decimal] = mapped_column(Money, default=0)
    expected_annual_return: Mapped[float] = mapped_column(default=0.0)  # fraction, 0.11 = 11%


class Loan(TimestampMixin, db.Model):
    __tablename__ = "loans"
    __table_args__ = (
        CheckConstraint("principal > 0", name="principal_positive"),
        CheckConstraint("outstanding >= 0 AND outstanding <= principal", name="outstanding_range"),
        CheckConstraint(
            "annual_interest_rate >= 0 AND annual_interest_rate <= 1", name="rate_range"
        ),
        CheckConstraint("emi > 0", name="emi_positive"),
        CheckConstraint("tenure_months > 0", name="tenure_positive"),
    )

    user_id: Mapped[int] = user_fk()
    name: Mapped[str] = mapped_column(String(120))
    loan_type: Mapped[LoanType] = mapped_column(enum_column(LoanType, "loan_type"))
    principal: Mapped[Decimal] = mapped_column(Money)
    outstanding: Mapped[Decimal] = mapped_column(Money)
    annual_interest_rate: Mapped[float]  # fraction, 0.10 = 10%
    emi: Mapped[Decimal] = mapped_column(Money)
    tenure_months: Mapped[int]
    start_date: Mapped[date]


class FinancialGoal(TimestampMixin, db.Model):
    __tablename__ = "financial_goals"
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="target_positive"),
        CheckConstraint(
            "current_amount >= 0 AND monthly_contribution >= 0", name="non_negative_amounts"
        ),
        CheckConstraint("priority BETWEEN 1 AND 5", name="priority_range"),
    )

    user_id: Mapped[int] = user_fk()
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[Decimal] = mapped_column(Money)
    current_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    target_date: Mapped[date | None]
    priority: Mapped[int] = mapped_column(default=3)  # 1 = highest
    monthly_contribution: Mapped[Decimal] = mapped_column(Money, default=0)
    status: Mapped[GoalStatus] = mapped_column(
        enum_column(GoalStatus, "goal_status"), default=GoalStatus.ACTIVE
    )
