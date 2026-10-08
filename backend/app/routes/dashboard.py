from datetime import date, timedelta

from flask import Blueprint

from app.repositories.user_data import load_user_data
from app.services.analytics import aggregations as agg
from app.services.analytics.risk_service import active_alerts
from app.services.digital_twin.builder import build_twin, cash_balance
from app.services.digital_twin.service import anomaly_flags, scored
from app.services.financial.goal_planner import plan_goals
from app.services.forecasting.service import forecast_expenses
from app.utils.auth import current_user_id, protect
from app.utils.http import ok

bp = protect(Blueprint("dashboard", __name__))


@bp.get("/dashboard")
def dashboard():
    """Everything the dashboard shows, computed from one load of the user's data."""
    user_id = current_user_id()
    data = load_user_data(user_id)
    twin = build_twin(data)
    health = scored(twin, anomaly_flags(data))
    start, end = agg.resolve_range("12m", None, None, date.today())
    start = agg.bucket_start(start, "month")
    trends = agg.trends(
        data.transactions, start, end, "month", cash_balance(data, start - timedelta(days=1))
    )
    return ok(
        {
            "twin": twin.to_dict(),
            "health": health.to_dict(),
            "trends": trends,
            "alerts": active_alerts(user_id),
            "goals": plan_goals(twin),
            "forecast": forecast_expenses(data, 3),
        }
    )
