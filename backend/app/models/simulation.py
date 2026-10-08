from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import Money, TimestampMixin, enum_column, user_fk
from app.models.enums import Severity


class SimulationScenario(TimestampMixin, db.Model):
    __tablename__ = "simulation_scenarios"
    __table_args__ = (CheckConstraint("horizon_months > 0", name="horizon_positive"),)

    user_id: Mapped[int] = user_fk()
    name: Mapped[str] = mapped_column(String(120))
    # Heterogeneous by change type (purchase, loan, income change, ...), validated by pydantic.
    changes: Mapped[list] = mapped_column(JSON)
    horizon_months: Mapped[int] = mapped_column(default=24)

    results: Mapped[list["SimulationResult"]] = relationship(
        back_populates="scenario", passive_deletes=True, order_by="SimulationResult.id"
    )


class SimulationResult(TimestampMixin, db.Model):
    __tablename__ = "simulation_results"

    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), index=True
    )
    risk_level: Mapped[Severity] = mapped_column(enum_column(Severity, "risk_level"))
    health_score_before: Mapped[float]
    health_score_after: Mapped[float]
    cash_change_12m: Mapped[Decimal] = mapped_column(Money)
    impact: Mapped[dict] = mapped_column(JSON)
    timeline: Mapped[list] = mapped_column(JSON)

    scenario: Mapped[SimulationScenario] = relationship(back_populates="results")
