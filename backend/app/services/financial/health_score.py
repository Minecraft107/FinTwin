"""Financial Health Score (0-100): a transparent weighted mean of seven component scores.

Each component maps one measurable indicator from the Digital Twin to 0-100 through a
piecewise-linear curve whose anchor points come from widely cited personal-finance
guidelines (see SPECS[...].basis). Components that cannot be measured are excluded and the
remaining weights renormalised, never silently scored as zero.

Pure: input is a TwinState, output a HealthScoreResult. No DB, no Flask.
"""

import statistics
from dataclasses import asdict, dataclass, field
from datetime import date

from app.services.digital_twin.state import TwinState
from app.services.financial.goals import allocate_surplus
from app.utils.money import inr, pct

Anchors = tuple[tuple[float, float], ...]

STRONG, WEAK = 80, 50
ANOMALY_PENALTY = 35  # sub-score points lost per recent HIGH/CRITICAL anomaly
GRADES = ((85, "A", "Excellent"), (70, "B", "Good"), (55, "C", "Fair"), (40, "D", "Weak"),
          (0, "E", "Critical"))  # fmt: skip


@dataclass(frozen=True)
class Spec:
    label: str
    weight: float
    indicator: str
    target: str
    basis: str
    anchors: Anchors = ()
    formula: str = ""


SPECS: dict[str, Spec] = {
    "savings": Spec(
        "Savings",
        20,
        "Savings ratio",
        "≥ 20%",
        "The 50/30/20 budgeting rule suggests saving at least 20% of income.",
        anchors=((0.0, 0), (0.10, 50), (0.20, 80), (0.30, 100)),
        formula="(income − expenses − EMIs) ÷ income; money invested counts as saved",
    ),
    "emergency_fund": Spec(
        "Emergency fund",
        20,
        "Emergency-fund coverage",
        "3–6 months",
        "A common guideline is an emergency fund covering 3–6 months of essential costs.",
        anchors=((0, 0), (1, 30), (3, 70), (6, 100)),
        formula="emergency fund ÷ monthly (essential expenses + EMIs), in months",
    ),
    "debt": Spec(
        "Debt burden",
        20,
        "Debt-to-income ratio",
        "≤ 20%",
        "Lenders commonly treat EMIs above 36% of income as high and above 50% as critical.",
        anchors=((0.0, 100), (0.20, 80), (0.36, 50), (0.50, 20), (0.60, 0)),
        formula="monthly EMIs ÷ monthly income",
    ),
    "cash_flow": Spec(
        "Cash-flow stability",
        15,
        "Cash-flow stability",
        "6 of 6 months positive",
        "Consistently positive, predictable monthly cash flow indicates a stable budget.",
        formula="70 × share of the last 6 months with positive net cash flow"
        " + 30 × (1 − min(CV of monthly spending ÷ 0.5, 1))",
    ),
    "investments": Spec(
        "Investments",
        10,
        "Investment rate",
        "10–15% of income",
        "A common guideline is to invest 10–15% of income, spread over more than one asset type.",
        anchors=((0.0, 0), (0.10, 70), (0.15, 100)),
        formula="70% × curve(investment contributions ÷ income)"
        " + 30% × diversification (1 type = 30, 2 = 70, 3+ = 100)",
    ),
    "goals": Spec(
        "Goal progress",
        10,
        "Goal funding",
        "100% of required contributions",
        "Goals are funded from the monthly surplus in priority order; this measures how much "
        "of the saving each goal needs is actually affordable.",
        formula="priority-weighted mean of min(1, fundable ÷ required monthly saving) × 100",
    ),
    "spending": Spec(
        "Spending behaviour",
        5,
        "Discretionary share of income",
        "≤ 30%",
        "The 50/30/20 rule suggests keeping wants (discretionary spending) within 30% of income.",
        anchors=((0.30, 100), (0.50, 50), (0.70, 0)),
        formula=f"curve(discretionary ÷ income); when anomaly data is available, 70% of that"
        f" + 30% × (100 − {ANOMALY_PENALTY} per HIGH/CRITICAL anomaly in the last 30 days)",
    ),
}
DIVERSIFICATION = {0: 0, 1: 30, 2: 70}  # 3+ types -> 100


def interpolate(x: float, anchors: Anchors) -> float:
    """Piecewise-linear curve through `anchors`, flat beyond the first and last points."""
    (x0, y0), (xn, yn) = anchors[0], anchors[-1]
    if x <= x0:
        return float(y0)
    if x >= xn:
        return float(yn)
    for (xa, ya), (xb, yb) in zip(anchors, anchors[1:], strict=False):
        if xa <= x <= xb:
            return ya + (yb - ya) * (x - xa) / (xb - xa)
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class Measure:
    score: float | None
    value: float | None
    display: str
    explanation: str
    excluded_reason: str | None = None


