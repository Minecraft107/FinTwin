from datetime import date

from flask import Blueprint, request

from app.repositories.user_data import load_user_data
from app.services.digital_twin.builder import build_twin
from app.services.digital_twin.service import anomaly_flags, monthly_history, scored
from app.utils.auth import current_user_id, protect
from app.utils.http import ApiError, ok

bp = protect(Blueprint("twin", __name__, url_prefix="/digital-twin"))


@bp.get("")
def get_twin():
    raw = request.args.get("as_of")
    try:
        as_of = date.fromisoformat(raw) if raw else None
    except ValueError:
        raise ApiError(400, "VALIDATION_ERROR", "'as_of' must be YYYY-MM-DD.") from None
    if as_of and as_of > date.today():
        raise ApiError(400, "VALIDATION_ERROR", "'as_of' cannot be in the future.")
    data = load_user_data(current_user_id())
    twin = build_twin(data, as_of)
    health = scored(twin, anomaly_flags(data))
    payload = twin.to_dict()
    payload["health_score"] = {
        "score": None if health.score is None else round(health.score, 1),
        "grade": health.grade,
        "label": health.label,
        "components": {
            c.key: None if c.score is None else round(c.score, 1) for c in health.components
        },
    }
    return ok(payload)


@bp.get("/history")
def history():
    rows = monthly_history(current_user_id())
    return ok(
        [
            {
                "as_of": s.as_of.isoformat(),
                "income": float(s.income),
                "expenses": float(s.expenses),
                "net_cash_flow": float(s.net_cash_flow),
                "savings_ratio": s.savings_ratio,
                "expense_ratio": s.expense_ratio,
                "debt_to_income": s.debt_to_income,
                "emergency_months": s.emergency_months,
                "cash_balance": float(s.cash_balance),
                "investments_value": float(s.investments_value),
                "total_debt": float(s.total_debt),
                "net_worth": float(s.net_worth),
                "months_of_history": s.months_of_history,
            }
            for s in rows
        ]
    )
