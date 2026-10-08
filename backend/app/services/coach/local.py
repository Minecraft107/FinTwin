"""Deterministic coach answers built from backend results (the default, offline mode, and the
fallback whenever an LLM is unavailable or its answer fails the grounding check).

Every number here comes from the Digital Twin, Health Score, goal planner, forecaster,
risk scan or simulator; templates only arrange them into sentences.
"""

import re
from datetime import timedelta

from app.services.analytics import aggregations as agg
from app.services.coach.context import CoachInputs
from app.services.coach.entities import Entities
from app.services.coach.llm.base import CoachAnswer
from app.services.coach.rag import Hit
from app.utils.money import inr, pct

EXAMPLES = [
    "Can I afford a ₹1,30,000 laptop?",
    "Why did my health score change?",
    "Where am I overspending?",
    "How much should I save each month for my car goal?",
    "What happens if I increase my SIP by ₹5,000?",
]


def _first_sentences(text: str, n: int = 2) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sentences[:n])


def _background(hits: list[Hit], n: int = 2) -> list[str]:
    return [f"{_first_sentences(h.chunk.text)} (from '{h.chunk.title}')" for h in hits[:n]]


def _state_facts(x: CoachInputs) -> list[str]:
    t = x.twin
    return [
        f"Monthly income {inr(t.monthly_income)}; spending {inr(t.monthly_expenses)}; "
        f"EMIs {inr(t.debt_payments)}; SIPs {inr(t.investment_contributions)}.",
        f"Monthly surplus {inr(t.net_cash_flow)}; cash balance {inr(t.cash_balance)}; "
        f"emergency fund {inr(t.emergency_fund)}.",
    ]


def _simulation(x: CoachInputs, hits: list[Hit], intent: str) -> CoachAnswer:
    if not x.simulation:
        ask = (
            "Tell me the price, e.g. 'Can I afford a ₹1,30,000 laptop?'"
            if intent == "affordability"
            else "Try for example 'What if I take a ₹5 lakh loan?' or 'What if my income falls "
            "by 20%?'"
        )
        return CoachAnswer(
            summary=f"I couldn't work out the exact scenario to simulate. {ask}",
            facts=_state_facts(x),
            background=_background(hits, 1),
        )
    sim, impact = x.simulation, x.simulation["impact"]
    after, before = sim["simulated_state"], sim["baseline_state"]
    verdict = {
        "LOW": "looks manageable",
        "MEDIUM": "is manageable but has trade-offs",
        "HIGH": "would leave little safety margin",
        "CRITICAL": "would leave you unable to cover your outgoings",
    }[sim["risk_level"]]
    if sim["risk_level"] == "LOW" and (
        impact["net_worth_change"] > 0 or impact["monthly_cash_flow_change"] > 0
    ):
        verdict = "would strengthen your position"
    calculations = [
        f"Cash after 12 months: {inr(after['cash_balance'])} versus {inr(before['cash_balance'])} "
        f"without this change ({inr(impact['cash_change'])}).",
        f"Monthly surplus changes by {inr(impact['monthly_cash_flow_change'])}; net worth after "
        f"12 months changes by {inr(impact['net_worth_change'])}.",
    ]
    if impact["health_score_change"] is not None:
        calculations.append(
            f"Projected health score: {after['health_score']:.0f} versus "
            f"{before['health_score']:.0f} "
            f"({impact['health_score_change']:+.1f} points)."
        )
    if impact["emergency_fund_drawn"]:
        calculations.append(f"Emergency fund used: {inr(impact['emergency_fund_drawn'])}.")
    if impact["first_shortfall_month"]:
        calculations.append(
            f"Money runs out in {impact['first_shortfall_month']} (shortfall up to "
            f"{inr(impact['max_shortfall'])})."
        )
    goal_moves = [
        f"'{g['name']}' would be reached {abs(g['delay_months'])} month(s) "
        f"{'later' if g['delay_months'] > 0 else 'sooner'} ({g['scenario_completion']})."
        for g in sim["goals"]
        if g["delay_months"]
    ]
    predictions = sim["risk_factors"][:3] + goal_moves[:2]
    predictions.append(
        f"Projections cover {sim['scenario']['horizon_months']} months and assume your recent "
        "income and spending continue."
    )
    return CoachAnswer(
        summary=f"Based on a simulation of {x.scenario_description}, this {verdict} "
        f"(risk level: {sim['risk_level']}).",
        facts=_state_facts(x),
        calculations=calculations,
        predictions=predictions[:5],
        recommendations=[sim["recommendation"]]
        + [f"Assumption: {a}" for a in x.scenario_assumptions[:2]],
        background=_background(hits, 1),
    )