@dataclass(frozen=True)
class Component:
    key: str
    label: str
    weight: float
    score: float | None
    effective_weight: float  # share of the total after renormalisation (0-1)
    points: float  # contribution to the total score
    indicator: str
    value: float | None
    value_display: str
    target: str
    basis: str
    explanation: str
    excluded_reason: str | None

    @property
    def status(self) -> str:
        if self.score is None:
            return "excluded"
        return "strong" if self.score >= STRONG else "weak" if self.score <= WEAK else "fair"


@dataclass(frozen=True)
class Recommendation:
    component: str
    title: str
    action: str
    potential_points: float  # score points available if this component reached 100


@dataclass(frozen=True)
class HealthScoreResult:
    as_of: date
    score: float | None
    grade: str
    label: str
    components: list[Component]
    strengths: list[str]
    weaknesses: list[str]
    recommendations: list[Recommendation]
    notes: list[str] = field(default_factory=list)

    def component(self, key: str) -> Component:
        return next(c for c in self.components if c.key == key)

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "score": None if self.score is None else round(self.score, 1),
            "grade": self.grade,
            "label": self.label,
            "components": [
                {
                    **asdict(c),
                    "status": c.status,
                    "score": None if c.score is None else round(c.score, 1),
                    "effective_weight": round(c.effective_weight, 4),
                    "points": round(c.points, 2),
                    "value": None if c.value is None else round(c.value, 4),
                }  # fmt: skip
                for c in self.components
            ],
            "excluded_components": [c.key for c in self.components if c.score is None],
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "recommendations": [
                {**asdict(r), "potential_points": round(r.potential_points, 1)}
                for r in self.recommendations
            ],
            "notes": self.notes,
        }


def grade_for(score: float) -> tuple[str, str]:
    return next((g, label) for floor, g, label in GRADES if score >= floor)


# ---------------------------------------------------------------- component measures


def _savings(t: TwinState) -> Measure:
    if t.savings_ratio is None:
        if t.monthly_expenses + t.debt_payments > 0:
            return Measure(0, None, "no income", "You have spending but no recorded income.")
        return Measure(None, None, "n/a", "", "No income or spending recorded yet.")
    r = t.savings_ratio
    return Measure(
        interpolate(r, SPECS["savings"].anchors), r, pct(r),
        f"You keep {pct(r)} of your income after expenses and EMIs; the 50/30/20 guideline "
        "is at least 20%.",
    )  # fmt: skip


def _emergency(t: TwinState) -> Measure:
    if t.emergency_months is None:
        return Measure(None, None, "n/a", "", "No essential expenses recorded to measure against.")
    m = t.emergency_months
    obligations = t.essential_expenses + t.debt_payments
    return Measure(
        interpolate(m, SPECS["emergency_fund"].anchors), m, f"{m:.1f} months",
        f"Your emergency fund of {inr(t.emergency_fund)} covers {m:.1f} months of essential "
        f"expenses and EMIs ({inr(obligations)}/month); 3–6 months is recommended.",
    )  # fmt: skip


def _debt(t: TwinState) -> Measure:
    if t.debt_to_income is None:
        if t.debt_payments > 0:
            return Measure(0, None, "no income", "You have EMIs but no recorded income.")
        return Measure(None, None, "n/a", "", "No income recorded yet.")
    d = t.debt_to_income
    text = (
        f"EMIs take {pct(d)} of your income ({inr(t.debt_payments)}/month)."
        if t.debt_payments
        else "You have no EMIs."
    )
    return Measure(interpolate(d, SPECS["debt"].anchors), d, pct(d), text)


def _cash_flow(t: TwinState) -> Measure:
    months = t.recent_months
    if len(months) < 3:
        return Measure(None, None, "n/a", "", "Needs at least 3 complete months of history.")
    positive = sum(m.net > 0 for m in months)
    spend = [m.expenses for m in months]
    mean = statistics.fmean(spend)
    cv = statistics.pstdev(spend) / mean if mean else 0.0
    score = 70 * positive / len(months) + 30 * (1 - min(cv / 0.5, 1))
    negative = [m.month for m in months if m.net <= 0]
    text = f"{positive} of the last {len(months)} months had positive cash flow"
    text += f" (negative: {', '.join(negative)})" if negative else ""
    text += f"; monthly spending varies by about {cv * 100:.0f}% around its average."
    return Measure(score, positive / len(months), f"{positive} of {len(months)} months", text)


