from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, StatementError

from app.extensions import db
from app.models import (
    ExpenseCategory,
    FinancialGoal,
    FinancialProfile,
    FinancialSnapshot,
    Loan,
    RiskAlert,
    Transaction,
    User,
)
from app.models.enums import SnapshotPeriod
from app.seed.categories import CATEGORIES, ensure_categories


@pytest.fixture
def user(app):
    ensure_categories()
    u = User(email="a@example.com", full_name="A")
    u.set_password("secret-pass")
    db.session.add(u)
    db.session.commit()
    return u


def _category(name: str) -> int:
    return db.session.scalar(db.select(ExpenseCategory.id).where(ExpenseCategory.name == name))


def _txn(user, **overrides) -> Transaction:
    fields = dict(
        user_id=user.id,
        date=date(2026, 1, 5),
        amount=500,
        type="expense",
        category_id=_category("Groceries"),
        description="DMART",
    )
    return Transaction(**(fields | overrides))


def _assert_rejected(obj) -> None:
    db.session.add(obj)
    with pytest.raises((IntegrityError, StatementError)):
        db.session.commit()
    db.session.rollback()


def test_password_is_hashed_and_verifiable(user):
    assert user.password_hash != "secret-pass"
    assert user.check_password("secret-pass")
    assert not user.check_password("wrong")


def test_duplicate_email_rejected(user):
    _assert_rejected(User(email="a@example.com", full_name="B", password_hash="x"))


def test_valid_transaction_saved_with_category(user):
    db.session.add(_txn(user))
    db.session.commit()
    saved = db.session.scalar(db.select(Transaction))
    assert saved.category.name == "Groceries"
    assert float(saved.amount) == 500


@pytest.mark.parametrize("amount", [0, -100])
def test_non_positive_amount_rejected(user, amount):
    _assert_rejected(_txn(user, amount=amount))


def test_invalid_transaction_type_rejected(user):
    _assert_rejected(_txn(user, type="refund"))


def test_invalid_enum_rejected_at_database_level(user):
    # Bypass the ORM: the CHECK constraint itself must block bad values.
    with pytest.raises(IntegrityError):
        db.session.execute(
            text(
                "INSERT INTO transactions (user_id, date, amount, type, category_id, description,"
                " payment_method, is_recurring, category_source)"
                " VALUES (:u, '2026-01-01', 10, 'refund', :c, 'x', 'upi', 0, 'manual')"
            ),
            {"u": user.id, "c": _category("Groceries")},
        )
    db.session.rollback()


def test_unknown_category_rejected(user):
    _assert_rejected(_txn(user, category_id=9999))


def test_category_in_use_cannot_be_deleted(user):
    db.session.add(_txn(user))
    db.session.commit()
    with pytest.raises(IntegrityError):
        db.session.execute(text("DELETE FROM expense_categories WHERE name = 'Groceries'"))
        db.session.commit()
    db.session.rollback()


def test_goal_priority_must_be_1_to_5(user):
    _assert_rejected(FinancialGoal(user_id=user.id, name="X", target_amount=1000, priority=6))


def test_loan_outstanding_cannot_exceed_principal(user):
    _assert_rejected(
        Loan(
            user_id=user.id,
            name="L",
            loan_type="personal",
            principal=100_000,
            outstanding=150_000,
            annual_interest_rate=0.12,
            emi=5_000,
            tenure_months=24,
            start_date=date(2026, 1, 1),
        )
    )


def test_one_profile_per_user(user):
    db.session.add(FinancialProfile(user_id=user.id))
    db.session.commit()
    _assert_rejected(FinancialProfile(user_id=user.id))


def test_snapshot_unique_per_period(user):
    def snap():
        return FinancialSnapshot(
            user_id=user.id, as_of=date(2026, 1, 31), period=SnapshotPeriod.MONTHLY,
            income=1, expenses=1, net_cash_flow=0, savings_ratio=0, expense_ratio=1,
            debt_to_income=0, emergency_months=0, cash_balance=0, investments_value=0,
            total_debt=0, net_worth=0, months_of_history=1,
        )  # fmt: skip

    db.session.add(snap())
    db.session.commit()
    _assert_rejected(snap())


def test_risk_alert_fingerprint_unique_per_user(user):
    def alert():
        return RiskAlert(
            user_id=user.id, type="large_expense", severity="HIGH", title="t", explanation="e",
            affected_metric="m", recommended_action="r", fingerprint="abc",
            detected_at=date(2026, 1, 1),
        )  # fmt: skip

    db.session.add(alert())
    db.session.commit()
    _assert_rejected(alert())


def test_deleting_user_cascades_to_owned_rows(user):
    db.session.add_all([_txn(user), FinancialProfile(user_id=user.id)])
    db.session.commit()
    db.session.delete(user)
    db.session.commit()
    assert db.session.scalar(db.select(db.func.count(Transaction.id))) == 0
    assert db.session.scalar(db.select(db.func.count(FinancialProfile.id))) == 0
    # Reference data is untouched.
    assert db.session.scalar(db.select(db.func.count(ExpenseCategory.id))) == len(CATEGORIES)


def test_ensure_categories_is_idempotent(app):
    db.session.execute(text("DELETE FROM expense_categories"))
    assert ensure_categories() == len(CATEGORIES)
    assert ensure_categories() == 0
    assert db.session.scalar(db.select(db.func.count(ExpenseCategory.id))) == len(CATEGORIES)
