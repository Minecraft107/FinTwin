import json

import pytest

import app.services.coach.llm.providers as providers
import app.services.coach.service as coach_service
from app.extensions import db
from app.models import CoachMessage, User
from app.seed.demo import seed_demo
from app.services.coach.llm.base import LLMError, LLMProvider
from app.services.coach.llm.prompts import SYSTEM_PROMPT
from tests.conftest import ApiClient, register

CHAT = "/api/coach/chat"


@pytest.fixture
def demo(app, client) -> ApiClient:
    seed_demo()
    user = db.session.scalar(db.select(User))
    res = client.post(
        "/api/auth/login", json={"email": user.email, "password": app.config["DEMO_PASSWORD"]}
    )
    return ApiClient(client, res.get_json()["data"]["access_token"])


def ask(api, message, **extra):
    res = api.post(CHAT, json={"message": message, **extra})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


class FakeLLM(LLMProvider):
    name = "openai"

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def generate(self, system, user):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return self.reply


def use_llm(monkeypatch, fake):
    monkeypatch.setattr(coach_service, "get_provider", lambda config: (fake, None))
    return fake


# ---------------- local (default) mode on the demo ----------------


@pytest.mark.parametrize(
    "question,intent,sections",
    [
        ("Can I afford a ₹1,30,000 laptop?", "affordability", {"SIMULATION_RESULTS"}),
        (
            "Why did my financial health score decrease?",
            "score_explanation",
            {"FINANCIAL_HEALTH_SCORE"},
        ),
        ("Where am I overspending?", "overspending", {"RECENT_TRANSACTIONS"}),
        ("How much should I save each month for my car goal?", "goal_planning", {"GOALS"}),
        ("Why is my emergency fund weak?", "emergency_fund", {"FINANCIAL_HEALTH_SCORE"}),
        ("What happens if I increase my SIP by ₹5,000?", "what_if", {"SIMULATION_RESULTS"}),
        ("How can I improve my financial health?", "improve_health", {"FINANCIAL_HEALTH_SCORE"}),
        ("What will my expenses be next month?", "forecast", {"FORECAST"}),
        ("Any unusual transactions?", "risk", {"RISKS"}),
    ],
)
def test_local_answers_are_grounded_in_the_demo(demo, question, intent, sections):
    data = ask(demo, question)
    assert data["intent"] == intent and data["provider"] == "local"
    assert sections <= set(data["context_sections"])
    assert "CURRENT_FINANCIAL_STATE" in data["context_sections"]
    answer = data["answer"]
    assert answer["summary"]
    assert answer["facts"] or answer["calculations"] or answer["predictions"]
    assert "not a licensed financial advisor" in data["disclaimer"]


def test_affordability_runs_the_simulator(demo):
    data = ask(demo, "Can I afford a ₹1,30,000 laptop?")
    assert data["simulation"]["changes"][0] == {
        "type": "large_purchase", "amount": 130000.0, "date": None, "label": None,
        "financed_by_loan": False, "loan_annual_rate": 0.12, "loan_tenure_months": 24,
    }  # fmt: skip
    # The demo data is dated today, so the exact cash/goal split and risk level can vary.
    assert data["simulation"]["impact"]["net_worth_change"] == pytest.approx(-130_000)
    assert data["simulation"]["risk_level"] in ("LOW", "MEDIUM")
    assert f"risk level: {data['simulation']['risk_level']}" in data["answer"]["summary"]


def test_score_question_uses_a_window_where_it_actually_fell(demo):
    data = ask(demo, "Why did my health score decrease?")
    assert "fell" in data["answer"]["summary"]


def test_out_of_scope_refuses_product_advice(demo):
    data = ask(demo, "Which stock should I buy?")
    assert data["intent"] == "out_of_scope"
    assert "can't recommend specific stocks" in data["answer"]["summary"]
    assert any("SEBI-registered" in r for r in data["answer"]["recommendations"])


def test_concept_question_cites_the_knowledge_base(demo):
    data = ask(demo, "What is the 50/30/20 rule?")
    assert data["sources"][0]["doc"] == "budgeting-50-30-20"
    assert "50%" in data["answer"]["summary"]


# ---------------- LLM path and grounding fallback ----------------


def good_reply(summary: str) -> str:
    return json.dumps({"summary": summary, "facts": [], "calculations": [], "predictions": [],
                       "recommendations": [], "background": []})  # fmt: skip


def test_grounded_llm_answer_is_used(demo, monkeypatch):
    fake = use_llm(
        monkeypatch, FakeLLM(good_reply("Your emergency fund is ₹95,000, about 1.5 months."))
    )
    data = ask(demo, "Why is my emergency fund weak?")
    assert data["provider"] == "openai"
    assert data["grounding"] == {"checked": 2, "passed": True, "unverified_numbers": []}
    system, user = fake.calls[0]
    assert system == SYSTEM_PROMPT and "Never" in system
    payload = json.loads(user)
    assert payload["question"] == "Why is my emergency fund weak?"  # question passed as data
    assert payload["CONTEXT"]["CURRENT_FINANCIAL_STATE"]["emergency_fund"] == "₹95,000"


