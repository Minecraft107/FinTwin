from app.extensions import db
from app.models import ExpenseCategory
from app.models.enums import CategoryKind

ESS, DIS, INC, INV, DEBT = (
    CategoryKind.ESSENTIAL,
    CategoryKind.DISCRETIONARY,
    CategoryKind.INCOME,
    CategoryKind.INVESTMENT,
    CategoryKind.DEBT,
)

# (name, kind, color, lucide icon). "Food" is split into Groceries (essential) and
# Food & Dining (discretionary) so the essential-vs-discretionary analysis is meaningful.
CATEGORIES: list[tuple[str, CategoryKind, str, str]] = [
    ("Salary", INC, "#059669", "briefcase"),
    ("Freelance", INC, "#10b981", "laptop"),
    ("Bonus", INC, "#34d399", "gift"),
    ("Interest", INC, "#6ee7b7", "percent"),
    ("Other Income", INC, "#a7f3d0", "plus-circle"),
    ("Housing", ESS, "#1e40af", "home"),
    ("Utilities", ESS, "#2563eb", "zap"),
    ("Groceries", ESS, "#3b82f6", "shopping-basket"),
    ("Transport", ESS, "#60a5fa", "car"),
    ("Healthcare", ESS, "#0ea5e9", "heart-pulse"),
    ("Insurance", ESS, "#0284c7", "shield"),
    ("Education", ESS, "#0369a1", "graduation-cap"),
    ("Family Support", ESS, "#075985", "users"),
    ("Food & Dining", DIS, "#f97316", "utensils"),
    ("Shopping", DIS, "#ec4899", "shopping-bag"),
    ("Entertainment", DIS, "#a855f7", "film"),
    ("Subscriptions", DIS, "#8b5cf6", "repeat"),
    ("Travel", DIS, "#f59e0b", "plane"),
    ("Personal Care", DIS, "#f472b6", "sparkles"),
    ("Other", DIS, "#94a3b8", "circle-help"),
    ("Investment", INV, "#14b8a6", "trending-up"),
    ("EMI/Debt", DEBT, "#dc2626", "landmark"),
]

FALLBACK_EXPENSE_CATEGORY = "Other"
FALLBACK_INCOME_CATEGORY = "Other Income"


def ensure_categories() -> int:
    """Idempotently insert/update the reference categories. Returns how many were created."""
    existing = {c.name: c for c in db.session.scalars(db.select(ExpenseCategory))}
    created = 0
    for name, kind, color, icon in CATEGORIES:
        category = existing.get(name)
        if category is None:
            db.session.add(ExpenseCategory(name=name, kind=kind, color=color, icon=icon))
            created += 1
        else:
            category.kind, category.color, category.icon = kind, color, icon
    db.session.commit()
    return created
