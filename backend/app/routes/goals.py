"""Goal planner endpoints (goal CRUD lives in holdings.py)."""

import datetime as dt

from flask import Blueprint, request
from pydantic import Field

from app.repositories.user_data import load_user_data
from app.schemas.common import InModel, parse_body
from app.services.digital_twin.builder import build_twin
from app.services.financial.goal_planner import plan_goals
from app.utils.auth import current_user_id, protect
from app.utils.http import ApiError, ok

bp = protect(Blueprint("goal_planner", __name__, url_prefix="/goals"))

MAX_RETURN = 0.15


class GoalSimulation(InModel):
    """What-if changes to one goal; nothing is saved."""

    monthly_contribution: float | None = Field(default=None, ge=0, le=1e10)
    target_amount: float | None = Field(default=None, gt=0, le=1e11)
    target_date: dt.date | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    annual_return: float = Field(default=0.0, ge=0, le=MAX_RETURN)
    extra_monthly_surplus: float = Field(default=0.0, ge=0, le=1e10)  # e.g. spending cut


def _annual_return() -> float:
    raw = request.args.get("annual_return", "0")
    try:
        value = float(raw)
    except ValueError:
        value = -1
    if not 0 <= value <= MAX_RETURN:
        raise ApiError(400, "VALIDATION_ERROR", f"'annual_return' must be 0-{MAX_RETURN}.")
    return value


def _plans(**kwargs) -> tuple[list[dict], dict]:
    twin = build_twin(load_user_data(current_user_id()))
    meta = {"as_of": twin.as_of.isoformat(), "monthly_surplus": round(twin.net_cash_flow, 2)}
    return plan_goals(twin, **kwargs), meta


def _one(plans: list[dict], goal_id: int) -> dict:
    plan = next((p for p in plans if p["goal_id"] == goal_id), None)
    if plan is None:
        raise ApiError(404, "NOT_FOUND", f"FinancialGoal {goal_id} not found.")
    return plan


@bp.get("/plan")
def all_plans():
    plans, meta = _plans(annual_return=_annual_return())
    return ok(plans, meta)


@bp.get("/<int:goal_id>/plan")
def goal_plan(goal_id: int):
    plans, meta = _plans(annual_return=_annual_return())
    return ok(_one(plans, goal_id), meta)


@bp.post("/<int:goal_id>/simulate")
def simulate_goal(goal_id: int):
    body = parse_body(GoalSimulation)
    overrides = body.model_dump(
        exclude_none=True, exclude={"annual_return", "extra_monthly_surplus"}
    )  # field names match the goal's
    before, meta = _plans(annual_return=body.annual_return)
    current = _one(before, goal_id)
    after, _ = _plans(
        annual_return=body.annual_return,
        extra_surplus=body.extra_monthly_surplus,
        overrides={goal_id: overrides},
    )
    simulated = _one(after, goal_id)
    others = {p["goal_id"]: p for p in before if p["goal_id"] != goal_id}
    affected = [
        {
            "goal_id": p["goal_id"],
            "name": p["name"],
            "fundable_before": others[p["goal_id"]]["fundable_monthly"],
            "fundable_after": p["fundable_monthly"],
        }  # fmt: skip
        for p in after
        if p["goal_id"] in others
        and p["fundable_monthly"] != others[p["goal_id"]]["fundable_monthly"]
    ]
    return ok(
        {
            "changes": body.model_dump(exclude_none=True),
            "current": current,
            "simulated": simulated,
            "other_goals_affected": affected,
        },
        meta,
    )
