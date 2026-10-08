from datetime import UTC, datetime

from flask import Blueprint, request

from app.extensions import db
from app.models import ForecastResult
from app.models.enums import ForecastTarget
from app.repositories.user_data import load_user_data
from app.services.forecasting.service import forecast_cash_flow, forecast_expenses
from app.services.ml.artifacts import status as ml_status
from app.utils.auth import current_user_id, protect
from app.utils.http import ApiError, ok

bp = protect(Blueprint("forecast", __name__))


def _horizon(default: int, maximum: int) -> int:
    raw = request.args.get("horizon", str(default))
    if not raw.isdigit() or not 1 <= int(raw) <= maximum:
        raise ApiError(400, "VALIDATION_ERROR", f"'horizon' must be 1-{maximum} months.")
    return int(raw)


def _save(user_id: int, target: ForecastTarget, result: dict, value_key: str) -> None:
    """Keep the latest forecast per target (an audit trail of what the user was shown)."""
    if result["status"] != "ok":
        return
    db.session.execute(
        db.delete(ForecastResult).where(
            ForecastResult.user_id == user_id, ForecastResult.target == target
        )
    )
    db.session.add(
        ForecastResult(
            user_id=user_id,
            target=target,
            model_name=result["model"]["selected"],
            horizon_months=result["horizon"],
            generated_at=datetime.now(UTC),
            backtest_mae=next(
                (
                    b["mae"]
                    for b in result["model"]["backtest"]
                    if b["model"] == result["model"]["selected"]
                ),  # fmt: skip
                None,
            ),
            points=[{"month": p["month"], "value": p[value_key]} for p in result["forecast"]],
        )
    )
    db.session.commit()


@bp.get("/forecast/expenses")
def expenses():
    user_id = current_user_id()
    result = forecast_expenses(load_user_data(user_id), _horizon(3, 6))
    _save(user_id, ForecastTarget.EXPENSES, result, "value")
    return ok(result)


@bp.get("/forecast/cash-flow")
def cash_flow():
    user_id = current_user_id()
    result = forecast_cash_flow(load_user_data(user_id), _horizon(6, 12))
    _save(user_id, ForecastTarget.CASH_FLOW, result, "net_cash_flow")
    return ok(result)


@bp.get("/ml/status")
def get_ml_status():
    return ok(ml_status())
