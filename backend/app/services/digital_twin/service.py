"""Digital Twin orchestration: compute the twin and keep persisted snapshots in sync."""

import logging
from datetime import date

from flask import Blueprint, request

from app.extensions import db
from app.models import FinancialSnapshot
from app.models.enums import SnapshotPeriod
from app.repositories.user_data import load_user_data
from app.services.digital_twin.builder import build_twin, monthly_snapshot_dates
from app.services.digital_twin.state import TwinState, UserData

logger = logging.getLogger(__name__)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def current_twin(user_id: int, as_of: date | None = None) -> TwinState:
    return build_twin(load_user_data(user_id), as_of)


def _snapshot_values(twin: TwinState) -> dict:
    return {
        "income": round(twin.monthly_income, 2),
        "expenses": round(twin.monthly_expenses, 2),
        "net_cash_flow": round(twin.net_cash_flow, 2),
        # Undefined ratios (zero income) are stored as 0; months_of_history disambiguates.
        "savings_ratio": twin.savings_ratio or 0.0,
        "expense_ratio": twin.expense_ratio or 0.0,
        "debt_to_income": twin.debt_to_income or 0.0,
        "emergency_months": twin.emergency_months or 0.0,
        "cash_balance": round(twin.cash_balance, 2),
        "investments_value": round(twin.investments_value, 2),
        "total_debt": round(twin.total_debt, 2),
        "net_worth": round(twin.net_worth, 2),
        "months_of_history": twin.months_of_history,
    }


def refresh_snapshots(user_id: int, data: UserData | None = None) -> int:
    """Recompute every monthly snapshot plus today's on-change snapshot.

    Monthly snapshots are rebuilt (not appended) because an import or edit can change any
    past month. Snapshots for months that no longer have data are removed.
    """
    data = data or load_user_data(user_id)
    existing = {
        (s.as_of, s.period): s
        for s in db.session.scalars(
            db.select(FinancialSnapshot).where(FinancialSnapshot.user_id == user_id)
        )
    }
    wanted = [(d, SnapshotPeriod.MONTHLY) for d in monthly_snapshot_dates(data)]
    wanted.append((data.today, SnapshotPeriod.ON_CHANGE))

    for as_of, period in wanted:
        values = _snapshot_values(build_twin(data, as_of))
        snapshot = existing.pop((as_of, period), None)
        if snapshot is None:
            db.session.add(FinancialSnapshot(user_id=user_id, as_of=as_of, period=period, **values))
        else:
            for name, value in values.items():
                setattr(snapshot, name, value)
    for (_, period), stale in existing.items():
        if period == SnapshotPeriod.MONTHLY:
            db.session.delete(stale)
    db.session.commit()
    return len(wanted)


def monthly_history(user_id: int) -> list[FinancialSnapshot]:
    query = (
        db.select(FinancialSnapshot)
        .where(
            FinancialSnapshot.user_id == user_id,
            FinancialSnapshot.period == SnapshotPeriod.MONTHLY,
        )
        .order_by(FinancialSnapshot.as_of)
    )
    snapshots = list(db.session.scalars(query))
    if not snapshots and refresh_snapshots(user_id) > 1:  # lazily backfill for older accounts
        snapshots = list(db.session.scalars(query))
    return snapshots


def recalculate_after_writes(bp: Blueprint, skip: tuple[str, ...] = ()) -> Blueprint:
    """Keep the twin's snapshots current after any successful data change in this blueprint
    (endpoints in `skip`, e.g. read-only POSTs, are ignored).

    Failures are logged, not raised: the user's write has already been committed.
    """
    from app.utils.auth import current_user_id

    @bp.after_request
    def _recalculate(response):
        endpoint = (request.endpoint or "").rsplit(".", 1)[-1]
        if request.method in WRITE_METHODS and response.status_code < 400 and endpoint not in skip:
            try:
                refresh_snapshots(current_user_id())
            except Exception:
                db.session.rollback()
                logger.exception("Digital Twin recalculation failed")
        return response

    return bp
