"""Turn a natural-language what-if / affordability question into a validated Scenario.

Deterministic pattern rules: the parsed scenario is shown back to the user, together with
any assumptions the parser had to make (e.g. a default loan rate), so nothing is hidden.
"""

import re
from dataclasses import dataclass, field

from app.services.coach.entities import Entities
from app.services.digital_twin.state import TwinState
from app.services.simulation.scenarios import Scenario
from app.utils.money import inr

DEFAULT_LOAN_RATE = 0.105  # assumed when the question gives no rate
DEFAULT_LOAN_MONTHS = 60
DEFAULT_JOB_LOSS_MONTHS = 6
DEFAULT_DELAY_MONTHS = 6

_DOWN = r"(cut|decrease|decreases|drop|drops|reduce|reduces|fall|falls|lower|down|less|loses?)"


@dataclass
class ParsedScenario:
    scenario: Scenario
    description: str
    assumptions: list[str] = field(default_factory=list)


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def parse_scenario(text: str, e: Entities, twin: TwinState) -> ParsedScenario | None:
    t = text.lower()
    changes: list[dict] = []
    parts: list[str] = []
    assumptions: list[str] = []
    amount = e.amount

    if _has(r"\b(lose|lost|losing) (my )?job\b|\bno income\b", t):
        months = e.months[0] if e.months else DEFAULT_JOB_LOSS_MONTHS
        changes.append({"type": "income_change", "pct": -100, "duration_months": months})
        parts.append(f"losing your income for {months} months")
        if not e.months:
            assumptions.append(
                f"Income stops for {DEFAULT_JOB_LOSS_MONTHS} months (no duration given)."
            )
    elif _has(r"\b(salary|income|pay)\b", t) and (e.percents or amount):
        sign = -1 if _has(_DOWN, t) else 1
        if e.percents:
            changes.append({"type": "income_change", "pct": sign * e.percents[0]})
            parts.append(f"your income {'falling' if sign < 0 else 'rising'} by {e.percents[0]:g}%")
        else:
            changes.append({"type": "income_change", "amount": sign * amount})
            parts.append(
                f"your income {'falling' if sign < 0 else 'rising'} by {inr(amount)}/month"
            )

    if _has(r"\bsips?\b", t):
        if _has(r"\b(stop|pause|cancel)\b", t):
            changes.append({"type": "sip_change", "amount": -twin.investment_contributions})
            parts.append(f"stopping your SIPs ({inr(twin.investment_contributions)}/month)")
        elif amount:
            sign = -1 if _has(_DOWN, t) else 1
            changes.append({"type": "sip_change", "amount": sign * amount})
            parts.append(
                f"{'reducing' if sign < 0 else 'increasing'} your SIP by {inr(amount)}/month"
            )

    windfall = _has(r"\b(bonus|windfall|inheritance|gift|prize)\b", t)
    purchase = _has(r"\b(buy|purchase|afford|buying|get)\b", t) and not windfall
    financed = _has(r"\b(emi|loan|finance|financed|installments?)\b", t)
    if _has(r"\bloan\b", t) and amount and not purchase:
        rate = e.percents[0] / 100 if e.percents else DEFAULT_LOAN_RATE
        months = e.months[0] if e.months else DEFAULT_LOAN_MONTHS
        changes.append(
            {"type": "new_loan", "principal": amount, "annual_rate": rate, "tenure_months": months}
        )
        parts.append(f"taking a {inr(amount)} loan at {rate * 100:g}% for {months} months")
        if not e.percents:
            assumptions.append(
                f"Loan interest rate assumed at {DEFAULT_LOAN_RATE * 100:g}% a year."
            )
        if not e.months:
            assumptions.append(f"Loan tenure assumed at {DEFAULT_LOAN_MONTHS} months.")
    elif purchase and amount:
        change = {"type": "large_purchase", "amount": amount}
        if financed:
            rate = e.percents[0] / 100 if e.percents else DEFAULT_LOAN_RATE
            months = e.months[0] if e.months else 24
            change |= {
                "financed_by_loan": True,
                "loan_annual_rate": rate,
                "loan_tenure_months": months,
            }
            parts.append(f"buying something for {inr(amount)} on a {months}-month loan")
            if not e.percents:
                assumptions.append(
                    f"Loan interest rate assumed at {DEFAULT_LOAN_RATE * 100:g}% a year."
                )
        else:
            parts.append(f"spending {inr(amount)} on a purchase now")
        changes.append(change)

    if _has(r"\b(expenses?|spending|rent)\b", t) and (amount or e.percents) and not purchase:
        sign = -1 if _has(_DOWN, t) else 1
        kind = "essential" if _has(r"\b(rent|groceries|essential|bills?)\b", t) else "discretionary"
        change = {"type": "expense_change", "kind": kind}
        if e.percents:
            change["pct"] = sign * e.percents[0]
            parts.append(
                f"{kind} spending {'falling' if sign < 0 else 'rising'} by {e.percents[0]:g}%"
            )
        else:
            change["amount"] = sign * amount
            parts.append(
                f"{kind} spending {'falling' if sign < 0 else 'rising'} by {inr(amount)}/month"
            )
        changes.append(change)
    elif _has(r"\b(save|saving) .*\bmore\b|\bspend .*\bless\b", t) and amount:
        changes.append({"type": "extra_savings", "amount": amount})
        parts.append(f"saving an extra {inr(amount)} every month")

    if _has(r"\b(delay|postpone|push back)\b", t) and e.goal_ids:
        months = e.months[0] if e.months else DEFAULT_DELAY_MONTHS
        goal = next(g for g in twin.goals if g.id == e.goal_ids[0])
        changes.append({"type": "goal_delay", "goal_id": goal.id, "months": months})
        parts.append(f"delaying '{goal.name}' by {months} months")

    if windfall and amount:
        changes.append({"type": "one_time_income", "amount": amount})
        parts.append(f"receiving a one-time {inr(amount)}")

    if not changes:
        return None
    scenario = Scenario.model_validate({"changes": changes[:10]})
    return ParsedScenario(scenario, " and ".join(parts), assumptions)
