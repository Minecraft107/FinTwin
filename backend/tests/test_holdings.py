import pytest

from app.services.financial.formulas import emi
from tests.conftest import register

LOAN = {
    "name": "Car loan",
    "loan_type": "car",
    "principal": 500_000,
    "annual_interest_rate": 0.09,
    "tenure_months": 60,
    "start_date": "2025-01-01",
}


def test_investment_crud(api):
    created = api.post(
        "/api/investments",
        json={"name": "Nifty SIP", "asset_type": "sip_equity", "monthly_contribution": 5000},
    )
    assert created.status_code == 201
    inv = created.get_json()["data"]
    updated = api.put(f"/api/investments/{inv['id']}", json={"current_value": 60_000})
    assert updated.get_json()["data"]["current_value"] == 60_000
    assert updated.get_json()["data"]["monthly_contribution"] == 5000
    assert len(api.get("/api/investments").get_json()["data"]) == 1
    assert api.delete(f"/api/investments/{inv['id']}").status_code == 204
    assert api.get("/api/investments").get_json()["data"] == []


def test_loan_defaults_emi_and_outstanding(api):
    loan = api.post("/api/loans", json=LOAN).get_json()["data"]
    assert loan["outstanding"] == 500_000
    assert loan["emi"] == pytest.approx(emi(500_000, 0.09, 60), abs=0.01)


def test_loan_outstanding_cannot_exceed_principal(api):
    res = api.post("/api/loans", json=LOAN | {"outstanding": 600_000})
    assert res.status_code == 400
    loan = api.post("/api/loans", json=LOAN).get_json()["data"]
    res = api.put(f"/api/loans/{loan['id']}", json={"principal": 100_000})  # now < outstanding
    assert res.status_code == 400
    assert api.get("/api/loans").get_json()["data"][0]["principal"] == 500_000  # rolled back


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Car", "target_amount": 0},
        {"name": "Car", "target_amount": 1000, "priority": 0},
        {"name": "Car", "target_amount": 1000, "status": "abandoned"},
        {"target_amount": 1000},
    ],
)
def test_goal_validation(api, body):
    assert api.post("/api/goals", json=body).status_code == 400


def test_goal_target_date_can_be_cleared(api):
    goal = api.post(
        "/api/goals", json={"name": "Car", "target_amount": 800_000, "target_date": "2028-10-01"}
    ).get_json()["data"]
    res = api.put(f"/api/goals/{goal['id']}", json={"target_date": None})
    assert res.get_json()["data"]["target_date"] is None
    assert res.get_json()["data"]["name"] == "Car"


@pytest.mark.parametrize("url", ["/api/investments", "/api/loans", "/api/goals"])
def test_holdings_are_private(client, api, url):
    bodies = {
        "/api/investments": {"name": "X", "asset_type": "fd"},
        "/api/loans": LOAN,
        "/api/goals": {"name": "X", "target_amount": 10},
    }
    item = api.post(url, json=bodies[url]).get_json()["data"]
    other = register(client, email="other@example.com")
    assert other.get(url).get_json()["data"] == []
    assert other.put(f"{url}/{item['id']}", json={"name": "hacked"}).status_code == 404
    assert other.delete(f"{url}/{item['id']}").status_code == 404
