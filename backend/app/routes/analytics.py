from datetime import date, timedelta

from flask import Blueprint, request

from app.repositories.user_data import load_transactions, load_user_data
from app.services.analytics import aggregations as agg
from app.services.digital_twin.builder import cash_balance
from app.utils.auth import current_user_id, protect
from app.utils.http import ApiError, ok

bp = protect(Blueprint("analytics", __name__, url_prefix="/analytics"))


def _date_arg(name: str) -> date | None:
    raw = request.args.get(name)
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        raise ApiError(400, "VALIDATION_ERROR", f"'{name}' must be YYYY-MM-DD.") from None


def _range() -> tuple[date, date]:
    try:
        return agg.resolve_range(
            request.args.get("range"), _date_arg("from"), _date_arg("to"), date.today()
        )
    except ValueError as e:
        raise ApiError(400, "VALIDATION_ERROR", str(e)) from None


def _meta(start: date, end: date, **extra) -> dict:
    return {"from": start.isoformat(), "to": end.isoformat(), **extra}


@bp.get("/overview")
def overview():
    start, end = _range()
    return ok(agg.overview(load_transactions(current_user_id()), start, end), _meta(start, end))


@bp.get("/categories")
def categories():
    start, end = _range()
    rows = agg.categories(load_transactions(current_user_id()), start, end)
    return ok(rows, _meta(start, end))


@bp.get("/trends")
def trends():
    start, end = _range()
    granularity = request.args.get("granularity") or agg.granularity_for(start, end)
    if granularity not in ("day", "month"):
        raise ApiError(400, "VALIDATION_ERROR", "'granularity' must be day or month.")
    data = load_user_data(current_user_id())
    start = agg.bucket_start(start, granularity)
    opening = cash_balance(data, start - timedelta(days=1))
    rows = agg.trends(data.transactions, start, end, granularity, opening)
    return ok(rows, _meta(start, end, granularity=granularity))


@bp.get("/merchants")
def merchants():
    start, end = _range()
    raw = request.args.get("limit", "10")
    if not raw.isdigit() or not 1 <= int(raw) <= 50:
        raise ApiError(400, "VALIDATION_ERROR", "'limit' must be 1-50.")
    rows = agg.top_merchants(load_transactions(current_user_id()), start, end, int(raw))
    return ok(rows, _meta(start, end))
