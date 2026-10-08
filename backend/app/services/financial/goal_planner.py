"""Goal planner: what each goal needs, what is affordable, and when it will be reached.

For each goal, using the user's Digital Twin:
- required_monthly   saving needed to hit the target on the target date (annuity formula;
                     `annual_return` defaults to 0, i.e. a savings account)
- planned_monthly    what the user intends to save (goal.monthly_contribution)
- fundable_monthly   what the monthly surplus can actually cover once higher-priority goals
                     have taken their share (same allocation as the Health Score)
- completion dates at the planned and at the fundable pace, the shortfall, a status,
  a sensitivity table (±₹2k / ±₹5k a month) and concrete options to close any gap.

Pure functions: no DB, no Flask.
"""

from dataclasses import replace
from datetime import date

from app.services.digital_twin.state import GoalProgress, TwinState
from app.services.financial.formulas import future_value, months_to_target, required_payment
from app.services.financial.goals import GoalFunding, allocate_surplus
from app.utils.dates import add_months, months_between
from app.utils.money import inr

SENSITIVITY_STEPS = (-5_000, -2_000, 0, 2_000, 5_000)
TOLERANCE = 1.0  # rupees: rounding slack when comparing monthly amounts
DISCLAIMER = (
    "Goal plans are estimates based on your current surplus and the stated return assumption; "
    "actual returns and spending will vary."
)


def _month(as_of: date, months: int | None) -> str | None:
    return None if months is None else add_months(as_of.replace(day=1), months).strftime("%Y-%m")


def plan_goal(
    goal: GoalProgress, funding: GoalFunding | None, as_of: date, annual_return: float = 0.0
) -> dict:
    target, current = goal.target_amount, goal.current_amount
    remaining = max(target - current, 0.0)
    planned = goal.monthly_contribution
    fundable = funding.fundable_monthly if funding else 0.0
    capacity = funding.capacity if funding else 0.0
    left = months_between(as_of, goal.target_date) if goal.target_date else None
    due = max(left, 1) if left is not None else None
    required = required_payment(target, current, annual_return, due) if due else None

    if goal.status == "achieved" or remaining <= 0:
        status = "achieved"
    elif goal.status == "paused":
        status = "paused"
    elif goal.target_date is None:
        status = "no_target_date"
    elif left is not None and left < 0:
        status = "overdue"
    elif fundable >= required - TOLERANCE:
        status = "on_track"
    elif planned >= required - TOLERANCE:
        status = "at_risk"  # the plan is enough, but the surplus can't fund it
    else:
        status = "off_track"

    months_planned = months_to_target(target, current, planned, annual_return)
    months_fundable = months_to_target(target, current, fundable, annual_return)
    projected_at_target = future_value(current, fundable, annual_return, due) if due else None

    sensitivity = []
    for delta in SENSITIVITY_STEPS:
        monthly = max(planned + delta, 0.0)
        if delta and monthly == planned:
            continue
        months = months_to_target(target, current, monthly, annual_return)
        sensitivity.append(
            {
                "change": delta,
                "monthly": round(monthly, 2),
                "months_to_complete": months,
                "completion": _month(as_of, months),
                "meets_target_date": None if due is None or months is None else months <= due,
                "affordable": monthly <= capacity + TOLERANCE,
            }
        )

    plan = {
        "goal_id": goal.id,
        "name": goal.name,
        "priority": goal.priority,
        "status": status,
        "target_amount": round(target, 2),
        "current_amount": round(current, 2),
        "remaining": round(remaining, 2),
        "progress_pct": round(min(current / target, 1.0) * 100, 1),
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "months_left": left,
        "annual_return_assumed": annual_return,
        "required_monthly": None if required is None else round(required, 2),
        "planned_monthly": round(planned, 2),
        "fundable_monthly": round(fundable, 2),
        "surplus_capacity": round(capacity, 2),
        "shortfall_monthly": None if required is None else round(max(required - fundable, 0), 2),
        "projected_at_target_date": None
        if projected_at_target is None
        else round(projected_at_target, 2),
        "shortfall_at_target_date": None
        if projected_at_target is None
        else round(max(target - projected_at_target, 0.0), 2),
        "completion_at_planned": _month(as_of, months_planned),
        "completion_at_fundable": _month(as_of, months_fundable),
        "sensitivity": sensitivity,
        "options": _options(
            goal,
            status,
            required,
            planned,
            fundable,
            capacity,
            as_of,
            months_fundable,
            projected_at_target,
        ),  # fmt: skip
    }
    plan["explanation"] = _explain(plan)
    plan["disclaimer"] = DISCLAIMER
    return plan


