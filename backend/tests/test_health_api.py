import pytest

from app.extensions import db
from app.models import FinancialHealthScore, User
from app.seed.demo import seed_demo
from tests.conftest import ApiClient


@pytest.fixture
def demo(app, client) -> ApiClient:
    seed_demo()
    user = db.session.scalar(db.select(User))
    res = client.post(
        "/api/auth/login", json={"email": user.email, "password": app.config["DEMO_PASSWORD"]}
    )
    return ApiClient(client, res.get_json()["data"]["access_token"])


def test_demo_score_is_explained(demo):
    data = demo.get("/api/health-score?compare_months=6").get_json()["data"]
    assert 50 <= data["score"] <= 80
    assert data["grade"] in ("B", "C")
    assert len(data["components"]) == 7
    assert sum(c["points"] for c in data["components"]) == pytest.approx(data["score"], abs=0.1)
    weak = {c["key"] for c in data["components"] if c["status"] == "weak"}
    assert "emergency_fund" in weak  # the planted weakness
    assert data["recommendations"][0]["action"]
    assert data["change"]["summary"].startswith("Your score")
    assert data["change"]["drivers"]


def test_score_history_persisted_per_month(demo):
    history = demo.get("/api/health-score/history").get_json()["data"]
    assert len(history) >= 23
    assert all(0 <= h["score"] <= 100 for h in history)
    assert set(history[-1]["components"]) == {
        "savings", "emergency_fund", "debt", "cash_flow", "investments", "goals", "spending"
    }  # fmt: skip


def test_compare_months_validation(demo):
    assert demo.get("/api/health-score?compare_months=0").status_code == 400
    assert demo.get("/api/health-score?compare_months=x").status_code == 400


def test_methodology(api):
    data = api.get("/api/health-score/methodology").get_json()["data"]
    assert sum(c["weight"] for c in data["components"]) == 100
    assert data["grades"][0] == {"min": 85, "grade": "A", "label": "Excellent"}


def test_new_user_without_data_has_no_score(api):
    data = api.get("/api/health-score").get_json()["data"]
    assert data["score"] is None and data["grade"] == "N/A"
    assert data["change"] is None


def test_profile_write_stores_score_for_declared_data(api):
    api.put(
        "/api/financial-profile",
        json={
            "declared_monthly_income": 100_000,
            "monthly_essential_expenses": 40_000,
            "emergency_fund": 120_000,
        },  # fmt: skip
    )
    row = db.session.scalar(db.select(FinancialHealthScore))
    assert row is not None and row.emergency_fund == pytest.approx(30 + 40 * (3 - 1) / 2)


def test_twin_includes_health_summary(demo):
    twin = demo.get("/api/digital-twin").get_json()["data"]
    score = demo.get("/api/health-score").get_json()["data"]["score"]
    assert twin["health_score"]["score"] == score
    assert set(twin["health_score"]["components"]) >= {"savings", "debt"}