def _investments(t: TwinState) -> Measure:
    if t.investment_rate is None:
        return Measure(None, None, "n/a", "", "No income recorded yet.")
    rate = t.investment_rate
    types = sum(1 for share in t.investment_allocation.values() if share > 0)
    score = 0.7 * interpolate(rate, SPECS["investments"].anchors) + 0.3 * DIVERSIFICATION.get(
        types, 100
    )
    return Measure(
        score, rate, pct(rate),
        f"You invest {pct(rate)} of income ({inr(t.investment_contributions)}/month) across "
        f"{types} asset type(s).",
    )  # fmt: skip


def _goals(t: TwinState) -> Measure:
    funding = [f for f in allocate_surplus(t.goals, t.net_cash_flow, t.as_of) if f.required_monthly]
    if not funding:
        return Measure(None, None, "n/a", "", "No active goals with a target date.")
    weights = [6 - f.priority for f in funding]
    ratios = [min(f.fundable_monthly / f.required_monthly, 1.0) for f in funding]
    score = 100 * sum(w * r for w, r in zip(weights, ratios, strict=True)) / sum(weights)
    required = sum(f.required_monthly for f in funding)
    fundable = sum(f.fundable_monthly for f in funding)
    return Measure(
        score, score / 100, f"{score:.0f}%",
        f"Your goals need about {inr(required)}/month to stay on schedule; your current surplus "
        f"can fund {inr(fundable)}/month of that.",
    )  # fmt: skip


def _spending(t: TwinState, recent_high_alerts: int | None) -> Measure:
    if t.monthly_income <= 0:
        return Measure(None, None, "n/a", "", "No income recorded yet.")
    share = t.discretionary_expenses / t.monthly_income
    score = interpolate(share, SPECS["spending"].anchors)
    text = (
        f"Discretionary spending is {pct(share)} of income ({inr(t.discretionary_expenses)}/month)."
    )
    if recent_high_alerts is not None:
        score = 0.7 * score + 0.3 * max(0, 100 - ANOMALY_PENALTY * recent_high_alerts)
        text += f" {recent_high_alerts} high-severity spending anomaly(ies) in the last 30 days."
    return Measure(score, share, pct(share), text)


# ---------------------------------------------------------------- recommendations


def _recommendation(key: str, t: TwinState) -> tuple[str, str]:
    if key == "savings":
        income = t.monthly_income
        gap = max(0.20 * income - (income - t.monthly_expenses - t.debt_payments), 0)
        action = (
            f"Reducing spending by about {inr(gap)}/month would lift your savings ratio to 20%."
        )
        if t.discretionary_by_category:
            top, amount = next(iter(t.discretionary_by_category.items()))
            action += f" Your largest discretionary category is {top} at {inr(amount)}/month."
        return "Raise your savings ratio", action
    if key == "emergency_fund":
        obligations = t.essential_expenses + t.debt_payments
        months = t.emergency_months or 0
        target = 3 if months < 3 else 6
        gap = max(target * obligations - t.emergency_fund, 0)
        action = (
            f"Reaching {target} months of cover needs {inr(gap)} more — about "
            f"{inr(gap / 12)}/month over a year."
        )
        if t.cash_balance >= gap > 0:
            action += (
                f" Your account balance is {inr(t.cash_balance)}; earmarking {inr(gap)} of it "
                "as emergency savings would close the gap immediately."
            )
        return "Strengthen your emergency fund", action
    if key == "debt":
        return "Reduce your debt burden", (
            f"EMIs take {pct(t.debt_to_income)} of income. Avoiding new EMIs until this is below "
            "20%, and prepaying the highest-interest loan when possible, lowers it."
        )
    if key == "cash_flow":
        return "Smooth your monthly cash flow", (
            "Months with negative cash flow usually come from irregular large purchases. "
            "Planning big expenses ahead and setting a monthly limit for discretionary "
            "categories keeps cash flow positive."
        )
    if key == "investments":
        return "Review your investing habit", (
            f"You invest {pct(t.investment_rate)} of income. A common guideline is 10–15%, "
            "spread across more than one asset type. This is educational context, not a "
            "recommendation of any specific product."
        )
    if key == "goals":
        planned = sum(g.monthly_contribution for g in t.goals if g.status == "active")
        return "Make your goals affordable", (
            f"Planned goal contributions ({inr(planned)}/month) exceed your monthly surplus "
            f"({inr(max(t.net_cash_flow, 0))}). Extending target dates, reprioritising, or "
            "freeing up spending would close the gap."
        )
    return "Rein in discretionary spending", (
        f"Discretionary spending is {pct(t.discretionary_expenses / t.monthly_income)} of income "
        "against a 30% guideline."
    )


# ---------------------------------------------------------------- scoring


