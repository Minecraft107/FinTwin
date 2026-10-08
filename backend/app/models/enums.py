from enum import StrEnum


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class CategoryKind(StrEnum):
    ESSENTIAL = "essential"
    DISCRETIONARY = "discretionary"
    INCOME = "income"
    INVESTMENT = "investment"
    DEBT = "debt"


class PaymentMethod(StrEnum):
    UPI = "upi"
    CARD = "card"
    CASH = "cash"
    NETBANKING = "netbanking"
    AUTO_DEBIT = "auto_debit"
    OTHER = "other"


class CategorySource(StrEnum):
    IMPORT = "import"  # category supplied by the user's file / seed
    MEMORY = "memory"  # learned from the user's earlier manual corrections
    RULE = "rule"
    ML = "ml"
    MANUAL = "manual"


class RiskTolerance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EmploymentType(StrEnum):
    SALARIED = "salaried"
    SELF_EMPLOYED = "self_employed"
    STUDENT = "student"
    OTHER = "other"


class AssetType(StrEnum):
    SIP_EQUITY = "sip_equity"
    MUTUAL_FUND = "mutual_fund"
    STOCKS = "stocks"
    FD = "fd"
    PPF = "ppf"
    GOLD = "gold"
    OTHER = "other"


class LoanType(StrEnum):
    HOME = "home"
    CAR = "car"
    PERSONAL = "personal"
    EDUCATION = "education"
    CREDIT_CARD = "credit_card"
    OTHER = "other"


class GoalStatus(StrEnum):
    ACTIVE = "active"
    ACHIEVED = "achieved"
    PAUSED = "paused"


class SnapshotPeriod(StrEnum):
    MONTHLY = "monthly"
    ON_CHANGE = "on_change"


class ForecastTarget(StrEnum):
    EXPENSES = "expenses"
    CASH_FLOW = "cash_flow"
    SAVINGS = "savings"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(StrEnum):
    ACTIVE = "active"
    DISMISSED = "dismissed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
