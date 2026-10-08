from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.extensions import db
from app.models import RiskAlert, User
from app.models.enums import Severity
from app.seed.demo import seed_demo
from app.services.analytics.anomalies import (
    abnormal_months,
    category_drift,
    detect_transaction_anomalies,
    recent_high_count,
)
from app.services.analytics.risk_service import Alert, anomaly_alerts, ratio_alerts, sync_alerts
from app.services.digital_twin.state import MonthFlow
from tests.conftest import ApiClient, register
from tests.test_health_score import twin
from tests.test_twin_builder import frame

AS_OF = date(2026, 10, 8)


def groceries(n: int, outlier: float | None = None, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = AS_OF - timedelta(days=n * 3)
    rows = [((start + timedelta(days=3 * i)).isoformat(), float(round(rng.normal(2_000, 150))),
             "Groceries") for i in range(n)]  # fmt: skip
    if outlier:
        rows.append(((AS_OF - timedelta(days=1)).isoformat(), outlier, "Groceries"))
    df = frame(rows)
    df["id"] = range(len(df))
    return df


# ---------------- transaction level ----------------


def test_rule_flags_outlier_without_forest_on_small_history():
    flags = detect_transaction_anomalies(groceries(30, outlier=20_000), AS_OF)
    assert len(flags) == 1
    f = flags[0]
    assert f.amount == 20_000 and f.by_rule and not f.by_forest
    assert f.severity == Severity.MEDIUM
    assert f.category_median == pytest.approx(2_000, rel=0.1)


def test_rule_and_forest_agree_on_large_history():
    flags = detect_transaction_anomalies(groceries(80, outlier=20_000), AS_OF)
    outlier = next(f for f in flags if f.amount == 20_000)
    assert outlier.by_rule and outlier.by_forest
    assert outlier.severity == Severity.HIGH
    assert all(f.severity == Severity.LOW for f in flags if f is not outlier)


def test_critical_when_half_of_monthly_income():
    flags = detect_transaction_anomalies(
        groceries(80, outlier=60_000), AS_OF, monthly_income=100_000
    )
    assert next(f for f in flags if f.amount == 60_000).severity == Severity.CRITICAL


def test_small_categories_are_not_judged_by_the_rule():
    df = groceries(5, outlier=20_000)  # 6 rows < MIN_CATEGORY_TXNS
    assert detect_transaction_anomalies(df, AS_OF) == []


def test_duplicates_flag_only_the_repeat():
    df = groceries(20)
    dupes = frame([("2026-10-01", 3_499, "Shopping"), ("2026-10-01", 3_499, "Shopping")])
    dupes["id"] = [100, 101]
    flags = detect_transaction_anomalies(pd.concat([df, dupes], ignore_index=True), AS_OF)
    assert [(f.transaction_id, f.duplicate) for f in flags] == [(101, True)]


def test_future_and_non_spending_rows_ignored():
    df = groceries(20)
    extra = frame([("2026-12-01", 90_000, "Groceries"), ("2026-10-02", 90_000, "EMI/Debt")])
    extra["id"] = [200, 201]
    assert detect_transaction_anomalies(pd.concat([df, extra]), AS_OF) == []


def test_recent_high_count_window():
    flags = detect_transaction_anomalies(groceries(80, outlier=20_000), AS_OF)
    assert recent_high_count(flags, AS_OF) == 1
    assert recent_high_count(flags, AS_OF + timedelta(days=40)) == 0
    assert recent_high_count(flags, AS_OF - timedelta(days=5)) == 0


# ---------------- month level ----------------


def months(values: dict[str, list[float]]) -> pd.DataFrame:
    n = len(next(iter(values.values())))
    return pd.DataFrame(values, index=pd.period_range("2026-01", periods=n, freq="M"))


def test_abnormal_month_detected():
    m = months({"Shopping": [10_000, 11_000, 9_000, 10_500, 9_500, 10_000, 30_000]})
    [(month, z)] = abnormal_months(m)
    assert str(month) == "2026-07" and z > 3


def test_seasonal_spike_repeating_last_year_is_not_abnormal():
    year = [10_000.0] * 9 + [30_000, 10_000, 10_000]  # October spike...
    m = months({"Shopping": year + year[:10]})  # ...and again the next October
    flagged = [str(month) for month, _ in abnormal_months(m)]
    assert "2026-10" in flagged and "2027-10" not in flagged


def test_drift_trend_and_spike():
    m = months({
        "Food & Dining": [5_000, 5_000, 5_000, 9_000, 9_500, 10_000],  # sustained trend
        "Shopping": [4_000, 4_000, 4_000, 4_000, 4_000, 9_000],  # last-month spike
        "Groceries": [8_000, 8_000, 8_000, 8_000, 8_000, 9_000],  # +12%: ignored
        "Personal Care": [100, 100, 100, 100, 100, 1_000],  # +900% but < ₹2,000: ignored
    })  # fmt: skip
    found = {d.category: d for d in category_drift(m)}
    assert set(found) == {"Food & Dining", "Shopping"}
    assert (
        found["Food & Dining"].kind == "trend" and found["Food & Dining"].severity == Severity.HIGH
    )
    assert found["Shopping"].kind == "spike" and found["Shopping"].change == pytest.approx(1.25)


# ---------------- ratio rules ----------------


def test_healthy_twin_has_no_ratio_alerts():
    assert ratio_alerts(twin(cash_balance=500_000.0)) == []


@pytest.mark.parametrize(
    "overrides,alert_type,severity",
    [
        ({"savings_ratio": 0.05}, "low_savings", Severity.MEDIUM),
        ({"savings_ratio": -0.1}, "low_savings", Severity.HIGH),
        ({"debt_to_income": 0.40, "debt_payments": 40_000.0}, "high_debt", Severity.HIGH),
        ({"debt_to_income": 0.55, "debt_payments": 55_000.0}, "high_debt", Severity.CRITICAL),
        ({"emergency_months": 2.0}, "emergency_fund_shortage", Severity.MEDIUM),
        ({"emergency_months": 0.5}, "emergency_fund_shortage", Severity.HIGH),
        ({"cash_balance": 10_000.0}, "low_cash_buffer", Severity.HIGH),
        ({"cash_balance": -1.0}, "low_cash_buffer", Severity.CRITICAL),
    ],
)
def test_ratio_rules(overrides, alert_type, severity):
    alerts = ratio_alerts(twin(**({"cash_balance": 500_000.0} | overrides)))
    assert [(a.type, a.severity) for a in alerts] == [(alert_type, severity)]


def test_repeated_negative_cash_flow():
    bad = [MonthFlow(f"2026-0{m}", 50_000, 40_000, 20_000, 0, 0) for m in (7, 8)]
    good = MonthFlow("2026-09", 100_000, 40_000, 10_000, 0, 0)
    alerts = ratio_alerts(twin(cash_balance=500_000.0, recent_months=[*bad, good]))
    assert [a.type for a in alerts] == ["negative_cash_flow"]
    assert "2026-07, 2026-08" in alerts[0].explanation


def test_old_and_low_anomalies_are_not_alerts():
    flags = detect_transaction_anomalies(groceries(80, outlier=20_000), AS_OF)
    assert len(anomaly_alerts(flags, AS_OF)) == 1  # LOW forest-only flags excluded
    assert anomaly_alerts(flags, AS_OF + timedelta(days=120)) == []


# ---------------- persistence ----------------


def test_sync_keeps_dismissals_and_removes_resolved(app, client):
    register(client)
    user_id = db.session.scalar(db.select(User.id))
    a = Alert("high_debt", Severity.HIGH, "t", "e", "debt_to_income", 0.4, "r", "debt")
    b = Alert("low_savings", Severity.MEDIUM, "t", "e", "savings_ratio", 0.05, "r", "savings")
    sync_alerts(user_id, [a, b])
    row = db.session.scalar(db.select(RiskAlert).where(RiskAlert.type == "high_debt"))
    row.status = "dismissed"
    db.session.commit()
    worse = replace(a, severity=Severity.CRITICAL)
    sync_alerts(user_id, [worse])  # savings resolved, debt worsened
    rows = db.session.scalars(db.select(RiskAlert)).all()
    assert [(r.type, r.severity, r.status) for r in rows] == [
        ("high_debt", Severity.CRITICAL, "dismissed")
    ]


# ---------------- API ----------------


@pytest.fixture
def demo(app, client) -> ApiClient:
    seed_demo()
    user = db.session.scalar(db.select(User))
    res = client.post(
        "/api/auth/login", json={"email": user.email, "password": app.config["DEMO_PASSWORD"]}
    )
    return ApiClient(client, res.get_json()["data"]["access_token"])


def test_demo_risks_tell_the_story(demo):
    body = demo.get("/api/risks").get_json()
    types = [a["type"] for a in body["data"]]
    assert "category_spending_increase" in types
    assert "emergency_fund_shortage" in types
    assert "duplicate_charge" in types
    assert body["data"][0]["severity"] in ("HIGH", "CRITICAL")  # most severe first
    assert sum(body["meta"]["counts"].values()) == len(types)


def test_dismiss_survives_rescan(demo):
    alert = demo.get("/api/risks").get_json()["data"][0]
    res = demo.client.patch(
        f"/api/risks/{alert['id']}", json={"status": "dismissed"}, headers=demo.headers
    )
    assert res.get_json()["data"]["status"] == "dismissed"
    demo.post("/api/risks/scan")
    active = {a["id"] for a in demo.get("/api/risks").get_json()["data"]}
    dismissed = {a["id"] for a in demo.get("/api/risks?status=dismissed").get_json()["data"]}
    assert alert["id"] not in active and alert["id"] in dismissed


def test_risk_validation_and_privacy(demo, client):
    assert demo.get("/api/risks?status=open").status_code == 400
    alert_id = demo.get("/api/risks").get_json()["data"][0]["id"]
    bad = demo.client.patch(f"/api/risks/{alert_id}", json={"status": "gone"}, headers=demo.headers)
    assert bad.status_code == 400
    other = register(client, email="other@example.com")
    res = other.client.patch(
        f"/api/risks/{alert_id}", json={"status": "dismissed"}, headers=other.headers
    )
    assert res.status_code == 404


def test_writes_trigger_risk_scan(api):
    api.put("/api/financial-profile", json={"declared_monthly_income": 50_000,
                                            "monthly_essential_expenses": 40_000})  # fmt: skip
    types = {a["type"] for a in api.get("/api/risks").get_json()["data"]}
    assert "emergency_fund_shortage" in types  # 0 months of cover