def _score(x: CoachInputs, hits: list[Hit]) -> CoachAnswer:
    h = x.health
    if h.score is None:
        return CoachAnswer(summary="Your health score isn't available yet: " + "; ".join(h.notes))
    summary = f"Your Financial Health Score is {h.score:.0f}/100 ({h.grade}, {h.label})."
    calculations = []
    if x.health_change:
        summary += " " + x.health_change["summary"]
        calculations = [
            f"{d['label']}: {d['points_change']:+.1f} points ({d['from']} → {d['to']})"
            for d in x.health_change["drivers"][:4]
            if abs(d["points_change"]) >= 0.1
        ]
    return CoachAnswer(
        summary=summary,
        facts=[
            f"{c.label}: {c.score:.0f}/100 — {c.explanation}"
            for c in h.components
            if c.score is not None
        ][:6],
        calculations=calculations,
        recommendations=[f"{r.title}: {r.action}" for r in h.recommendations[:3]],
        background=_background(hits, 1),
    )


def _improve(x: CoachInputs, hits: list[Hit]) -> CoachAnswer:
    h = x.health
    if h.score is None or not h.recommendations:
        return _score(x, hits)
    top = h.recommendations[:3]
    return CoachAnswer(
        summary=f"Your score is {h.score:.0f}/100. The changes that would raise it most are: "
        + "; ".join(f"{r.title.lower()} (up to {r.potential_points:.0f} points)" for r in top)
        + ".",
        facts=h.weaknesses[:3],
        recommendations=[r.action for r in top],
        background=_background(hits, 1),
    )


def _overspending(x: CoachInputs, hits: list[Hit]) -> CoachAnswer:
    end = x.data.today
    rows = [
        r
        for r in agg.categories(x.data.transactions, end - timedelta(days=89), end)
        if r["kind"] == "discretionary"
    ]
    if not rows:
        return CoachAnswer(
            summary="I don't see any discretionary spending in the last 90 days.",
            facts=_state_facts(x),
        )
    rising = [r for r in rows if r["change_pct"] and r["change_pct"] >= 20]
    summary = (
        f"Your largest discretionary category over the last 90 days is {rows[0]['category']} "
        f"at {inr(rows[0]['total'])}."
    )
    if rising:
        summary += (
            f" {rising[0]['category']} is up {rising[0]['change_pct']:.0f}% on the previous 90 "
            "days."
        )
    drift = [a for a in x.alerts if a["type"] == "category_spending_increase"]
    return CoachAnswer(
        summary=summary,
        facts=[
            f"{r['category']}: {inr(r['total'])}"
            + (
                f" ({r['change_pct']:+.0f}% vs the previous 90 days)"
                if r["change_pct"] is not None
                else ""
            )
            for r in rows[:5]
        ],
        calculations=[
            "Discretionary spending is "
            f"{pct(x.twin.discretionary_expenses / x.twin.monthly_income)} "
            "of income (guideline: at most 30%)."
        ]
        if x.twin.monthly_income
        else [],
        recommendations=[a["recommended_action"] for a in drift[:2]]
        or ["Set a monthly limit for your largest discretionary category and review it monthly."],
        background=_background(hits, 1),
    )


def _goals(x: CoachInputs, hits: list[Hit], e: Entities) -> CoachAnswer:
    plans = [p for p in x.goal_plans if p["goal_id"] in e.goal_ids] or x.goal_plans
    if not plans:
        return CoachAnswer(
            summary="You haven't set any goals yet. Add one with a target amount and date, and "
            "I'll work out how much to save each month.",
            background=_background(hits, 1),
        )
    first = plans[0]
    options = [o["text"] for p in plans[:2] for o in p["options"][:2]]
    return CoachAnswer(
        summary=first["explanation"],
        facts=[f"Monthly surplus available for goals: {inr(x.twin.net_cash_flow)}."],
        calculations=[
            f"{p['name']}: needs {inr(p['required_monthly'])}/month, your surplus can fund "
            f"{inr(p['fundable_monthly'])}/month (status: {p['status'].replace('_', ' ')})."
            if p["required_monthly"] is not None
            else f"{p['name']}: {p['explanation']}"
            for p in plans[:4]
        ],
        predictions=[
            f"{p['name']}: estimated completion {p['completion_at_fundable']} at the fundable pace."
            for p in plans[:4]
            if p["completion_at_fundable"]
        ],
        recommendations=options[:4],
        background=_background(hits, 1),
    )


def _emergency(x: CoachInputs, hits: list[Hit]) -> CoachAnswer:
    c = x.health.component("emergency_fund")
    rec = next((r for r in x.health.recommendations if r.component == "emergency_fund"), None)
    summary = (
        c.explanation
        or "I can't measure your emergency fund until essential expenses are recorded."
    )
    if c.score is not None:
        summary += " That is " + (
            "healthy."
            if c.score >= 80
            else "below the recommended level."
            if c.score <= 50
            else "fair."
        )
    return CoachAnswer(
        summary=summary,
        facts=[
            f"Emergency fund: {inr(x.twin.emergency_fund)}; essential spending + EMIs: "
            f"{inr(x.twin.essential_expenses + x.twin.debt_payments)}/month."
        ],
        calculations=[f"Emergency-fund component of your health score: {c.score:.0f}/100."]
        if c.score is not None
        else [],
        recommendations=[rec.action] if rec else [],
        background=_background(hits, 2),
    )


