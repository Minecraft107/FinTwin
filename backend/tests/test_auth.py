from datetime import timedelta

import pytest
from flask_jwt_extended import create_access_token

from tests.conftest import register

REGISTER = "/api/auth/register"
LOGIN = "/api/auth/login"
ME = "/api/auth/me"


def _register(client, **overrides):
    body = {"email": "new@example.com", "password": "secret123", "full_name": "New"} | overrides
    return client.post(REGISTER, json=body)


def test_register_returns_user_and_token(client):
    res = _register(client, email="  Mixed@Example.COM ")
    assert res.status_code == 201
    data = res.get_json()["data"]
    assert data["user"]["email"] == "mixed@example.com"
    assert "password_hash" not in data["user"]
    assert data["access_token"]


def test_register_creates_empty_financial_profile(client):
    api = register(client)
    res = api.get("/api/financial-profile")
    assert res.status_code == 200
    assert res.get_json()["data"]["declared_monthly_income"] == 0


def test_duplicate_email_conflict(client):
    _register(client)
    res = _register(client, email="NEW@example.com")
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short1"},
        {"password": "allletters"},
        {"password": "12345678"},
        {"email": "not-an-email"},
        {"full_name": ""},
        {"is_admin": True},  # unknown fields are rejected
    ],
)
def test_register_validation(client, overrides):
    res = _register(client, **overrides)
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_non_json_body_rejected(client):
    res = client.post(REGISTER, data="email=x", content_type="application/x-www-form-urlencoded")
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "INVALID_JSON"


def test_login_success_and_me(client):
    _register(client)
    res = client.post(LOGIN, json={"email": "NEW@example.com", "password": "secret123"})
    assert res.status_code == 200
    token = res.get_json()["data"]["access_token"]
    me = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.get_json()["data"]["email"] == "new@example.com"


@pytest.mark.parametrize(
    "email,password", [("new@example.com", "wrong-pass1"), ("nobody@example.com", "secret123")]
)
def test_login_failure_is_generic(client, email, password):
    _register(client)
    res = client.post(LOGIN, json={"email": email, "password": password})
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_protected_route_requires_token(client):
    res = client.get("/api/transactions")
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_garbage_token_rejected(client):
    res = client.get(ME, headers={"Authorization": "Bearer not.a.jwt"})
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "INVALID_TOKEN"


def test_expired_token_rejected(app, client):
    token = create_access_token(identity="1", expires_delta=timedelta(seconds=-1))
    res = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "TOKEN_EXPIRED"


def test_token_for_deleted_user_rejected(app, client):
    token = create_access_token(identity="999")
    res = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
