from flask import Blueprint, request
from pydantic import Field

from app.extensions import db
from app.models import SimulationResult, SimulationScenario
from app.repositories.base import get_owned
from app.repositories.user_data import load_user_data
from app.services.simulation.scenarios import GoalDelay, Scenario
from app.services.simulation.service import run_scenario
from app.utils.auth import current_user_id, protect
from app.utils.http import ApiError, ok

bp = protect(Blueprint("simulation", __name__, url_prefix="/simulation"))

SCENARIO_KEYS = ("name", "horizon_months", "inflation_pct")


class SavedScenario(Scenario):
    name: str = Field(min_length=1, max_length=120)


def _scenario_from_body(model: type[Scenario] = Scenario) -> Scenario:
    """Accept a full scenario, or a single change object (e.g. {"type": "large_purchase", ...})."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_JSON", "Request body must be a JSON object.")
    if "changes" not in body and "type" in body:
        change = {k: v for k, v in body.items() if k not in SCENARIO_KEYS}
        body = {k: body[k] for k in SCENARIO_KEYS if k in body} | {"changes": [change]}
    return model.model_validate(body)


def _run(scenario: Scenario) -> dict:
    data = load_user_data(current_user_id())
    goal_ids = {g.id for g in data.goals}
    for change in scenario.changes:
        if isinstance(change, GoalDelay) and change.goal_id not in goal_ids:
            raise ApiError(400, "VALIDATION_ERROR", f"Goal {change.goal_id} does not exist.")
    return run_scenario(data, scenario)


def _store_result(scenario: SimulationScenario, result: dict) -> SimulationResult:
    details = {k: v for k, v in result.items() if k not in ("timeline", "scenario")}
    row = SimulationResult(
        scenario_id=scenario.id,
        risk_level=result["risk_level"],
        health_score_before=result["baseline_state"]["health_score"] or 0.0,
        health_score_after=result["simulated_state"]["health_score"] or 0.0,
        cash_change_12m=result["impact"]["cash_change"],
        impact=details,  # full result details except the month-by-month timeline
        timeline=result["timeline"],
    )
    db.session.add(row)
    db.session.commit()
    return row


def _scenario_dict(s: SimulationScenario, latest: SimulationResult | None) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "changes": s.changes,
        "horizon_months": s.horizon_months,
        "created_at": s.created_at.isoformat(),
        "latest_result": None
        if latest is None
        else {
            "id": latest.id,
            "run_at": latest.created_at.isoformat(),
            "risk_level": latest.risk_level.value,
            "health_score_before": latest.health_score_before,
            "health_score_after": latest.health_score_after,
            "cash_change_12m": float(latest.cash_change_12m),
        },
    }


@bp.post("/what-if")
def what_if():
    return ok(_run(_scenario_from_body()))


@bp.post("/scenarios")
def save_scenario():
    scenario = _scenario_from_body(SavedScenario)
    result = _run(scenario)
    row = SimulationScenario(
        user_id=current_user_id(),
        name=scenario.name,
        changes=[c.model_dump(mode="json") for c in scenario.changes],
        horizon_months=scenario.horizon_months,
    )
    db.session.add(row)
    db.session.flush()
    stored = _store_result(row, result)
    return ok({"scenario": _scenario_dict(row, stored), "result": result}, status=201)


@bp.get("/scenarios")
def list_scenarios():
    rows = db.session.scalars(
        db.select(SimulationScenario)
        .where(SimulationScenario.user_id == current_user_id())
        .order_by(SimulationScenario.id.desc())
    )
    return ok([_scenario_dict(s, s.results[-1] if s.results else None) for s in rows])


@bp.get("/scenarios/<int:scenario_id>")
def get_scenario(scenario_id: int):
    s = get_owned(SimulationScenario, scenario_id, current_user_id())
    latest = s.results[-1] if s.results else None
    return ok(
        _scenario_dict(s, latest)
        | {"result": None if latest is None else latest.impact | {"timeline": latest.timeline}}
    )


@bp.post("/scenarios/<int:scenario_id>/run")
def rerun_scenario(scenario_id: int):
    """Re-run a saved scenario against the user's current data."""
    s = get_owned(SimulationScenario, scenario_id, current_user_id())
    scenario = Scenario.model_validate(
        {"name": s.name, "changes": s.changes, "horizon_months": s.horizon_months}
    )
    result = _run(scenario)
    stored = _store_result(s, result)
    return ok({"scenario": _scenario_dict(s, stored), "result": result}, status=201)


@bp.delete("/scenarios/<int:scenario_id>")
def delete_scenario(scenario_id: int):
    db.session.delete(get_owned(SimulationScenario, scenario_id, current_user_id()))
    db.session.commit()
    return "", 204
