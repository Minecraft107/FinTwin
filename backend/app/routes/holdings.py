"""CRUD for the user's investments, loans and goals (same shape, one helper)."""

from collections.abc import Callable

from flask import Blueprint

from app.extensions import db
from app.models import FinancialGoal, Investment, Loan
from app.repositories.base import get_owned
from app.schemas.common import InModel, OutModel, dump, parse_body
from app.schemas.holdings import (
    GoalIn,
    GoalOut,
    GoalUpdate,
    InvestmentIn,
    InvestmentOut,
    InvestmentUpdate,
    LoanIn,
    LoanOut,
    LoanUpdate,
)
from app.services.financial.formulas import emi
from app.utils.auth import current_user_id, protect
from app.utils.http import ApiError, ok

bp = protect(Blueprint("holdings", __name__))


def register_crud(
    url: str,
    model: type[db.Model],
    create: type[InModel],
    update: type[InModel],
    out: type[OutModel],
    validate: Callable[[db.Model], None] = lambda obj: None,
) -> None:
    name = model.__tablename__

    @bp.get(f"/{url}", endpoint=f"list_{name}")
    def list_items():
        items = db.session.scalars(
            db.select(model).where(model.user_id == current_user_id()).order_by(model.id)
        )
        return ok([dump(out, i) for i in items])

    @bp.post(f"/{url}", endpoint=f"create_{name}")
    def create_item():
        obj = model(user_id=current_user_id(), **parse_body(create).model_dump())
        validate(obj)
        db.session.add(obj)
        db.session.commit()
        return ok(dump(out, obj), status=201)

    @bp.put(f"/{url}/<int:obj_id>", endpoint=f"update_{name}")
    def update_item(obj_id: int):
        body = parse_body(update)
        obj = get_owned(model, obj_id, current_user_id())
        for field, value in body.model_dump(exclude_unset=True).items():
            if value is not None or field == "target_date":  # target_date may be cleared
                setattr(obj, field, value)
        validate(obj)
        db.session.commit()
        return ok(dump(out, obj))

    @bp.delete(f"/{url}/<int:obj_id>", endpoint=f"delete_{name}")
    def delete_item(obj_id: int):
        db.session.delete(get_owned(model, obj_id, current_user_id()))
        db.session.commit()
        return "", 204


def _complete_loan(loan: Loan) -> None:
    """Fill defaults from loan terms and enforce invariants on the merged state."""
    if loan.outstanding is None:
        loan.outstanding = loan.principal
    if loan.emi is None:
        loan.emi = round(
            emi(float(loan.principal), loan.annual_interest_rate, loan.tenure_months), 2
        )
    if float(loan.outstanding) > float(loan.principal):
        raise ApiError(400, "VALIDATION_ERROR", "outstanding cannot exceed principal.")


register_crud("investments", Investment, InvestmentIn, InvestmentUpdate, InvestmentOut)
register_crud("loans", Loan, LoanIn, LoanUpdate, LoanOut, validate=_complete_loan)
register_crud("goals", FinancialGoal, GoalIn, GoalUpdate, GoalOut)
