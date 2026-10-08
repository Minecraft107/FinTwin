import io
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import FinancialSnapshot, User
from app.models.enums import SnapshotPeriod
from app.seed.demo import seed_demo
from app.utils.dates import add_months
from tests.conftest import ApiClient

TODAY = date.today()


def _month(offset: int, day: int = 5) -> str:
    """ISO date in the month `offset` months before the current one."""
    return add_months(TODAY.replace(day=1), -offset).replace(day=day).isoformat()


def _add(api, d, amount, txn_type="expense", description="DMART"):
    res = api.post(
        "/api/transactions",
        json={"date": d, "amount": amount, "type": txn_type, "description": description},
    )
    assert res.status_code == 201, res.get_json()


def _snapshots(period=None) -> list[FinancialSnapshot]:
    query = db.select(FinancialSnapshot)
    if period:
        query = query.where(FinancialSnapshot.period == period)
    return list(db.session.scalars(query.order_by(FinancialSnapshot.as_of)))


def test_new_user_twin_uses_declared_profile(api):
    api.put(
        "/api/financial-profile",
        json={"declared_monthly_income": 80_000, "monthly_essential_expenses": 30_000},
    )
    twin = api.get("/api/digital-twin").get_json()["data"]
    assert twin["monthly_income"] == 80_000
    assert twin["net_cash_flow"] == 50_000
    assert twin["sources"]["income"] == "declared"
    assert twin["window_months"] == 0


def test_twin_switches_to_observed_data(api):
    for offset in (1, 2):
        _add(api, _month(offset, 1), 90_000, "income", "SALARY ACME")
        _add(api, _month(offset), 30_000)
    twin = api.get("/api/digital-twin").get_json()["data"]
    assert twin["sources"]["income"] == "observed"
    assert twin["window_months"] == 2
    assert twin["monthly_income"] == 90_000
    assert twin["net_cash_flow"] == 60_000
    assert twin["expenses_by_category"] == {"Groceries": 30_000}


def test_writes_recalculate_snapshots(app, api):
    _add(api, _month(2), 1_000)
    _add(api, _month(1), 1_000)
    monthly = _snapshots(SnapshotPeriod.MONTHLY)
    assert len(monthly) == 2
    assert len(_snapshots(SnapshotPeriod.ON_CHANGE)) == 1

    # Deleting history removes the now-empty month's snapshot.
    txn_id = api.get("/api/transactions").get_json()["data"][-1]["id"]  # oldest
    api.delete(f"/api/transactions/{txn_id}")
    assert len(_snapshots(SnapshotPeriod.MONTHLY)) == 1


def test_profile_and_holdings_writes_recalculate(api):
    api.put("/api/financial-profile", json={"emergency_fund": 10_000})
    assert len(_snapshots(SnapshotPeriod.ON_CHANGE)) == 1
    api.post("/api/investments", json={"name": "FD", "asset_type": "fd", "current_value": 5_000})
    snap = _snapshots(SnapshotPeriod.ON_CHANGE)[0]
    db.session.refresh(snap)
    assert float(snap.investments_value) == 5_000


def test_preview_does_not_recalculate(api):
    api.post(
        "/api/transactions/import/preview",
        data={"file": (io.BytesIO(b"date,description,amount\n2026-01-01,X,-5\n"), "a.csv")},
        content_type="multipart/form-data",
    )
    assert _snapshots() == []


def test_recalculation_failure_does_not_fail_the_write(api, monkeypatch):
    import app.services.digital_twin.service as service

    def boom(*_args, **_kwargs):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(service, "recalculate", boom)
    _add(api, _month(1), 500)
    assert api.get("/api/transactions").get_json()["meta"]["total"] == 1


def test_history_backfills_lazily(api):
    _add(api, _month(3), 1_000)
    db.session.execute(db.delete(FinancialSnapshot))
    db.session.commit()
    history = api.get("/api/digital-twin/history").get_json()["data"]
    assert [h["as_of"][:7] for h in history] == [_month(m)[:7] for m in (3, 2, 1)]
    assert history[0]["expenses"] == 1_000


