"""What-If simulation: Digital Twin -> scenario -> deterministic projection -> comparison.

Both the baseline (no change) and the scenario are projected with the same engine, so the
impact isolates the effect of the scenario. Future states are turned back into TwinStates
and scored with the same Health Score code as the present. All numbers are computed here;
an LLM may later explain them but never produces them.
"""

import math
from dataclasses import replace

import pandas as pd

from app.services.digital_twin.builder import build_twin, derive
from app.services.digital_twin.state import GoalProgress, MonthFlow, TwinState, UserData
from app.services.financial.health_score import score_twin
from app.services.simulation.engine import (
    Baseline,
    GoalState,
    LoanState,
    Projection,
    months_to_save,
    project,
)
from app.services.simulation.scenarios import LargePurchase, Scenario
from app.utils.dates import month_end
from app.utils.money import inr, pct

CHECKPOINT_MONTHS = 12
DISCLAIMER = (
    "Simulations are estimates under the stated assumptions, not predictions or guarantees. "
    "FinTwin is a decision-support tool, not a licensed financial advisor."
)


def baseline_from(data: UserData, twin: TwinState) -> Baseline:
    loans = [
        LoanState(f"Loan {i + 1}", loan.outstanding, loan.annual_interest_rate, loan.emi)
        for i, loan in enumerate(data.loans)
        if loan.outstanding > 0
    ]
    total_value = sum(i.current_value for i in data.investments)
    weighted_return = (
        sum(i.current_value * i.expected_annual_return for i in data.investments) / total_value
        if total_value
        else 0.0
    )
    return Baseline(
        today=data.today,
        income=twin.monthly_income,
        essential=twin.essential_expenses,
        discretionary=twin.discretionary_expenses,
        sip=twin.investment_contributions,
        untracked_emi=twin.debt_payments if not loans else 0.0,
        cash=twin.cash_balance,
        emergency_fund=twin.emergency_fund,
        investments=twin.investments_value,
        investment_return=weighted_return,
        loans=loans,
        goals=[
            GoalState(
                g.id,
                g.name,
                g.target_amount,
                g.current_amount,
                g.monthly_contribution,
                g.priority,
                g.target_date,
                g.status,
            )  # fmt: skip
            for g in twin.goals
        ],
    )


def simulated_twin(twin: TwinState, proj: Projection, k: int) -> TwinState:
    """The Digital Twin as it would stand at the end of projection month k."""
    m = proj.at(k)
    flows = [
        MonthFlow(x.month, x.income, x.essential, x.discretionary + x.one_time_out, x.emi, x.sip)
        for x in proj.months[max(0, k - 6) : k]
    ]
    recent = [*twin.recent_months[-(6 - len(flows)) :], *flows] if len(flows) < 6 else flows
    goals = [
        GoalProgress(
            id=g.id, name=g.name, target_amount=g.target, current_amount=m.goal_balances[g.id],
            progress_pct=min(m.goal_balances[g.id] / g.target, 1.0) * 100,
            remaining=max(g.target - m.goal_balances[g.id], 0.0), monthly_contribution=g.planned,
            target_date=g.target_date, priority=g.priority, status=g.status,
        )
        for g in proj.goals
    ]  # fmt: skip
    return derive(
        replace(
            twin,
            as_of=month_end(pd.Period(m.month, "M").to_timestamp().date()),
            monthly_income=m.income,
            essential_expenses=m.essential,
            discretionary_expenses=m.discretionary,
            debt_payments=m.emi,
            investment_contributions=m.sip,
            cash_balance=m.cash,
            emergency_fund=m.emergency_fund,
            investments_value=m.investments,
            total_debt=m.debt,
            goals_saved=m.goals_saved,
            recent_months=recent,
            goals=goals,
            notes=[],
        )
    )


def _summary(t: TwinState) -> dict:
    health = score_twin(t)
    return {
        "as_of": t.as_of.isoformat(),
        "cash_balance": round(t.cash_balance, 2),
        "emergency_fund": round(t.emergency_fund, 2),
        "investments_value": round(t.investments_value, 2),
        "total_debt": round(t.total_debt, 2),
        "net_worth": round(t.net_worth, 2),
        "monthly_income": round(t.monthly_income, 2),
        "monthly_expenses": round(t.monthly_expenses, 2),
        "debt_payments": round(t.debt_payments, 2),
        "investment_contributions": round(t.investment_contributions, 2),
        "net_cash_flow": round(t.net_cash_flow, 2),
        "savings_ratio": None if t.savings_ratio is None else round(t.savings_ratio, 4),
        "debt_to_income": None if t.debt_to_income is None else round(t.debt_to_income, 4),
        "emergency_months": None if t.emergency_months is None else round(t.emergency_months, 2),
        "health_score": None if health.score is None else round(health.score, 1),
        "grade": health.grade,
    }


