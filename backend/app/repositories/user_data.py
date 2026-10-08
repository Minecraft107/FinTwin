"""Loads everything the Digital Twin is derived from into plain dataclasses / a DataFrame."""

from datetime import date

import pandas as pd

from app.extensions import db
from app.models import (
    ExpenseCategory,
    FinancialGoal,
    FinancialProfile,
    Investment,
    Loan,
    Transaction,
)
from app.services.digital_twin.state import (
    TRANSACTION_COLUMNS,
    GoalData,
    InvestmentData,
    LoanData,
    ProfileData,
    UserData,
    empty_transactions,
)


def load_transactions(user_id: int) -> pd.DataFrame:
    rows = db.session.execute(
        db.select(
            Transaction.id,
            Transaction.date,
            Transaction.amount,
            Transaction.type,
            ExpenseCategory.name,
            ExpenseCategory.kind,
            Transaction.merchant,
            Transaction.description,
        )
        .join(ExpenseCategory)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.date, Transaction.id)
    ).all()
    if not rows:
        return empty_transactions()
    df = pd.DataFrame(rows, columns=TRANSACTION_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)
    df["type"] = df["type"].map(str)
    df["kind"] = df["kind"].map(str)
    return df


def load_user_data(user_id: int, today: date | None = None) -> UserData:
    p = db.session.scalar(db.select(FinancialProfile).where(FinancialProfile.user_id == user_id))
    profile = (
        ProfileData(
            declared_monthly_income=float(p.declared_monthly_income),
            opening_balance=float(p.opening_balance),
            opening_balance_date=p.opening_balance_date,
            emergency_fund=float(p.emergency_fund),
            monthly_essential_expenses=float(p.monthly_essential_expenses),
            monthly_discretionary_expenses=float(p.monthly_discretionary_expenses),
        )
        if p
        else ProfileData()
    )

    def owned(model):
        return db.session.scalars(
            db.select(model).where(model.user_id == user_id).order_by(model.id)
        )

    return UserData(
        transactions=load_transactions(user_id),
        profile=profile,
        investments=[
            InvestmentData(
                asset_type=str(i.asset_type),
                current_value=float(i.current_value),
                monthly_contribution=float(i.monthly_contribution),
                expected_annual_return=i.expected_annual_return,
            )
            for i in owned(Investment)
        ],
        loans=[
            LoanData(
                principal=float(loan.principal),
                outstanding=float(loan.outstanding),
                annual_interest_rate=loan.annual_interest_rate,
                emi=float(loan.emi),
                tenure_months=loan.tenure_months,
                start_date=loan.start_date,
            )
            for loan in owned(Loan)
        ],
        goals=[
            GoalData(
                id=g.id,
                name=g.name,
                target_amount=float(g.target_amount),
                current_amount=float(g.current_amount),
                target_date=g.target_date,
                priority=g.priority,
                monthly_contribution=float(g.monthly_contribution),
                status=str(g.status),
            )
            for g in owned(FinancialGoal)
        ],
        today=today or date.today(),
    )
