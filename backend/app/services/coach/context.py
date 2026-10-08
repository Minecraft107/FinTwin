"""Structured, pre-formatted context for the coach: only verified backend numbers.

Sections (included per intent): CURRENT_FINANCIAL_STATE, FINANCIAL_HEALTH_SCORE,
RECENT_TRANSACTIONS, FORECAST, RISKS, GOALS, SIMULATION_RESULTS. Every number is already
formatted (₹ with Indian grouping, %), so an LLM can quote figures but never needs to
compute one; the grounding check then verifies that it didn't.
"""

from dataclasses import dataclass, field
from datetime import timedelta

import pandas as pd

from app.services.analytics import aggregations as agg
from app.services.digital_twin.state import TwinState, UserData
from app.services.financial.health_score import HealthScoreResult
from app.utils.money import inr, pct

SECTIONS_BY_INTENT = {
    "affordability": ["SIMULATION_RESULTS", "FINANCIAL_HEALTH_SCORE", "GOALS"],
    "what_if": ["SIMULATION_RESULTS", "FINANCIAL_HEALTH_SCORE", "GOALS"],
    "score_explanation": ["FINANCIAL_HEALTH_SCORE", "RISKS"],
    "improve_health": ["FINANCIAL_HEALTH_SCORE", "RISKS", "GOALS"],
    "overspending": ["RECENT_TRANSACTIONS", "RISKS"],
    "goal_planning": ["GOALS"],
    "emergency_fund": ["FINANCIAL_HEALTH_SCORE"],
    "debt": ["FINANCIAL_HEALTH_SCORE"],
    "forecast": ["FORECAST"],
    "risk": ["RISKS"],
}


@dataclass
class CoachInputs:
    """Everything already computed by the backend for one question."""

    data: UserData
    twin: TwinState
    health: HealthScoreResult
    health_change: dict | None = None
    goal_plans: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)
    forecast: dict | None = None
    cash_flow: dict | None = None
    simulation: dict | None = None
    scenario_description: str | None = None
    scenario_assumptions: list[str] = field(default_factory=list)


def current_state(t: TwinState, data: UserData) -> dict:
    window = (
        f"average of {t.window_start:%b %Y}–{t.window_end:%b %Y} "
        f"({t.window_months} complete months)"
        if t.window_months
        else "declared profile values (not enough transaction history yet)"
    )
    return {
        "as_of": t.as_of.isoformat(),
        "based_on": window,
        "monthly_income": inr(t.monthly_income),
        "monthly_spending": inr(t.monthly_expenses),
        "essential_spending": inr(t.essential_expenses),
        "discretionary_spending": inr(t.discretionary_expenses),
        "loan_emis": inr(t.debt_payments),
        "investment_contributions": inr(t.investment_contributions),
        "monthly_surplus": inr(t.net_cash_flow),
        "cash_balance": inr(t.cash_balance),
        "emergency_fund": inr(t.emergency_fund),
        "investments_value": inr(t.investments_value),
        "loans_outstanding": inr(t.total_debt),
        "net_worth": inr(t.net_worth),
        "savings_ratio": pct(t.savings_ratio),
        "debt_to_income": pct(t.debt_to_income),
        "emergency_fund_months": "n/a"
        if t.emergency_months is None
        else f"{t.emergency_months:.1f} months",
        "top_discretionary_categories": [
            f"{c}: {inr(v)}/month" for c, v in list(t.discretionary_by_category.items())[:4]
        ],
        "loans": [
            f"Loan at {loan.annual_interest_rate * 100:g}%: EMI {inr(loan.emi)}, "
            f"outstanding {inr(loan.outstanding)}"
            for loan in data.loans
        ],
    }


def health_section(h: HealthScoreResult, change: dict | None) -> dict:
    if h.score is None:
        return {"score": "not available yet", "reason": "; ".join(h.notes)}
    return {
        "score": f"{h.score:.1f} / 100",
        "grade": f"{h.grade} ({h.label})",
        "components": [
            f"{c.label}: {c.score:.0f}/100 (weight {c.weight:g}%) — {c.explanation}"
            for c in h.components
            if c.score is not None
        ],
        "strengths": h.strengths,
        "weaknesses": h.weaknesses,
        "recommendations": [f"{r.title}: {r.action}" for r in h.recommendations[:4]],
        "change": change["summary"] if change else "no earlier month to compare",
    }


