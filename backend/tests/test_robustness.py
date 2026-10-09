"""Edge-case sweep: every API route, hit with an empty account, a seeded account and junk
input, must answer with the JSON envelope and never a 5xx."""

import re
from datetime import date

import pytest

from app.seed.demo import seed_demo
from tests.conftest import ApiClient, register

JUNK_QUERY = (
    "?range=bogus&from=2026-13-45&to=yesterday&horizon=-1&limit=abc&as_of=notadate"
    "&status=weird&page=-3&per_page=100000&annual_return=9&compare_months=0&granularity=year"
)
JUNK_BODIES = [
    {},
    [],
    "not json",
    {"amount": "NaN", "date": "2026-02-30", "type": "loan", "category_id": -1},
    {"amount": 1e308, "target_amount": -5, "name": "x" * 10_000, "message": ""},
    {"type": "large_purchase", "amount": float("inf")},
    {"changes": [{"type": "new_loan", "principal": 1e15, "annual_interest_rate": 999}]},
    {"email": "a@b", "password": ""},
]


def api_routes(app) -> list[tuple[str, str]]:
    routes = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api"):
            continue
        url = re.sub(r"<(?:int:)?\w+>", "999999", rule.rule)
        routes += [(m, url) for m in sorted(rule.methods - {"HEAD", "OPTIONS"})]
    return routes


def call(api: ApiClient, method: str, url: str, body=None):
    kwargs = {}
    if method in ("POST", "PUT", "PATCH"):
        kwargs = {"data": body, "content_type": "text/plain"} if isinstance(body, str) else {
            "json": body}  # fmt: skip
    return api._call(method.lower(), url, **kwargs)


def assert_enveloped(res, label):
    assert res.status_code < 500, (label, res.status_code, res.get_data(as_text=True)[:300])
    if res.status_code != 204 and res.mimetype == "application/json":
        payload = res.get_json()
        assert ("data" in payload) != ("error" in payload), label


@pytest.fixture
def demo_api(client) -> ApiClient:
    seed_demo(today=date.today())
    res = client.post("/api/auth/demo")
    assert res.status_code == 200
    return ApiClient(client, res.get_json()["data"]["access_token"])


def test_every_get_route_works_for_an_empty_account(app, api):
    for method, url in api_routes(app):
        if method == "GET":
            assert_enveloped(call(api, method, url), url)
            assert_enveloped(call(api, method, url + JUNK_QUERY), url + " junk query")


def test_every_get_route_works_for_a_seeded_account(app, demo_api):
    for method, url in api_routes(app):
        if method == "GET":
            assert_enveloped(call(demo_api, method, url), url)
            assert_enveloped(call(demo_api, method, url + JUNK_QUERY), url + " junk query")


@pytest.mark.parametrize("body", JUNK_BODIES, ids=range(len(JUNK_BODIES)))
def test_junk_bodies_are_rejected_not_crashed(app, client, body):
    api = register(client)
    for method, url in api_routes(app):
        if method in ("POST", "PUT", "PATCH") and not url.startswith("/api/auth/"):
            assert_enveloped(call(api, method, url, body), f"{method} {url} {body!r:.60}")


def test_routes_require_a_token(app, client):
    open_routes = {"/api/health", "/api/auth/register", "/api/auth/login", "/api/auth/demo"}
    for method, url in api_routes(app):
        if url in open_routes:
            continue
        res = getattr(client, method.lower())(url)
        assert res.status_code == 401, (method, url, res.status_code)
