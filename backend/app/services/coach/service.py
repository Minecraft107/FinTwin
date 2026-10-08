"""AI Financial Coach pipeline.

    question -> intent + entities -> backend calculations (twin, score, goals, risks,
    forecast, simulation) -> structured context -> knowledge retrieval (RAG)
    -> LLM (if configured) -> grounding check -> answer, else deterministic local answer

The LLM only explains; every number it may use is in the context it receives, and any
answer quoting a number that is not there is discarded in favour of the local answer.
"""

import json
import logging
import re

from flask import current_app
from pydantic import ValidationError

from app.extensions import db
from app.models import CoachConversation, CoachMessage, RiskAlert
from app.models.enums import AlertStatus, MessageRole
from app.repositories.user_data import load_user_data
from app.services.coach import grounding, local
from app.services.coach.context import CoachInputs, build_context
from app.services.coach.entities import extract
from app.services.coach.intent import detect
from app.services.coach.llm.base import CoachAnswer, LLMError
from app.services.coach.llm.prompts import SYSTEM_PROMPT, user_prompt
from app.services.coach.llm.providers import get_provider
from app.services.coach.rag import retrieve
from app.services.coach.scenario_parser import parse_scenario
from app.services.digital_twin.builder import build_twin
from app.services.digital_twin.service import anomaly_flags, scored
from app.services.financial.goal_planner import plan_goals
from app.services.financial.health_score import explain_change
from app.services.forecasting.service import forecast_cash_flow, forecast_expenses
from app.services.simulation.service import run_scenario
from app.utils.dates import add_months, month_end

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "FinTwin is a decision-support and educational tool, not a licensed financial advisor. "
    "Projections and simulations are estimates based on your data and stated assumptions."
)
# Extra words that steer retrieval toward the right knowledge for each intent.
RETRIEVAL_HINTS = {
    "affordability": "big purchase afford saving first",
    "what_if": "plan monthly surplus",
    "score_explanation": "health score components",
    "improve_health": "health score savings emergency fund",
    "overspending": "spending category drift subscriptions",
    "emergency_fund": "emergency fund months essential expenses",
    "debt": "debt EMI prepay loan",
    "goal_planning": "goal monthly saving priority",
    "out_of_scope": "diversification asset allocation SIP",
    "risk": "unusual duplicate charges",
}
SECTION_TITLES = [
    ("facts", "Your data"),
    ("calculations", "Calculations"),
    ("predictions", "Estimates and projections"),
    ("recommendations", "What you could do"),
    ("background", "Background"),
]


def _active_alerts(user_id: int) -> list[dict]:
    from app.services.analytics.anomalies import SEVERITY_RANK

    rows = db.session.scalars(
        db.select(RiskAlert).where(
            RiskAlert.user_id == user_id, RiskAlert.status == AlertStatus.ACTIVE
        )
    )
    rows = sorted(rows, key=lambda a: -SEVERITY_RANK[a.severity])
    return [
        {
            "type": a.type,
            "severity": a.severity.value,
            "title": a.title,
            "explanation": a.explanation,
            "recommended_action": a.recommended_action,
        }
        for a in rows
    ]


COMPARE_MONTHS = (3, 6, 1, 12)
_ASKS_DOWN = re.compile(
    r"\b(decrease|decreased|drop|dropped|fall|fell|fallen|lower|worse|down)\b", re.I
)
_ASKS_UP = re.compile(r"\b(increase|increased|rise|rose|higher|better|improved|up)\b", re.I)


def _score_change(data, twin, health, flags, question: str) -> dict | None:
    """Explain the score change. Default comparison: 3 months back. If the question asks why
    the score fell (or rose), use the nearest comparison window where it actually did; the
    answer always names the date it compares against, so this is never hidden."""
    if not twin.window_end or health.score is None:
        return None
    wanted = -1 if _ASKS_DOWN.search(question) else 1 if _ASKS_UP.search(question) else 0
    changes = []
    for months in COMPARE_MONTHS:
        previous = build_twin(data, month_end(add_months(twin.window_end.replace(day=1), -months)))
        if previous.window_months:
            change = explain_change(health, scored(previous, flags))
            if change:
                changes.append(change)
    if not changes:
        return None
    if wanted:
        matching = [c for c in changes if c["delta"] * wanted > 0]
        if matching:
            return matching[0]
    return changes[0]