def _delta(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round(a - b, 4)


PACE_MONTHS = 3  # recent projected months used to extrapolate goals beyond the horizon


def _completion(proj: Projection, goal: GoalState) -> tuple[str | None, bool]:
    """(YYYY-MM, estimated?) when the goal is reached. Inside the horizon it is simulated;
    beyond it, extrapolated from the saving pace of the final months. None = never at that pace."""
    if goal.completed:
        return goal.completed, False
    months = proj.months
    if len(months) <= PACE_MONTHS:
        return None, False
    pace = (
        months[-1].goal_balances[goal.id] - months[-1 - PACE_MONTHS].goal_balances[goal.id]
    ) / PACE_MONTHS
    if pace <= 0:
        return None, False
    remaining = goal.target - months[-1].goal_balances[goal.id]
    return str(pd.Period(months[-1].month, "M") + math.ceil(remaining / pace)), True


def _month_gap(a: str, b: str) -> int:
    return (pd.Period(b, "M") - pd.Period(a, "M")).n


def _goal_outcomes(base: Projection, scen: Projection, k: int) -> list[dict]:
    out = []
    for g in scen.goals:
        b = next(x for x in base.goals if x.id == g.id)
        if g.status != "active":
            continue
        b_done, b_est = _completion(base, b)
        s_done, s_est = _completion(scen, g)
        target = g.target_date.strftime("%Y-%m") if g.target_date else None
        out.append(
            {
                "goal_id": g.id,
                "name": g.name,
                "target_date": target,
                "baseline_completion": b_done,
                "baseline_completion_estimated": b_est,
                "scenario_completion": s_done,
                "scenario_completion_estimated": s_est,
                # Positive = later than without the change. None when either is never reached.
                "delay_months": _month_gap(b_done, s_done) if b_done and s_done else None,
                "no_longer_reached": b_done is not None and s_done is None,
                "on_track": bool(s_done and target and s_done <= target),
                "saved_at_checkpoint": {
                    "baseline": round(base.at(k).goal_balances[g.id], 2),
                    "scenario": round(scen.at(k).goal_balances[g.id], 2),
                },
            }
        )
    return out


def _risk(
    base: Projection, scen: Projection, score_drop: float, goals: list[dict]
) -> tuple[str, list[str]]:
    factors_by_level: dict[str, list[str]] = {"CRITICAL": [], "HIGH": [], "MEDIUM": []}
    shortfalls = [m for m in scen.months if m.shortfall > 0]
    if shortfalls:
        worst = max(shortfalls, key=lambda m: m.shortfall)
        factors_by_level["CRITICAL"].append(
            f"Money runs out in {shortfalls[0].month}: short by up to {inr(worst.shortfall)} "
            f"({worst.month}) even after using the emergency fund."
        )

    def coverage(m) -> float:
        obligations = m.essential + m.emi
        return m.emergency_fund / obligations if obligations else float("inf")

    low = [m for m in scen.months if coverage(m) < 1]
    if low and not any(coverage(m) < 1 for m in base.months):
        factors_by_level["HIGH"].append(
            f"Emergency cover falls below 1 month of essentials and EMIs in {low[0].month}."
        )
    heavy = [m for m in scen.months if m.income and m.emi / m.income > 0.5]
    if heavy:
        factors_by_level["HIGH"].append(
            f"EMIs exceed 50% of income from {heavy[0].month} "
            f"({pct(heavy[0].emi / heavy[0].income)})."
        )
    if score_drop >= 15:
        factors_by_level["HIGH"].append(f"Health score falls by {score_drop:.0f} points.")
    elif score_drop >= 5:
        factors_by_level["MEDIUM"].append(f"Health score falls by {score_drop:.0f} points.")
    drawn = sum(m.emergency_drawn for m in scen.months) - sum(
        m.emergency_drawn for m in base.months
    )
    if drawn > 1:
        factors_by_level["MEDIUM"].append(f"Uses {inr(drawn)} of your emergency fund.")

    def thin(m) -> bool:
        return m.cash < m.essential + m.discretionary + m.emi

    thin_months = [m for m in scen.months if thin(m)]
    if thin_months and not any(thin(m) for m in base.months):
        factors_by_level["MEDIUM"].append(
            f"Your cash balance drops below one month of outgoings in {thin_months[0].month}."
        )
    for g in goals:
        if g["no_longer_reached"]:
            factors_by_level["MEDIUM"].append(
                f"'{g['name']}' is no longer reached at the simulated saving pace."
            )
        elif g["delay_months"] and g["delay_months"] >= 3:
            estimated = " (estimated)" if g["scenario_completion_estimated"] else ""
            factors_by_level["MEDIUM"].append(
                f"'{g['name']}' is delayed by {g['delay_months']} months{estimated}."
            )
    level = next((lvl for lvl in ("CRITICAL", "HIGH", "MEDIUM") if factors_by_level[lvl]), "LOW")
    return level, [f for lvl in ("CRITICAL", "HIGH", "MEDIUM") for f in factors_by_level[lvl]]


def _recommendation(scenario: Scenario, level: str, impact: dict, base_surplus: float) -> str:
    purchase = sum(
        c.amount
        for c in scenario.changes
        if isinstance(c, LargePurchase) and not c.financed_by_loan
    )
    if level == "CRITICAL":
        text = (
            "Based on the simulated assumptions, this scenario leaves you unable to cover your "
            "outgoings. Consider a smaller amount, spreading the cost, or saving first."
        )
    elif level == "HIGH":
        text = (
            "Based on the simulated assumptions, this scenario is affordable on paper but leaves "
            "little safety margin. Rebuilding your emergency fund first would reduce the risk."
        )
    elif level == "MEDIUM":
        text = (
            "Based on the simulated assumptions, this scenario is manageable but has trade-offs "
            "(listed under risk factors) that are worth weighing."
        )
    elif (
        (impact["health_score_change"] or 0) > 0
        or impact["monthly_cash_flow_change"] > 0
        or impact["net_worth_change"] > 0
    ):
        text = (
            "Based on the simulated assumptions, this scenario strengthens your financial position."
        )
    else:
        text = (
            "Based on the simulated assumptions, this scenario does not materially weaken "
            "your position."
        )
    if purchase:
        months = months_to_save(purchase, base_surplus)
        text += (
            f" At your current monthly surplus of {inr(base_surplus)}, saving {inr(purchase)} "
            f"would take about {months} month(s)."
            if months
            else " Your current monthly surplus is not positive, so this would have to come "
            "from savings."
        )
    return text


def run_scenario(data: UserData, scenario: Scenario) -> dict:
    twin = build_twin(data)
    base = baseline_from(data, twin)
    horizon = scenario.horizon_months
    baseline_proj = project(base, [], horizon, scenario.inflation_pct)
    scenario_proj = project(base, list(scenario.changes), horizon, scenario.inflation_pct)
    k = min(CHECKPOINT_MONTHS, horizon)

    b_twin, s_twin = simulated_twin(twin, baseline_proj, k), simulated_twin(twin, scenario_proj, k)
    current, b_state, s_state = _summary(twin), _summary(b_twin), _summary(s_twin)
    b_k, s_k = baseline_proj.at(k), scenario_proj.at(k)
    b_end, s_end = baseline_proj.months[-1], scenario_proj.months[-1]
    goals = _goal_outcomes(baseline_proj, scenario_proj, k)
    score_change = _delta(s_state["health_score"], b_state["health_score"])
    shortfalls = [m for m in scenario_proj.months if m.shortfall > 0]
    lowest = min(scenario_proj.months, key=lambda m: m.cash)

    impact = {
        "checkpoint_month": s_k.month,
        "checkpoint_months_ahead": k,
        "cash_change": round(s_k.cash - b_k.cash, 2),
        "cash_change_at_horizon": round(s_end.cash - b_end.cash, 2),
        "monthly_cash_flow_change": round(s_k.recurring_surplus - b_k.recurring_surplus, 2),
        "savings_change": _delta(s_state["savings_ratio"], b_state["savings_ratio"]),
        "emergency_fund_change": round(s_k.emergency_fund - b_k.emergency_fund, 2),
        "emergency_months_change": _delta(s_state["emergency_months"], b_state["emergency_months"]),
        "debt_change": round(s_k.debt - b_k.debt, 2),
        "debt_to_income_change": _delta(s_state["debt_to_income"], b_state["debt_to_income"]),
        "investment_change": round(s_k.investments - b_k.investments, 2),
        "goals_saved_change": round(s_k.goals_saved - b_k.goals_saved, 2),
        "net_worth_change": round(s_k.net_worth - b_k.net_worth, 2),
        "net_worth_change_at_horizon": round(s_end.net_worth - b_end.net_worth, 2),
        "health_score_change": score_change,
        "goal_delay": max((g["delay_months"] or 0 for g in goals), default=0),
        "goals_no_longer_reached": [g["name"] for g in goals if g["no_longer_reached"]],
        "emergency_fund_drawn": round(sum(m.emergency_drawn for m in scenario_proj.months), 2),
        "first_shortfall_month": shortfalls[0].month if shortfalls else None,
        "max_shortfall": round(max((m.shortfall for m in shortfalls), default=0.0), 2),
        "lowest_cash": {"month": lowest.month, "value": round(lowest.cash, 2)},
    }
    level, factors = _risk(baseline_proj, scenario_proj, -(score_change or 0), goals)
    base_surplus = baseline_proj.at(1).recurring_surplus

    def signed(x: float) -> str:
        return f"{'+' if x >= 0 else '−'}{inr(abs(x))}"

    explanation = (
        f"Simulated over {horizon} months. By {s_k.month}, your net worth would be "
        f"{inr(s_k.net_worth)} versus {inr(b_k.net_worth)} without this change "
        f"({signed(impact['net_worth_change'])}); cash {inr(s_k.cash)} versus {inr(b_k.cash)}; "
        f"monthly surplus {inr(s_k.recurring_surplus)} versus {inr(b_k.recurring_surplus)}."
    )
    if impact["goals_saved_change"]:
        explanation += f" Goal savings change by {signed(impact['goals_saved_change'])}."
    if score_change is not None:
        explanation += (
            f" Projected health score: {s_state['health_score']:.0f} versus "
            f"{b_state['health_score']:.0f} ({score_change:+.1f})."
        )
    for g in goals:
        if not g["delay_months"]:
            continue
        word = "later" if g["delay_months"] > 0 else "sooner"
        estimated = (
            " (estimated from the saving pace)" if g["scenario_completion_estimated"] else ""
        )
        explanation += (
            f" '{g['name']}' would be reached {abs(g['delay_months'])} month(s) {word}: "
            f"{g['scenario_completion']} instead of {g['baseline_completion']}{estimated}."
        )

    return {
        "scenario": scenario.model_dump(mode="json"),
        "current_state": current,
        "baseline_state": b_state,
        "simulated_state": s_state,
        "impact": impact,
        "goals": goals,
        "risk_level": level,
        "risk_factors": factors,
        "recommendation": _recommendation(scenario, level, impact, base_surplus),
        "explanation": explanation,
        "timeline": [
            {
                "month": b.month,
                "baseline": _point(b),
                "scenario": _point(s),
            }
            for b, s in zip(baseline_proj.months, scenario_proj.months, strict=True)
        ],
        "assumptions": _assumptions(twin, base, scenario),
        "notes": scenario_proj.notes,
        "disclaimer": DISCLAIMER,
    }


def _point(m) -> dict:
    return {
        "cash": round(m.cash, 2),
        "emergency_fund": round(m.emergency_fund, 2),
        "investments": round(m.investments, 2),
        "debt": round(m.debt, 2),
        "goals_saved": round(m.goals_saved, 2),
        "net_worth": round(m.net_worth, 2),
        "net_cash_flow": round(m.net_cash_flow, 2),
    }


def _assumptions(twin: TwinState, base: Baseline, scenario: Scenario) -> list[str]:
    window = (
        f"the average of your last {twin.window_months} complete month(s)"
        if twin.window_months
        else "your declared profile values"
    )
    return [
        f"Income ({inr(base.income)}/month) and spending ({inr(base.essential)} essential + "
        f"{inr(base.discretionary)} discretionary) continue at {window}, except where the "
        "scenario changes them.",
        f"Spending grows with inflation of {scenario.inflation_pct:g}% a year."
        if scenario.inflation_pct
        else "No inflation is applied.",
        f"Investments grow at {pct(base.investment_return)} a year (value-weighted expected "
        "return of your holdings); cash earns nothing.",
        "Existing loans are amortised at their recorded rates; new loans use the standard EMI "
        "formula, with the first EMI the month after disbursement.",
        "Goal contributions come from each month's surplus, in priority order, up to each "
        "goal's planned amount, and only from cash above one month of outgoings.",
        "If cash goes negative, the emergency fund covers the gap; anything beyond is a shortfall.",
        f"Impact is measured {min(CHECKPOINT_MONTHS, scenario.horizon_months)} months ahead, "
        "against the same projection without the change.",
    ]


def goal_ids(data: UserData) -> set[int]:
    return {g.id for g in data.goals}