def _options(
    goal, status, required, planned, fundable, capacity, as_of, months_fundable, projected
):
    if status not in ("at_risk", "off_track", "overdue") or required is None:
        return []
    options = []
    if required > planned + TOLERANCE:
        options.append(
            {"type": "increase_contribution", "monthly": round(required, 2),
             "text": f"Save {inr(required)}/month instead of {inr(planned)} "
                     f"(+{inr(required - planned)})."}
        )  # fmt: skip
    if required > capacity + TOLERANCE:
        gap = required - capacity
        options.append(
            {"type": "free_up_spending", "monthly": round(gap, 2),
             "text": f"Free up about {inr(gap)}/month of spending (or raise this goal's priority) "
                     "so your surplus can fund it."}
        )  # fmt: skip
    if months_fundable is not None and fundable > 0:
        new_date = _month(as_of, months_fundable)
        options.append(
            {"type": "extend_target_date", "target_date": new_date,
             "text": f"Move the target date to {new_date}, which your current surplus can fund."}
        )  # fmt: skip
    if projected is not None and fundable > 0 and projected < goal.target_amount:
        options.append(
            {"type": "reduce_target", "target_amount": round(projected, 2),
             "text": f"Lower the target to about {inr(projected)}, reachable by "
                     f"{goal.target_date.strftime('%Y-%m')} at your current surplus."}
        )  # fmt: skip
    return options


def _explain(p: dict) -> str:
    name = p["name"]
    if p["status"] == "achieved":
        return (
            f"'{name}' is complete: {inr(p['current_amount'])} saved of {inr(p['target_amount'])}."
        )
    if p["status"] == "paused":
        return f"'{name}' is paused, so no surplus is allocated to it."
    if p["status"] == "no_target_date":
        when = p["completion_at_fundable"]
        return (
            f"'{name}' has no target date. At the {inr(p['fundable_monthly'])}/month your surplus "
            f"can fund, it would be reached around {when}." if when
            else f"'{name}' has no target date and your surplus cannot fund it right now."
        )  # fmt: skip
    text = (
        f"To reach {inr(p['target_amount'])} by {p['target_date'][:7]} you need about "
        f"{inr(p['required_monthly'])}/month. You plan {inr(p['planned_monthly'])}/month, and "
        f"after higher-priority goals your surplus can fund {inr(p['fundable_monthly'])}/month."
    )
    if p["status"] == "on_track":
        return text + " You are on track."
    when = p["completion_at_fundable"]
    text += (
        f" At that pace you would reach it around {when}." if when
        else " At that pace the goal would not be reached."
    )  # fmt: skip
    if p["shortfall_at_target_date"]:
        text += f" You would be {inr(p['shortfall_at_target_date'])} short on the target date."
    return text


def plan_goals(
    twin: TwinState,
    annual_return: float = 0.0,
    extra_surplus: float = 0.0,
    overrides: dict[int, dict] | None = None,
) -> list[dict]:
    """Plans for every goal, in priority order. `overrides` (goal id -> field changes) and
    `extra_surplus` support what-if questions without touching stored data."""
    goals = [replace(g, **(overrides or {}).get(g.id, {})) for g in twin.goals]
    surplus = twin.net_cash_flow + extra_surplus
    funding = {f.goal_id: f for f in allocate_surplus(goals, surplus, twin.as_of)}
    return [
        plan_goal(g, funding.get(g.id), twin.as_of, annual_return)
        for g in sorted(goals, key=lambda g: (g.priority, g.id))
    ]
