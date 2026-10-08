"""Question understanding: intents, entities, scenario parsing, retrieval, grounding."""

import pytest

from app.services.coach import grounding
from app.services.coach.entities import extract, parse_amounts, parse_months, parse_percents
from app.services.coach.intent import INTENTS, detect
from app.services.coach.rag import load_chunks, retrieve
from app.services.coach.scenario_parser import DEFAULT_LOAN_RATE, parse_scenario
from tests.test_health_score import goal, twin

# ---------------- intents ----------------


@pytest.mark.parametrize(
    "question,intent",
    [
        ("Can I afford this laptop for ₹1,30,000?", "affordability"),
        ("Should I buy a car worth 8 lakh?", "affordability"),
        ("Why did my financial health score decrease?", "score_explanation"),
        ("Where am I overspending?", "overspending"),
        ("How much should I save each month for my car goal?", "goal_planning"),
        ("Why is my emergency fund weak?", "emergency_fund"),
        ("What happens if I increase my SIP by 5000?", "what_if"),
        ("What happens if I take a 5 lakh loan?", "what_if"),
        ("What if my income decreases by 20%?", "what_if"),
        ("What happens if my monthly expenses increase by ₹10,000?", "what_if"),
        ("What if I save ₹15,000 more every month?", "what_if"),
        ("What happens if I delay my car goal by 6 months?", "what_if"),
        ("How can I improve my financial health?", "improve_health"),
        ("What will my expenses be next month?", "forecast"),
        ("Are there any unusual transactions?", "risk"),
        ("Should I prepay my education loan?", "debt"),
        ("Which stock should I buy?", "out_of_scope"),
        ("Is bitcoin a good investment?", "out_of_scope"),
        ("What is SIP?", "concept_question"),
        ("hello", "greeting"),
    ],
)
def test_intents(question, intent):
    assert detect(question).name == intent


def test_every_intent_is_reachable_and_scores_exposed():
    result = detect("What happens if I take a loan?")
    assert set(result.scores) | {"concept_question"} == set(INTENTS)
    assert result.scores["what_if"] > result.scores["debt"]


# ---------------- entities ----------------


@pytest.mark.parametrize(
    "text,amounts",
    [
        ("₹1,30,000 laptop", [130_000]),
        ("1.3 lakh", [130_000]),
        ("5L loan", [500_000]),
        ("a 2 crore house", [20_000_000]),
        ("SIP of 15k", [15_000]),
        ("Rs. 50,000 and INR 2500", [50_000, 2_500]),
        ("10000 rupees", [10_000]),
        ("in 2027 for 6 months at 9%", []),  # years, durations and rates are not money
        ("my 3 goals", []),
    ],
)
def test_amounts(text, amounts):
    assert parse_amounts(text) == amounts


def test_percents_and_durations():
    assert parse_percents("cut by 20% then 12.5 percent") == [20, 12.5]
    assert parse_months("for 6 months or 2 years or 1.5 yrs") == [6, 24, 18]


def test_goal_matching():
    goals = [goal(1, 1), goal(2, 2)]
    goals[0] = goals[0].__class__(**{**goals[0].__dict__, "name": "Buy a car"})
    goals[1] = goals[1].__class__(**{**goals[1].__dict__, "name": "Europe trip"})
    assert extract("save for my car", goals).goal_ids == [1]
    assert extract("the europe TRIP goal", goals).goal_ids == [2]
    assert extract("buy a goal", goals).goal_ids == []  # stop-words only


# ---------------- scenario parsing ----------------


def parse(question: str, **twin_overrides):
    t = twin(**twin_overrides)
    return parse_scenario(question, extract(question, t.goals), t)


def change(question: str, **twin_overrides) -> dict:
    parsed = parse(question, **twin_overrides)
    assert parsed is not None, question
    return parsed.scenario.changes[0].model_dump()


def test_purchase():
    c = change("Can I afford a ₹1,30,000 laptop?")
    assert c["type"] == "large_purchase" and c["amount"] == 130_000 and not c["financed_by_loan"]


def test_financed_purchase_with_assumed_rate():
    parsed = parse("Should I buy a car for 8 lakh on EMI for 3 years?")
    c = parsed.scenario.changes[0]
    assert c.financed_by_loan and c.loan_tenure_months == 36
    assert c.loan_annual_rate == DEFAULT_LOAN_RATE
    assert any("interest rate assumed" in a for a in parsed.assumptions)


def test_loan_with_rate_and_tenure():
    c = change("What if I take a 5 lakh loan at 9% for 4 years?")
    assert (c["type"], c["principal"], c["annual_rate"], c["tenure_months"]) == (
        "new_loan",
        500_000,
        0.09,
        48,
    )


@pytest.mark.parametrize(
    "question,expected",
    [
        ("What if my income decreases by 20%?", {"type": "income_change", "pct": -20}),
        ("What if I get a 10% salary hike?", {"type": "income_change", "pct": 10}),
        ("What if I increase my SIP by ₹5,000?", {"type": "sip_change", "amount": 5_000}),
        ("What if I reduce my SIP by 2k?", {"type": "sip_change", "amount": -2_000}),
        (
            "What if my rent increases by ₹10,000?",
            {"type": "expense_change", "amount": 10_000, "kind": "essential"},
        ),
        (
            "What if my expenses drop by 15%?",
            {"type": "expense_change", "pct": -15, "kind": "discretionary"},
        ),
        ("What if I save ₹15,000 more every month?", {"type": "extra_savings", "amount": 15_000}),
        ("What if I get a bonus of 1 lakh?", {"type": "one_time_income", "amount": 100_000}),
    ],
)
def test_change_types(question, expected):
    c = change(question)
    assert {k: c[k] for k in expected} == expected


