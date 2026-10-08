"""Goal funding arithmetic shared by the health score (and extended by the goal planner).

Goal contributions are funded from the monthly surplus (net cash flow), in priority order;
they are not an extra outflow on top of it (see implementation-plan risk #14).
"""

from dataclasses import dataclass
from datetime import date

from app.utils.dates import months_between


@dataclass(frozen=True)
class GoalFunding:
    goal_id: int
    name: str
    priority: int
    required_monthly: float | None  # None when the goal has no target date
    planned_monthly: float
    fundable_monthly: float  # what the surplus can actually cover after higher priorities
    capacity: float  # surplus still available when this goal's turn comes
    months_left: int | None


def months_left(target_date: date | None, as_of: date) -> int | None:
    if target_date is None:
        return None
    return max(months_between(as_of, target_date), 1)


def required_monthly(remaining: float, months: int | None) -> float | None:
    """Straight-line saving needed (no assumed returns; the goal planner adds returns)."""
    if months is None:
        return None
    return max(remaining, 0.0) / months


def allocate_surplus(goals, surplus: float, as_of: date) -> list[GoalFunding]:
    """Fund active, unfinished goals from `surplus` in priority order (1 = first)."""
    available = max(surplus, 0.0)
    result = []
    for g in sorted(goals, key=lambda g: (g.priority, g.id)):
        remaining = g.target_amount - g.current_amount
        if g.status != "active" or remaining <= 0:
            continue
        left = months_left(g.target_date, as_of)
        planned = g.monthly_contribution
        capacity = available
        fundable = min(planned, available)
        available -= fundable
        result.append(
            GoalFunding(
                goal_id=g.id,
                name=g.name,
                priority=g.priority,
                required_monthly=required_monthly(remaining, left),
                planned_monthly=planned,
                fundable_monthly=fundable,
                capacity=capacity,
                months_left=left,
            )
        )
    return result