def test_invented_number_falls_back_to_local(demo, monkeypatch):
    use_llm(monkeypatch, FakeLLM(good_reply("Save ₹12,345 a month and you'll be fine.")))
    data = ask(demo, "Why is my emergency fund weak?")
    assert data["provider"] == "local"
    assert data["grounding"]["unverified_numbers"] == ["₹12,345"]
    assert "not found in your data" in data["fallback_reason"]
    assert "₹12,345" not in data["text"]


@pytest.mark.parametrize(
    "fake",
    [
        FakeLLM("not json at all"),
        FakeLLM(json.dumps({"facts": ["missing summary"]})),
        FakeLLM(error=LLMError("timeout")),
    ],
)
def test_unusable_llm_reply_falls_back(demo, monkeypatch, fake):
    use_llm(monkeypatch, fake)
    data = ask(demo, "How can I improve my financial health?")
    assert data["provider"] == "local" and data["answer"]["summary"]
    assert "LLM unavailable or invalid reply" in data["fallback_reason"]


def test_missing_api_key_uses_local(demo, app):
    app.config.update(LLM_PROVIDER="openai", OPENAI_API_KEY="")
    data = ask(demo, "Where am I overspending?")
    assert data["provider"] == "local"
    assert data["fallback_reason"] == "OPENAI_API_KEY is not set"


def test_provider_selection(app):
    assert providers.get_provider({"LLM_PROVIDER": "local"}) == (None, None)
    gemini, _ = providers.get_provider(
        {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "k", "GEMINI_MODEL": "m"}
    )
    assert isinstance(gemini, providers.GeminiProvider)


def test_gemini_request_keeps_key_out_of_url(monkeypatch):
    captured = {}

    def fake_post(url, headers, payload, timeout):
        captured.update(url=url, headers=headers, payload=payload)
        return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    monkeypatch.setattr(providers, "post_json", fake_post)
    providers.GeminiProvider("secret-key", "gemini-2.0-flash", 5).generate("sys", "user")
    assert "secret-key" not in captured["url"]
    assert captured["headers"] == {"x-goog-api-key": "secret-key"}
    assert captured["payload"]["generationConfig"]["responseMimeType"] == "application/json"


def test_openai_bad_shape_raises(monkeypatch):
    monkeypatch.setattr(providers, "post_json", lambda *a, **k: {"error": "nope"})
    with pytest.raises(LLMError):
        providers.OpenAIProvider("k", "m", 5).generate("s", "u")


# ---------------- conversations ----------------


def test_conversation_history(demo):
    first = ask(demo, "Where am I overspending?")
    cid = first["conversation_id"]
    second = ask(demo, "What is SIP?", conversation_id=cid)
    assert second["conversation_id"] == cid

    listing = demo.get("/api/coach/conversations").get_json()["data"]
    assert listing[0]["id"] == cid and listing[0]["messages"] == 4
    detail = demo.get(f"/api/coach/conversations/{cid}").get_json()["data"]
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert detail["messages"][1]["structured"]["answer"]["summary"]

    assert demo.delete(f"/api/coach/conversations/{cid}").status_code == 204
    assert db.session.scalar(db.select(db.func.count(CoachMessage.id))) == 0


def test_chat_validation_and_privacy(demo, client):
    assert demo.post(CHAT, json={"message": ""}).status_code == 400
    assert demo.post(CHAT, json={"message": "x" * 1001}).status_code == 400
    cid = ask(demo, "hello")["conversation_id"]
    other = register(client, email="other@example.com")
    assert other.post(CHAT, json={"message": "hi", "conversation_id": cid}).status_code == 404
    assert other.get(f"/api/coach/conversations/{cid}").status_code == 404


def test_new_user_without_data_gets_helpful_answers(api):
    data = ask(api, "Can I afford a ₹50,000 phone?")
    assert data["answer"]["summary"]
    assert ask(api, "Why did my score drop?")["answer"]["summary"]


# ---------------- HTTP helper (network faked) ----------------


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_post_json_success_and_failures(monkeypatch):
    import io
    import urllib.error
    import urllib.request

    from app.services.coach.llm.base import post_json

    sent = {}

    def ok_urlopen(request, timeout):
        sent.update(url=request.full_url, data=json.loads(request.data), timeout=timeout)
        return _Response(b'{"ok": true}')

    monkeypatch.setattr(urllib.request, "urlopen", ok_urlopen)
    assert post_json("https://example.test/x", {}, {"a": 1}, 7) == {"ok": True}
    assert sent == {"url": "https://example.test/x", "data": {"a": 1}, "timeout": 7}

    def http_error(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))

    monkeypatch.setattr(urllib.request, "urlopen", http_error)
    with pytest.raises(LLMError, match="HTTP 401"):
        post_json("https://example.test/x", {}, {}, 1)

    def timeout_error(request, timeout):
        raise TimeoutError()

    monkeypatch.setattr(urllib.request, "urlopen", timeout_error)
    with pytest.raises(LLMError, match="TimeoutError"):
        post_json("https://example.test/x", {}, {}, 1)
