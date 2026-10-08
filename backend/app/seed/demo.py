"""Demo user: 24 months of synthetic history ending today, plus profile, holdings and goals.

Data is generated relative to the current date so "last 30 days" filters always have data;
`flask seed --reset` regenerates it.
"""

from dataclasses import dataclass
from datetime import date

from flask import current_app

from app.extensions import db
from app.models import (
    ExpenseCategory,
    FinancialGoal,
    FinancialProfile,
    Investment,
    Loan,
    Transaction,
    User,
)
from app.models.enums import AssetType, CategorySource, EmploymentType, LoanType, RiskTolerance
from app.seed.synthetic import Persona, generate_transactions, month_starts
from app.services.financial.formulas import emi, future_value, outstanding_after

HISTORY_MONTHS = 24
PRE_WINDOW_MONTHS = 6  # loan and SIP began this many months before the generated history

LOAN_PRINCIPAL, LOAN_RATE, LOAN_TENURE = 600_000, 0.10, 72
SIP_AMOUNT, SIP_RETURN = 10_000, 0.11


def _add_months(d: date, months: int) -> date:
    total = d.year * 12 + d.month - 1 + months
    return date(total // 12, total % 12 + 1, 1)


def demo_persona() -> Persona:
    return Persona(
        emi=round(emi(LOAN_PRINCIPAL, LOAN_RATE, LOAN_TENURE), 2),
        sips=(("SIP - AXIS BLUECHIP FUND", SIP_AMOUNT, 10),),
        anomalies={9: "travel_month", 7: "hospital", 4: "large_electronics", 2: "duplicate"},
    )


@dataclass
class SeedResult:
    created: bool
    email: str
    transactions: int = 0


def seed_demo(today: date | None = None, reset: bool = False) -> SeedResult:
    today = today or date.today()
    email = current_app.config["DEMO_EMAIL"]
    existing = db.session.scalar(db.select(User).where(User.email == email))
    if existing and not reset:
        return SeedResult(created=False, email=email)
    if existing:
        db.session.delete(existing)  # ON DELETE CASCADE removes all of the user's data
        db.session.flush()

    window_start = month_starts(today, HISTORY_MONTHS)[0]
    loan_start = _add_months(window_start, -PRE_WINDOW_MONTHS)
    rows = generate_transactions(demo_persona(), today, HISTORY_MONTHS, seed=2026)

    user = User(email=email, full_name="Aarav Sharma")
    user.set_password(current_app.config["DEMO_PASSWORD"])
    db.session.add(user)
    db.session.flush()

    db.session.add(
        FinancialProfile(
            user_id=user.id,
            declared_monthly_income=95_000,
            opening_balance=25_000,
            opening_balance_date=window_start,
            emergency_fund=95_000,
            monthly_essential_expenses=52_000,
            monthly_discretionary_expenses=18_000,
            risk_tolerance=RiskTolerance.MEDIUM,
            dependents=1,
            employment_type=EmploymentType.SALARIED,
        )
    )

    category_ids = {c.name: c.id for c in db.session.scalars(db.select(ExpenseCategory))}
    db.session.add_all(
        Transaction(
            user_id=user.id,
            date=r["date"],
            amount=r["amount"],
            type=r["type"],
            category_id=category_ids[r["category"]],
            description=r["description"],
            merchant=r["merchant"],
            payment_method=r["payment_method"],
            is_recurring=r["is_recurring"],
            category_source=CategorySource.IMPORT,
        )
        for r in rows
    )

    emis_paid = PRE_WINDOW_MONTHS + sum(r["category"] == "EMI/Debt" for r in rows)
    sips_paid = PRE_WINDOW_MONTHS + sum(r["category"] == "Investment" for r in rows)
    db.session.add_all(
        [
            Loan(
                user_id=user.id,
                name="HDFC Education Loan",
                loan_type=LoanType.EDUCATION,
                principal=LOAN_PRINCIPAL,
                outstanding=round(
                    outstanding_after(LOAN_PRINCIPAL, LOAN_RATE, LOAN_TENURE, emis_paid), 2
                ),
                annual_interest_rate=LOAN_RATE,
                emi=round(emi(LOAN_PRINCIPAL, LOAN_RATE, LOAN_TENURE), 2),
                tenure_months=LOAN_TENURE,
                start_date=loan_start,
            ),
            Investment(
                user_id=user.id,
                name="Axis Bluechip Fund (SIP)",
                asset_type=AssetType.SIP_EQUITY,
                invested_amount=SIP_AMOUNT * sips_paid,
                current_value=round(future_value(0, SIP_AMOUNT, SIP_RETURN, sips_paid), 2),
                monthly_contribution=SIP_AMOUNT,
                expected_annual_return=SIP_RETURN,
            ),
            Investment(
                user_id=user.id,
                name="Public Provident Fund",
                asset_type=AssetType.PPF,
                invested_amount=150_000,
                current_value=168_400,
                expected_annual_return=0.071,
            ),
            Investment(
                user_id=user.id,
                name="Sovereign Gold Bond",
                asset_type=AssetType.GOLD,
                invested_amount=40_000,
                current_value=48_200,
                expected_annual_return=0.08,
            ),
            FinancialGoal(
                user_id=user.id,
                name="Buy a car",
                target_amount=800_000,
                current_amount=200_000,
                target_date=_add_months(today, 24),
                priority=1,
                monthly_contribution=15_000,
            ),
            FinancialGoal(
                user_id=user.id,
                name="Europe trip",
                target_amount=300_000,
                current_amount=40_000,
                target_date=_add_months(today, 18),
                priority=2,
                monthly_contribution=6_000,
            ),
            FinancialGoal(
                user_id=user.id,
                name="Higher studies fund",
                target_amount=500_000,
                current_amount=120_000,
                target_date=_add_months(today, 36),
                priority=3,
                monthly_contribution=8_000,
            ),
        ]
    )
    db.session.commit()
    return SeedResult(created=True, email=email, transactions=len(rows))
