from datetime import date, timedelta

import pytest

from tests.conftest import register

URL = "/api/transactions"


def _create(api, **overrides):
    body = {"date": "2026-09-10", "amount": 450, "type": "expense", "description": "SWIGGY ORDER"}
    return api.post(URL, json=body | overrides)


def test_create_auto_categorizes(api):
    res = _create(api)
    assert res.status_code == 201
    data = res.get_json()["data"]
    assert data["category"]["name"] == "Food & Dining"
    assert data["category_source"] == "rule"
    assert data["amount"] == 450


def test_create_with_explicit_category(api, category_ids):
    res = _create(api, category_id=category_ids["Groceries"])
    data = res.get_json()["data"]
    assert data["category"]["name"] == "Groceries"
    assert data["category_source"] == "manual"


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": 0},
        {"amount": -5},
        {"type": "transfer"},
        {"description": ""},
        {"date": "not-a-date"},
        {"date": (date.today() + timedelta(days=1)).isoformat()},
        {"category_id": 9999},
    ],
)
def test_create_validation(api, overrides):
    assert _create(api, **overrides).status_code == 400


def test_income_cannot_use_expense_category(api, category_ids):
    res = _create(api, type="income", category_id=category_ids["Groceries"])
    assert res.status_code == 400
    assert "cannot be used for income" in res.get_json()["error"]["message"]


def test_list_filters_and_pagination(api, category_ids):
    _create(api, date="2026-07-01", description="DMART", category_id=category_ids["Groceries"])
    _create(api, date="2026-08-01", description="UBER TRIP")
    _create(api, date="2026-09-01", type="income", amount=90_000, description="SALARY ACME")

    def listing(query=""):
        body = api.get(f"{URL}{query}").get_json()
        return [t["description"] for t in body["data"]], body["meta"]

    names, meta = listing()
    assert names == ["SALARY ACME", "UBER TRIP", "DMART"]  # newest first
    assert meta["total"] == 3
    assert listing("?type=income")[0] == ["SALARY ACME"]
    assert listing("?from=2026-07-15&to=2026-08-31")[0] == ["UBER TRIP"]
    assert listing("?q=uber")[0] == ["UBER TRIP"]
    assert listing(f"?category_id={category_ids['Groceries']}")[0] == ["DMART"]
    names, meta = listing("?per_page=2&page=2")
    assert names == ["DMART"] and meta == {"page": 2, "per_page": 2, "total": 3}


@pytest.mark.parametrize("query", ["?from=yesterday", "?page=0", "?per_page=abc", "?type=refund"])
def test_list_rejects_bad_query(api, query):
    assert api.get(f"{URL}{query}").status_code == 400


def test_per_page_is_capped(api):
    assert api.get(f"{URL}?per_page=10000").get_json()["meta"]["per_page"] == 200


def test_manual_correction_is_remembered(api, category_ids):
    txn = _create(api, description="UPI/111/RAMESH STORES").get_json()["data"]
    assert txn["category"]["name"] == "Other"
    res = api.put(f"{URL}/{txn['id']}", json={"category_id": category_ids["Groceries"]})
    assert res.get_json()["data"]["category_source"] == "manual"

    later = _create(api, description="UPI/222/RAMESH STORES").get_json()["data"]
    assert later["category"]["name"] == "Groceries"
    assert later["category_source"] == "memory"


def test_update_fields(api):
    txn = _create(api).get_json()["data"]
    res = api.put(f"{URL}/{txn['id']}", json={"amount": 999.5, "is_recurring": True})
    data = res.get_json()["data"]
    assert data["amount"] == 999.5 and data["is_recurring"] is True
    assert data["description"] == "SWIGGY ORDER"


def test_changing_type_requires_compatible_category(api, category_ids):
    txn = _create(api).get_json()["data"]
    assert api.put(f"{URL}/{txn['id']}", json={"type": "income"}).status_code == 400
    res = api.put(
        f"{URL}/{txn['id']}", json={"type": "income", "category_id": category_ids["Other Income"]}
    )
    assert res.status_code == 200


def test_delete(api):
    txn = _create(api).get_json()["data"]
    assert api.delete(f"{URL}/{txn['id']}").status_code == 204
    assert api.delete(f"{URL}/{txn['id']}").status_code == 404


def test_users_cannot_see_or_touch_each_others_transactions(client, api):
    txn = _create(api).get_json()["data"]
    intruder = register(client, email="intruder@example.com")
    assert intruder.get(URL).get_json()["meta"]["total"] == 0
    assert intruder.put(f"{URL}/{txn['id']}", json={"amount": 1}).status_code == 404
    assert intruder.delete(f"{URL}/{txn['id']}").status_code == 404
    assert api.get(URL).get_json()["data"][0]["amount"] == 450


def test_categories_listed(api):
    data = api.get("/api/categories").get_json()["data"]
    assert {"name": "Groceries", "kind": "essential"}.items() <= next(
        c for c in data if c["name"] == "Groceries"
    ).items()