@pytest.mark.parametrize("as_of", ["yesterday", (TODAY + timedelta(days=1)).isoformat()])
def test_as_of_validation(api, as_of):
    assert api.get(f"/api/digital-twin?as_of={as_of}").status_code == 400


def test_twin_as_of_past_date(api):
    _add(api, _month(2), 1_000)
    _add(api, _month(1), 9_000)
    past = api.get(f"/api/digital-twin?as_of={_month(1, 1)}").get_json()["data"]
    assert past["monthly_expenses"] == 1_000  # only the older month existed then


# ---------------- analytics API ----------------


def test_analytics_endpoints(api):
    api.put(
        "/api/financial-profile",
        json={"opening_balance": 10_000, "opening_balance_date": _month(1, 1)},
    )
    _add(api, TODAY.isoformat(), 50_000, "income", "SALARY")
    _add(api, TODAY.isoformat(), 800, description="SWIGGY ORDER")
    overview = api.get("/api/analytics/overview?range=30d").get_json()
    assert overview["data"]["current"]["income"] == 50_000
    assert overview["meta"]["to"] == TODAY.isoformat()

    cats = api.get("/api/analytics/categories?range=30d").get_json()["data"]
    assert cats[0]["category"] == "Food & Dining" and cats[0]["share"] == 1.0

    trends = api.get("/api/analytics/trends?range=12m").get_json()
    assert trends["meta"]["granularity"] == "month"
    assert len(trends["data"]) == 13  # 12 months back to today spans 13 calendar months
    assert trends["data"][-1]["cash_balance"] == pytest.approx(10_000 + 50_000 - 800)
    assert trends["data"][0]["cash_balance"] == pytest.approx(10_000)  # before the opening date

    merchants = api.get("/api/analytics/merchants?range=30d&limit=5").get_json()["data"]
    assert merchants[0]["total"] == 800


@pytest.mark.parametrize(
    "query",
    [
        "/overview?range=2w",
        "/overview?from=2026-01-01",
        "/categories?from=2026-02-01&to=2026-01-01",
        "/trends?granularity=hour",
        "/merchants?limit=0",
        "/merchants?limit=abc",
        "/trends?from=bad&to=2026-01-01",
    ],
)
def test_analytics_validation(api, query):
    res = api.get(f"/api/analytics{query}")
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_analytics_require_auth(client):
    assert client.get("/api/analytics/overview").status_code == 401


# ---------------- the demo story holds ----------------


def test_demo_twin_tells_the_intended_story(app, client):
    seed_demo()
    user = db.session.scalar(db.select(User))
    res = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": app.config["DEMO_PASSWORD"]},
    )
    api = ApiClient(client, res.get_json()["data"]["access_token"])
    twin = api.get("/api/digital-twin").get_json()["data"]
    assert twin["window_months"] == 3 and twin["months_of_history"] >= 23
    assert 0.05 < twin["savings_ratio"] < 0.30  # squeezed by rising food delivery
    assert twin["emergency_months"] < 3  # the planted weakness
    assert 0.05 < twin["debt_to_income"] < 0.2
    assert set(twin["investment_allocation"]) == {"sip_equity", "ppf", "gold"}
    assert len(api.get("/api/digital-twin/history").get_json()["data"]) >= 23


def test_dashboard_aggregate(app, client):
    seed_demo()
    user = db.session.scalar(db.select(User))
    res = client.post(
        "/api/auth/login", json={"email": user.email, "password": app.config["DEMO_PASSWORD"]}
    )
    api = ApiClient(client, res.get_json()["data"]["access_token"])
    data = api.get("/api/dashboard").get_json()["data"]
    assert set(data) == {"twin", "health", "trends", "alerts", "goals", "forecast"}
    assert data["health"]["score"] == api.get("/api/health-score").get_json()["data"]["score"]
    assert len(data["trends"]) == 13
    assert data["alerts"][0]["severity"] in ("HIGH", "CRITICAL")
    assert data["forecast"]["status"] == "ok"
