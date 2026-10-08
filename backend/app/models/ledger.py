import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import Money, TimestampMixin, enum_column, user_fk
from app.models.enums import CategoryKind, CategorySource, PaymentMethod, TransactionType


class ExpenseCategory(TimestampMixin, db.Model):
    """Global reference list (income categories included). `kind` drives essential vs
    discretionary analytics, debt-to-income and investment-rate calculations."""

    __tablename__ = "expense_categories"

    name: Mapped[str] = mapped_column(String(50), unique=True)
    kind: Mapped[CategoryKind] = mapped_column(enum_column(CategoryKind, "category_kind"))
    color: Mapped[str] = mapped_column(String(7))
    icon: Mapped[str] = mapped_column(String(40))


class Transaction(TimestampMixin, db.Model):
    """Single ledger: income is a transaction with type='income' (no separate income table)."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "category_confidence IS NULL"
            " OR (category_confidence >= 0 AND category_confidence <= 1)",
            name="confidence_range",
        ),
        Index("ix_transactions_user_date", "user_id", "date"),
        Index("ix_transactions_user_category", "user_id", "category_id"),
    )

    user_id: Mapped[int] = user_fk()
    date: Mapped[dt.date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    type: Mapped[TransactionType] = mapped_column(enum_column(TransactionType, "transaction_type"))
    category_id: Mapped[int] = mapped_column(
        ForeignKey("expense_categories.id", ondelete="RESTRICT")
    )
    description: Mapped[str] = mapped_column(String(255))
    merchant: Mapped[str | None] = mapped_column(String(120))
    payment_method: Mapped[PaymentMethod] = mapped_column(
        enum_column(PaymentMethod, "payment_method"), default=PaymentMethod.OTHER
    )
    is_recurring: Mapped[bool] = mapped_column(default=False)
    category_source: Mapped[CategorySource] = mapped_column(
        enum_column(CategorySource, "category_source"), default=CategorySource.MANUAL
    )
    category_confidence: Mapped[float | None]

    category: Mapped[ExpenseCategory] = relationship(lazy="joined")
