"""Importing this package registers every table on db.metadata (needed by Alembic)."""

from app.models.analytics import FinancialHealthScore, FinancialSnapshot, ForecastResult, RiskAlert
from app.models.coach import CoachConversation, CoachMessage
from app.models.holdings import FinancialGoal, Investment, Loan
from app.models.ledger import ExpenseCategory, Transaction
from app.models.simulation import SimulationResult, SimulationScenario
from app.models.user import FinancialProfile, User

__all__ = [
    "CoachConversation",
    "CoachMessage",
    "ExpenseCategory",
    "FinancialGoal",
    "FinancialHealthScore",
    "FinancialProfile",
    "FinancialSnapshot",
    "ForecastResult",
    "Investment",
    "Loan",
    "RiskAlert",
    "SimulationResult",
    "SimulationScenario",
    "Transaction",
    "User",
]
