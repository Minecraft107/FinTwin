from datetime import date

import pytest

from app.extensions import db
from app.models import FinancialGoal, FinancialProfile, Investment, Loan, Transaction, User
from app.seed.categories import ensure_categories
from app.seed.demo import seed_demo
from app.services.financial.formulas import emi


def _count(model) -> int:
    return db.session.scalar(db.select(db.func.count(model.id)))


def test_seed_cli_creates_demo_user_and_is_idempotent(app):
    runner = app.test_cli_runner()
    first = runner.invoke(args=["seed"])
    assert first.exit_code == 0, first.output
    assert "transactions generated" in first.output
    txn_count = _count(Transaction)
    assert txn_count > 1000

    second = runner.invoke(args=["seed"])
    assert "already exists" in second.output
    assert _count(Transaction) == txn_count
    assert _count(User) == 1


def test_seed_reset_regenerates_without_duplicates(app):
    ensure_categories()
    seed_demo(today=date(2026, 10, 8))
    result = seed_demo(today=date(2026, 10, 8), reset=True)
    assert result.created
    assert _count(User) == 1
    assert _count(Transaction) == result.transactions
    assert _count(FinancialProfile) == 1


def test_demo_holdings_are_internally_consistent(app):
    ensure_categories()
    seed_demo(today=date(2026, 10, 8))
    user = db.session.scalar(db.select(User))
    assert user.check_password(app.config["DEMO_PASSWORD"])

    loan = db.session.scalar(db.select(Loan))
    assert float(loan.emi) == pytest.approx(emi(600_000, 0.10, 72), abs=0.01)
    assert 0 < float(loan.outstanding) < float(loan.principal)
    emi_txns = db.session.scalars(
        db.select(Transaction).where(Transaction.description == "EMI - HDFC EDUCATION LOAN")
    ).all()
    assert {float(t.amount) for t in emi_txns} == {float(loan.emi)}

    assert _count(Investment) == 3
    assert _count(FinancialGoal) == 3
    goals = db.session.scalars(db.select(FinancialGoal)).all()
    assert all(g.target_date > date(2026, 10, 8) for g in goals)
