from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.base import Money, TimestampMixin, enum_column
from app.models.enums import EmploymentType, RiskTolerance


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))

    profile: Mapped["FinancialProfile | None"] = relationship(
        back_populates="user", uselist=False, passive_deletes=True
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class FinancialProfile(TimestampMixin, db.Model):
    """Self-declared financial facts. Used directly for balances, and as the fallback for
    income/expenses when there is not yet enough transaction history (see TwinState)."""

    __tablename__ = "financial_profiles"
    __table_args__ = (
        CheckConstraint(
            "declared_monthly_income >= 0 AND opening_balance >= 0 AND emergency_fund >= 0"
            " AND monthly_essential_expenses >= 0 AND monthly_discretionary_expenses >= 0",
            name="non_negative_amounts",
        ),
        CheckConstraint("dependents >= 0", name="dependents_non_negative"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    declared_monthly_income: Mapped[Decimal] = mapped_column(Money, default=0)
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=0)
    opening_balance_date: Mapped[date] = mapped_column(default=date.today)
    emergency_fund: Mapped[Decimal] = mapped_column(Money, default=0)
    monthly_essential_expenses: Mapped[Decimal] = mapped_column(Money, default=0)
    monthly_discretionary_expenses: Mapped[Decimal] = mapped_column(Money, default=0)
    risk_tolerance: Mapped[RiskTolerance] = mapped_column(
        enum_column(RiskTolerance, "risk_tolerance"), default=RiskTolerance.MEDIUM
    )
    dependents: Mapped[int] = mapped_column(default=0)
    employment_type: Mapped[EmploymentType] = mapped_column(
        enum_column(EmploymentType, "employment_type"), default=EmploymentType.SALARIED
    )

    user: Mapped[User] = relationship(back_populates="profile")
