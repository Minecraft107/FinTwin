import pytest

URL = "/api/financial-profile"


def test_partial_update_keeps_other_fields(api):
    api.put(URL, json={"declared_monthly_income": 100_000, "emergency_fund": 50_000})
    res = api.put(URL, json={"dependents": 2, "risk_tolerance": "high"})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["declared_monthly_income"] == 100_000
    assert data["emergency_fund"] == 50_000
    assert data["dependents"] == 2
    assert data["risk_tolerance"] == "high"


def test_profile_persists_across_requests(api):
    api.put(URL, json={"opening_balance": 25_000, "opening_balance_date": "2026-01-01"})
    data = api.get(URL).get_json()["data"]
    assert data["opening_balance"] == 25_000
    assert data["opening_balance_date"] == "2026-01-01"


@pytest.mark.parametrize(
    "body",
    [
        {"declared_monthly_income": -1},
        {"risk_tolerance": "yolo"},
        {"dependents": 50},
        {"salary": 100},
    ],
)
def test_invalid_profile_rejected(api, body):
    res = api.put(URL, json=body)
    assert res.status_code == 400


def test_profiles_are_isolated_per_user(client, api):
    from tests.conftest import register

    other = register(client, email="other@example.com")
    api.put(URL, json={"declared_monthly_income": 123_456})
    assert other.get(URL).get_json()["data"]["declared_monthly_income"] == 0