def score_twin(twin: TwinState, recent_high_alerts: int | None = None) -> HealthScoreResult:
    """`recent_high_alerts`: HIGH/CRITICAL anomalies in the last 30 days (None = not assessed)."""
    measures = {
        "savings": _savings(twin),
        "emergency_fund": _emergency(twin),
        "debt": _debt(twin),
        "cash_flow": _cash_flow(twin),
        "investments": _investments(twin),
        "goals": _goals(twin),
        "spending": _spending(twin, recent_high_alerts),
    }
    included_weight = sum(SPECS[k].weight for k, m in measures.items() if m.score is not None)

    components = []
    for key, m in measures.items():
        spec = SPECS[key]
        share = spec.weight / included_weight if m.score is not None else 0.0
        components.append(
            Component(
                key=key, label=spec.label, weight=spec.weight, score=m.score,
                effective_weight=share, points=share * (m.score or 0.0), indicator=spec.indicator,
                value=m.value, value_display=m.display, target=spec.target, basis=spec.basis,
                explanation=m.explanation, excluded_reason=m.excluded_reason,
            )
        )  # fmt: skip

    notes = [f"{c.label} not scored: {c.excluded_reason}" for c in components if c.score is None]
    if not included_weight:
        return HealthScoreResult(twin.as_of, None, "N/A", "Not enough data", components, [], [],
                                 [], notes)  # fmt: skip

    score = sum(c.points for c in components)
    grade, label = grade_for(score)
    scored = [c for c in components if c.score is not None]
    strengths = [f"{c.label}: {c.explanation}" for c in scored if c.score >= STRONG]
    weaknesses = [f"{c.label}: {c.explanation}" for c in scored if c.score <= WEAK]
    improvable = sorted(
        (c for c in scored if c.score < STRONG),
        key=lambda c: c.effective_weight * (100 - c.score),
        reverse=True,
    )
    recommendations = [
        Recommendation(c.key, *_recommendation(c.key, twin), c.effective_weight * (100 - c.score))
        for c in improvable
    ]
    return HealthScoreResult(
        twin.as_of, score, grade, label, components, strengths, weaknesses, recommendations, notes
    )


# ---------------------------------------------------------------- change explanation

_CHANGE_PHRASES = {
    "savings": "savings ratio",
    "emergency_fund": "emergency-fund coverage",
    "debt": "debt-to-income ratio",
    "cash_flow": "months with positive cash flow",
    "investments": "investment rate",
    "goals": "affordable share of goal contributions",
    "spending": "discretionary share of income",
}


def explain_change(current: HealthScoreResult, previous: HealthScoreResult) -> dict | None:
    """Why the score moved between two results, attributed per component in score points."""
    if current.score is None or previous.score is None:
        return None
    delta = current.score - previous.score
    drivers = []
    for cur in current.components:
        prev = previous.component(cur.key)
        if cur.score is None or prev.score is None:
            continue
        drivers.append(
            {
                "component": cur.key,
                "label": cur.label,
                "points_change": round(cur.points - prev.points, 2),
                "from": prev.value_display,
                "to": cur.value_display,
            }
        )
    drivers.sort(key=lambda d: abs(d["points_change"]), reverse=True)

    if abs(delta) < 1:
        summary = (
            f"Your score is essentially unchanged since {previous.as_of.isoformat()} "
            f"({previous.score:.0f} → {current.score:.0f})."
        )
    else:
        direction = "rose" if delta > 0 else "fell"
        same_way = [d for d in drivers if d["points_change"] * delta > 0 and d["from"] != d["to"]]
        reasons = [
            f"your {_CHANGE_PHRASES[d['component']]} moved from {d['from']} to {d['to']} "
            f"({d['points_change']:+.1f} points)"
            for d in same_way[:2]
        ]
        summary = (
            f"Your score {direction} by {abs(delta):.0f} points since {previous.as_of.isoformat()} "
            f"({previous.score:.0f} → {current.score:.0f})"
        )
        summary += ", mainly because " + " and ".join(reasons) + "." if reasons else "."
    return {
        "previous_as_of": previous.as_of.isoformat(),
        "previous_score": round(previous.score, 1),
        "delta": round(delta, 1),
        "summary": summary,
        "drivers": drivers,
    }


def methodology() -> dict:
    return {
        "scale": "0-100, weighted mean of component scores",
        "grades": [{"min": floor, "grade": g, "label": label} for floor, g, label in GRADES],
        "thresholds": {"strong": STRONG, "weak": WEAK},
        "missing_data": "Components that cannot be measured are excluded and the remaining "
        "weights are renormalised to 100%.",
        "components": [
            {
                "key": key,
                "label": s.label,
                "weight": s.weight,
                "indicator": s.indicator,
                "formula": s.formula,
                "target": s.target,
                "basis": s.basis,
                "anchors": [{"value": x, "score": y} for x, y in s.anchors],
            }
            for key, s in SPECS.items()
        ],
    }
