from flask import Blueprint, request

from app.extensions import db
from app.models import FinancialHealthScore, FinancialSnapshot
from app.models.enums import SnapshotPeriod
from app.services.digital_twin.service import health_report, monthly_history
from app.services.financial.health_score import SPECS, methodology
from app.utils.auth import current_user_id, protect
from app.utils.http import ApiError, ok

bp = protect(Blueprint("health", __name__, url_prefix="/health-score"))


@bp.get("")
def get_score():
    raw = request.args.get("compare_months", "1")
    if not raw.isdigit() or not 1 <= int(raw) <= 12:
        raise ApiError(400, "VALIDATION_ERROR", "'compare_months' must be 1-12.")
    return ok(health_report(current_user_id(), int(raw)))


@bp.get("/history")
def history():
    user_id = current_user_id()
    monthly_history(user_id)  # backfills snapshots (and scores) when missing
    rows = db.session.execute(
        db.select(FinancialSnapshot.as_of, FinancialHealthScore)
        .join(FinancialHealthScore)
        .where(
            FinancialSnapshot.user_id == user_id,
            FinancialSnapshot.period == SnapshotPeriod.MONTHLY,
        )
        .order_by(FinancialSnapshot.as_of)
    )
    return ok(
        [
            {
                "as_of": as_of.isoformat(),
                "score": score.score,
                "grade": score.grade,
                "components": {key: getattr(score, key) for key in SPECS},
            }
            for as_of, score in rows
        ]
    )


@bp.get("/methodology")
def get_methodology():
    return ok(methodology())
