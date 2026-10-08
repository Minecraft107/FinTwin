from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import Money, TimestampMixin, enum_column, user_fk
from app.models.enums import AlertStatus, ForecastTarget, Severity, SnapshotPeriod


class FinancialSnapshot(TimestampMixin, db.Model):
    """Persisted copy of the derived Digital Twin's headline metrics at a point in time."""

    __tablename__ = "financial_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "as_of", "period", name="one_per_period"),)

    user_id: Mapped[int] = user_fk()
    as_of: Mapped[date]
    period: Mapped[SnapshotPeriod] = mapped_column(enum_column(SnapshotPeriod, "snapshot_period"))
    income: Mapped[Decimal] = mapped_column(Money)
    expenses: Mapped[Decimal] = mapped_column(Money)
    net_cash_flow: Mapped[Decimal] = mapped_column(Money)
    savings_ratio: Mapped[float]
    expense_ratio: Mapped[float]
    debt_to_income: Mapped[float]
    emergency_months: Mapped[float]
    cash_balance: Mapped[Decimal] = mapped_column(Money)
    investments_value: Mapped[Decimal] = mapped_column(Money)
    total_debt: Mapped[Decimal] = mapped_column(Money)
    net_worth: Mapped[Decimal] = mapped_column(Money)
    months_of_history: Mapped[int]

    health_score: Mapped["FinancialHealthScore | None"] = relationship(
        back_populates="snapshot", uselist=False, passive_deletes=True
    )


class FinancialHealthScore(TimestampMixin, db.Model):
    """Total score plus every component sub-score (0-100), so history is explainable.
    A component is NULL when it was excluded for lack of data."""

    __tablename__ = "financial_health_scores"
    __table_args__ = (CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),)

    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("financial_snapshots.id", ondelete="CASCADE"), unique=True
    )
    score: Mapped[float]
    grade: Mapped[str] = mapped_column(String(2))
    savings: Mapped[float | None]
    emergency_fund: Mapped[float | None]
    debt: Mapped[float | None]
    cash_flow: Mapped[float | None]
    investments: Mapped[float | None]
    goals: Mapped[float | None]
    spending: Mapped[float | None]

    snapshot: Mapped[FinancialSnapshot] = relationship(back_populates="health_score")


class ForecastResult(TimestampMixin, db.Model):
    __tablename__ = "forecast_results"
    __table_args__ = (
        CheckConstraint("horizon_months > 0", name="horizon_positive"),
        Index("ix_forecast_results_user_target_time", "user_id", "target", "generated_at"),
    )

    user_id: Mapped[int] = user_fk()
    target: Mapped[ForecastTarget] = mapped_column(enum_column(ForecastTarget, "forecast_target"))
    model_name: Mapped[str] = mapped_column(String(40))
    horizon_months: Mapped[int]
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    backtest_mae: Mapped[float | None]
    points: Mapped[list] = mapped_column(JSON)  # [{month, value, lower, upper}] — a derived series


class RiskAlert(TimestampMixin, db.Model):
    __tablename__ = "risk_alerts"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint", name="unique_fingerprint"),)

    user_id: Mapped[int] = user_fk()
    type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[Severity] = mapped_column(enum_column(Severity, "severity"))
    title: Mapped[str] = mapped_column(String(160))
    explanation: Mapped[str] = mapped_column(String(1000))
    affected_metric: Mapped[str] = mapped_column(String(60))
    metric_value: Mapped[float | None]
    recommended_action: Mapped[str] = mapped_column(String(500))
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    status: Mapped[AlertStatus] = mapped_column(
        enum_column(AlertStatus, "alert_status"), default=AlertStatus.ACTIVE
    )
    # Stable hash of (type, subject, period) so re-running detection never duplicates alerts.
    fingerprint: Mapped[str] = mapped_column(String(64))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