def recent_transactions(data: UserData) -> dict:
    end = data.today
    start = end - timedelta(days=89)
    categories = agg.categories(data.transactions, start, end)
    recent = data.transactions[data.transactions["date"].dt.date > end - timedelta(days=30)]
    large = recent[recent["type"] == "expense"].nlargest(5, "amount")
    return {
        "period": f"{start.isoformat()} to {end.isoformat()}, compared with the 90 days before",
        "spending_by_category": [
            f"{r['category']} ({r['kind']}): {inr(r['total'])}"
            + (
                f", {r['change_pct']:+.0f}% vs the previous 90 days"
                if r["change_pct"] is not None
                else ""
            )
            for r in categories[:8]
        ],
        "largest_expenses_last_30_days": [
            f"{pd.Timestamp(d).date().isoformat()} {desc}: {inr(a)}"
            for d, desc, a in zip(large["date"], large["description"], large["amount"], strict=True)
        ],
    }


def goals_section(plans: list[dict]) -> list[str]:
    return [p["explanation"] + f" [status: {p['status'].replace('_', ' ')}]" for p in plans]


def risks_section(alerts: list[dict]) -> list[str]:
    return [f"{a['severity']}: {a['title']} — {a['explanation']}" for a in alerts] or [
        "No active alerts."
    ]


def forecast_section(forecast: dict | None, cash_flow: dict | None) -> dict:
    if not forecast or forecast.get("status") != "ok":
        return {"status": "not enough history to forecast"}
    return {
        "expenses": forecast["explanation"],
        "expense_forecast": [
            f"{p['month']}: {inr(p['value'])} (likely {inr(p['lower'])}–{inr(p['upper'])})"
            for p in forecast["forecast"]
        ],
        "model": f"{forecast['model']['label']}, confidence {forecast['confidence']}",
        "cash_flow": cash_flow["explanation"]
        if cash_flow and cash_flow.get("status") == "ok"
        else "n/a",
    }


def simulation_section(sim: dict, description: str, assumptions: list[str]) -> dict:
    i = sim["impact"]
    return {
        "scenario": description,
        "risk_level": sim["risk_level"],
        "risk_factors": sim["risk_factors"],
        "explanation": sim["explanation"],
        "recommendation": sim["recommendation"],
        "impact": {
            "cash_change_after_12_months": inr(i["cash_change"]),
            "net_worth_change_after_12_months": inr(i["net_worth_change"]),
            "monthly_surplus_change": inr(i["monthly_cash_flow_change"]),
            "health_score_change": "n/a"
            if i["health_score_change"] is None
            else f"{i['health_score_change']:+.1f} points",
            "emergency_fund_used": inr(i["emergency_fund_drawn"]),
            "first_shortfall_month": i["first_shortfall_month"] or "none",
        },
        "assumptions": assumptions + sim["assumptions"],
    }


def build_context(intent: str, x: CoachInputs) -> dict:
    sections = {"CURRENT_FINANCIAL_STATE": current_state(x.twin, x.data)}
    for name in SECTIONS_BY_INTENT.get(intent, []):
        if name == "FINANCIAL_HEALTH_SCORE":
            sections[name] = health_section(x.health, x.health_change)
        elif name == "RECENT_TRANSACTIONS":
            sections[name] = recent_transactions(x.data)
        elif name == "GOALS":
            sections[name] = goals_section(x.goal_plans) or ["No goals set."]
        elif name == "RISKS":
            sections[name] = risks_section(x.alerts)
        elif name == "FORECAST":
            sections[name] = forecast_section(x.forecast, x.cash_flow)
        elif name == "SIMULATION_RESULTS" and x.simulation:
            sections[name] = simulation_section(
                x.simulation, x.scenario_description or "", x.scenario_assumptions
            )
    return sections
