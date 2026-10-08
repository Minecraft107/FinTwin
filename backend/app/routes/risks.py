from flask import Blueprint, request
from pydantic import BaseModel, ConfigDict

from app.extensions import db
from app.models import RiskAlert
from app.models.enums import AlertStatus
from app.repositories.base import get_owned
from app.services.analytics.anomalies import SEVERITY_RANK
from app.services.digital_twin.service import recalculate
from app.utils.auth import current_user_id, protect
from app.utils.http import ApiError, ok

bp = protect(Blueprint("risks", __name__, url_prefix="/risks"))


class AlertUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: AlertStatus


def _alert(a: RiskAlert) -> dict:
    return {
        "id": a.id,
        "type": a.type,
        "severity": a.severity.value,
        "title": a.title,
        "explanation": a.explanation,
        "affected_metric": a.affected_metric,
        "metric_value": a.metric_value,
        "recommended_action": a.recommended_action,
        "transaction_id": a.transaction_id,
        "status": a.status.value,
        "detected_at": a.detected_at.isoformat(),
    }


@bp.get("")
def list_risks():
    status = request.args.get("status", "active")
    if status not in ("active", "dismissed", "all"):
        raise ApiError(400, "VALIDATION_ERROR", "'status' must be active, dismissed or all.")
    query = db.select(RiskAlert).where(RiskAlert.user_id == current_user_id())
    if status != "all":
        query = query.where(RiskAlert.status == status)
    alerts = sorted(
        db.session.scalars(query),
        key=lambda a: (-SEVERITY_RANK[a.severity], a.id),
    )
    counts = {s: sum(a.severity == s for a in alerts) for s in SEVERITY_RANK}
    return ok([_alert(a) for a in alerts], meta={"counts": {str(k): v for k, v in counts.items()}})


@bp.post("/scan")
def scan():
    recalculate(current_user_id())
    return list_risks()


@bp.patch("/<int:alert_id>")
def update(alert_id: int):
    body = AlertUpdate.model_validate(request.get_json(silent=True) or {})
    alert = get_owned(RiskAlert, alert_id, current_user_id())
    alert.status = body.status
    db.session.commit()
    return ok(_alert(alert))