def gather(user_id: int, question: str):
    """Intent, entities and every backend computation the question needs."""
    data = load_user_data(user_id)
    twin = build_twin(data)
    intent = detect(question)
    entities = extract(question, twin.goals)
    flags = anomaly_flags(data)
    health = scored(twin, flags)
    change = _score_change(data, twin, health, flags, question)
    inputs = CoachInputs(
        data=data,
        twin=twin,
        health=health,
        health_change=change,
        goal_plans=plan_goals(twin),
        alerts=_active_alerts(user_id),
    )
    if intent.name == "forecast":
        inputs.forecast = forecast_expenses(data, 3)
        inputs.cash_flow = forecast_cash_flow(data, 3)
    if intent.name in ("affordability", "what_if"):
        parsed = parse_scenario(question, entities, twin)
        if parsed:
            inputs.simulation = run_scenario(data, parsed.scenario)
            inputs.scenario_description = parsed.description
            inputs.scenario_assumptions = parsed.assumptions
    return intent, entities, inputs


def _llm_answer(provider, question, intent, context, knowledge) -> tuple[CoachAnswer | None, dict]:
    """Ask the LLM; return (answer or None, diagnostics). None means: use the local answer."""
    try:
        raw = provider.generate(SYSTEM_PROMPT, user_prompt(question, intent, context, knowledge))
        candidate = CoachAnswer.model_validate(json.loads(raw))
    except (LLMError, json.JSONDecodeError, ValidationError, TypeError) as e:
        logger.warning("LLM answer unusable (%s); using local answer", e.__class__.__name__)
        return None, {
            "fallback_reason": f"LLM unavailable or invalid reply ({e.__class__.__name__})"
        }
    allowed = grounding.allowed_numbers(context, knowledge, question)
    result = grounding.check(candidate.text(), allowed)
    diagnostics = {
        "grounding": {
            "checked": result.checked,
            "passed": result.passed,
            "unverified_numbers": result.unverified,
        }
    }
    if not result.passed:
        logger.warning("LLM answer failed grounding: %s", result.unverified)
        diagnostics["fallback_reason"] = "LLM answer contained numbers not found in your data"
        return None, diagnostics
    return candidate, diagnostics


def render(answer: CoachAnswer) -> str:
    parts = [answer.summary]
    for key, title in SECTION_TITLES:
        items = getattr(answer, key)
        if items:
            parts.append(f"**{title}**\n" + "\n".join(f"- {item}" for item in items))
    return "\n\n".join(parts)


def ask(user_id: int, question: str, conversation_id: int | None = None) -> dict:
    intent, entities, inputs = gather(user_id, question)
    context = build_context(intent.name, inputs)
    query = f"{question} {RETRIEVAL_HINTS.get(intent.name, '')}"
    hits = retrieve(query)
    knowledge = [
        {"source": f"{h.chunk.title} › {h.chunk.heading}", "text": h.chunk.text} for h in hits
    ]

    provider, reason = get_provider(current_app.config)
    diagnostics: dict = {"fallback_reason": reason} if reason else {}
    answer, provider_name = None, "local"
    if provider is not None:
        answer, diagnostics = _llm_answer(provider, question, intent.name, context, knowledge)
        provider_name = provider.name if answer else "local"
    if answer is None:
        answer = local.answer(intent.name, inputs, hits, entities)

    conversation = _conversation(user_id, conversation_id, question)
    db.session.add(
        CoachMessage(conversation_id=conversation.id, role=MessageRole.USER, content=question)
    )
    simulation = (
        None
        if not inputs.simulation
        else {
            "scenario": inputs.scenario_description,
            "changes": inputs.simulation["scenario"]["changes"],
            "risk_level": inputs.simulation["risk_level"],
            "impact": inputs.simulation["impact"],
            "assumptions": inputs.scenario_assumptions,
        }
    )
    sources = [
        {
            "doc": h.chunk.doc,
            "title": h.chunk.title,
            "heading": h.chunk.heading,
            "score": round(h.score, 3),
        }
        for h in hits
    ]
    structured = {
        "answer": answer.model_dump(),
        "sources": sources,
        "simulation": simulation,
        "context_sections": list(context),
        **diagnostics,
    }
    message = CoachMessage(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=render(answer),
        intent=intent.name,
        structured=structured,
        provider=provider_name,
    )
    db.session.add(message)
    db.session.commit()
    return {
        "conversation_id": conversation.id,
        "message_id": message.id,
        "intent": intent.name,
        "provider": provider_name,
        "answer": answer.model_dump(),
        "text": message.content,
        "sources": sources,
        "simulation": simulation,
        "context_sections": list(context),
        **diagnostics,
        "disclaimer": DISCLAIMER,
    }


def _conversation(user_id: int, conversation_id: int | None, question: str) -> CoachConversation:
    from app.repositories.base import get_owned

    if conversation_id is not None:
        return get_owned(CoachConversation, conversation_id, user_id)
    conversation = CoachConversation(user_id=user_id, title=question[:80])
    db.session.add(conversation)
    db.session.flush()
    return conversation