def _debt(x: CoachInputs, hits: list[Hit]) -> CoachAnswer:
    t = x.twin
    if not x.data.loans and not t.debt_payments:
        return CoachAnswer(
            summary="You have no loans or EMIs recorded.", background=_background(hits, 1)
        )
    c = x.health.component("debt")
    return CoachAnswer(
        summary=f"Your EMIs total {inr(t.debt_payments)}/month, which is {pct(t.debt_to_income)} "
        f"of your income; total outstanding is {inr(t.total_debt)}.",
        facts=[
            f"Loan at {loan.annual_interest_rate * 100:g}%: EMI {inr(loan.emi)}, outstanding "
            f"{inr(loan.outstanding)}."
            for loan in x.data.loans
        ][:4],
        calculations=[f"Debt component of your health score: {c.score:.0f}/100."]
        if c.score is not None
        else [],
        recommendations=[
            "Before prepaying, check for prepayment charges and keep your emergency "
            "fund intact; prepaying the highest-interest loan saves the most."
        ],
        background=_background(hits, 2),
    )


def _forecast(x: CoachInputs, hits: list[Hit]) -> CoachAnswer:
    f = x.forecast
    if not f or f.get("status") != "ok":
        return CoachAnswer(
            summary="I need at least one complete month of transactions to forecast. "
            "If more historical data is available, prediction confidence will improve."
        )
    predictions = [
        f"{p['month']}: about {inr(p['value'])} (likely {inr(p['lower'])}–{inr(p['upper'])})"
        for p in f["forecast"]
    ]
    if x.cash_flow and x.cash_flow.get("status") == "ok":
        predictions.append(x.cash_flow["explanation"])
    return CoachAnswer(
        summary=f["explanation"],
        calculations=[f"Model: {f['model']['label']} (confidence: {f['confidence']})."],
        predictions=predictions[:4],
        recommendations=[
            "Treat these as estimates: plan for the upper end of the range in months "
            "with known extra costs such as festivals or annual premiums."
        ],
    )


def _risks(x: CoachInputs, hits: list[Hit]) -> CoachAnswer:
    if not x.alerts:
        return CoachAnswer(
            summary="There are no active risk alerts on your account right now.",
            facts=_state_facts(x),
        )
    return CoachAnswer(
        summary=f"You have {len(x.alerts)} active alert(s); the most serious is: "
        f"{x.alerts[0]['title']}.",
        facts=[f"{a['severity']}: {a['title']} — {a['explanation']}" for a in x.alerts[:4]],
        recommendations=[a["recommended_action"] for a in x.alerts[:3]],
        background=_background(hits, 1),
    )


def answer(intent: str, x: CoachInputs, hits: list[Hit], e: Entities) -> CoachAnswer:
    if intent in ("affordability", "what_if"):
        return _simulation(x, hits, intent)
    if intent == "score_explanation":
        return _score(x, hits)
    if intent == "improve_health":
        return _improve(x, hits)
    if intent == "overspending":
        return _overspending(x, hits)
    if intent == "goal_planning":
        return _goals(x, hits, e)
    if intent == "emergency_fund":
        return _emergency(x, hits)
    if intent == "debt":
        return _debt(x, hits)
    if intent == "forecast":
        return _forecast(x, hits)
    if intent == "risk":
        return _risks(x, hits)
    if intent == "greeting":
        return CoachAnswer(
            summary="Hi! I'm your FinTwin coach. I answer questions using your own financial "
            "data, the app's calculations and simulations, and general financial knowledge.",
            recommendations=[f"Try: {q}" for q in EXAMPLES[:4]],
        )
    if intent == "out_of_scope":
        return CoachAnswer(
            summary="I can't recommend specific stocks, funds, crypto or other products, and I "
            "can't predict market returns. I can explain concepts like diversification and SIPs, "
            "and show how investing a given amount affects your plan.",
            facts=[
                f"You currently invest {inr(x.twin.investment_contributions)}/month "
                f"({pct(x.twin.investment_rate)} of income)."
            ],
            recommendations=[
                "For personalised investment advice, consult a SEBI-registered investment adviser.",
                "Ask me 'What happens if I increase my SIP by ₹5,000?' to see the "
                "effect on your plan.",
            ],
            background=_background(hits, 2),
        )
    if hits:  # concept question answered from the knowledge base
        return CoachAnswer(
            summary=_first_sentences(hits[0].chunk.text, 3),
            background=_background(hits[1:], 2),
        )
    return CoachAnswer(
        summary="I don't have information on that topic. I can help with your spending, savings, "
        "goals, debt, health score, forecasts and what-if scenarios.",
        recommendations=[f"Try: {q}" for q in EXAMPLES[:3]],
    )