def test_stop_sip_uses_current_contribution():
    assert change("What if I stop my SIP?", investment_contributions=12_000)["amount"] == -12_000


def test_job_loss_defaults_to_six_months():
    parsed = parse("What happens if I lose my job?")
    c = parsed.scenario.changes[0]
    assert (c.pct, c.duration_months) == (-100, 6)
    assert parsed.assumptions


def test_goal_delay():
    goals = [goal(7, 1)]
    goals[0] = goals[0].__class__(**{**goals[0].__dict__, "name": "Buy a car"})
    c = change("What if I delay my car goal by 9 months?", goals=goals)
    assert c == {"type": "goal_delay", "goal_id": 7, "months": 9}


def test_unparseable_returns_none():
    assert parse("What if things get better?") is None
    assert parse("Can I afford this laptop?") is None  # no amount


# ---------------- retrieval ----------------

RETRIEVAL_SET = [
    ("how much emergency fund should I keep", "emergency-fund"),
    ("rainy day savings for job loss", "emergency-fund"),
    ("what is a good savings ratio", "savings-and-cash-flow"),
    ("how is EMI calculated", "debt-and-emis"),
    ("should I prepay my loan", "debt-and-emis"),
    ("what is the 50/30/20 rule", "budgeting-50-30-20"),
    ("needs versus wants", "budgeting-50-30-20"),
    ("what is SIP", "sip-and-compounding"),
    ("how does compounding work", "sip-and-compounding"),
    ("diversify between gold and fixed deposits", "asset-allocation"),
    ("how much to save for my car goal", "goal-planning"),
    ("do I need term insurance", "insurance-basics"),
    ("how to improve CIBIL score", "credit-score"),
    ("what is inflation rule of 72", "inflation"),
    ("can I afford a new laptop", "big-purchases"),
    ("zero cost EMI offer", "big-purchases"),
    ("too many subscriptions", "spending-patterns"),
    ("why did my health score drop", "health-score"),
    ("food delivery spending keeps increasing", "spending-patterns"),
    ("PPF lock-in period", "asset-allocation"),
]


def test_knowledge_base_chunks_are_clean():
    chunks = load_chunks()
    assert len({c.doc for c in chunks}) == 13 and len(chunks) > 40
    assert not any(c.text.startswith("- ") or " - " in c.text[:3] for c in chunks)


def test_retrieval_quality():
    top1 = sum(retrieve(q)[0].chunk.doc == doc for q, doc in RETRIEVAL_SET if retrieve(q))
    top3 = sum(doc in [h.chunk.doc for h in retrieve(q)] for q, doc in RETRIEVAL_SET)
    assert top3 == len(RETRIEVAL_SET)
    assert top1 >= 0.9 * len(RETRIEVAL_SET)


def test_off_topic_and_missing_knowledge_base(tmp_path):
    assert retrieve("best cricket team in the world") == []
    assert retrieve("xyzzy") == []
    assert retrieve("emergency fund", directory=tmp_path / "missing") == []


def test_index_rebuilds_when_documents_change(tmp_path):
    (tmp_path / "a.md").write_text(
        "# A\n\n## Tea\nMasala chai is a spiced tea.\n", encoding="utf-8"
    )
    (tmp_path / "b.md").write_text("# B\n\n## Coffee\nFilter coffee is strong.\n", encoding="utf-8")
    assert retrieve("chai", directory=tmp_path)[0].chunk.doc == "a"
    (tmp_path / "c.md").write_text("# C\n\n## Lassi\nLassi is a yoghurt drink.\n", encoding="utf-8")
    assert retrieve("lassi yoghurt", directory=tmp_path)[0].chunk.doc == "c"


# ---------------- grounding ----------------


def test_number_extraction():
    found = {
        (v, k)
        for v, k, _ in grounding.numbers("₹1,30,000 or 1.3 lakh, 16.8%, 17 months, on 2027-01-15")
    }
    assert found == {(130_000, "money"), (130_000, "money"), (16.8, "pct"), (17, "plain")}


def test_grounding_accepts_context_numbers_and_rounding():
    allowed = grounding.allowed_numbers(
        {"cash": "₹2,26,814", "ratio": "16.8%", "months": "17 month(s)"}
    )
    ok = grounding.check(
        "You have ₹2,26,814 (about ₹2.27 lakh), save 16.8% and need 17 months.", allowed
    )
    assert ok.passed and ok.checked == 4


def test_grounding_rejects_invented_or_calculated_numbers():
    allowed = grounding.allowed_numbers({"surplus": "₹7,720"})
    result = grounding.check(
        "Your surplus is ₹7,720, so in a year you save ₹92,640 and 18% more.", allowed
    )
    assert not result.passed
    assert result.unverified == ["₹92,640", "18%"]


def test_grounding_ignores_small_counts_and_years():
    assert grounding.check("Keep 3 to 6 months in 2026.", []).passed


def test_grounding_checks_small_decimals():
    assert not grounding.check(
        "It covers 1.8 months.", grounding.allowed_numbers("1.5 months")
    ).passed
    assert grounding.check("It covers 1.5 months.", grounding.allowed_numbers("1.5 months")).passed
