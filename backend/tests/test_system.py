from sqlalchemy.exc import IntegrityError, OperationalError

from app.extensions import db


def test_health_ok(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["data"] == {"status": "ok", "database": "up", "environment": "testing"}
    assert body["meta"] == {}


def test_health_reports_database_down(client, monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(db.session, "execute", broken)
    res = client.get("/api/health")
    assert res.status_code == 503
    assert res.get_json()["data"]["database"] == "down"


def test_unknown_route_uses_error_envelope(client):
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404
    assert res.get_json()["error"]["code"] == "NOT_FOUND"


def test_method_not_allowed_uses_error_envelope(client):
    res = client.post("/api/health")
    assert res.status_code == 405
    assert res.get_json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_unhandled_db_error_returns_503(app, client):
    @app.get("/api/_boom")
    def boom():
        raise OperationalError("SELECT 1", {}, Exception("db gone"))

    res = client.get("/api/_boom")
    assert res.status_code == 503
    assert res.get_json()["error"]["code"] == "DB_UNAVAILABLE"


def test_cors_allows_frontend_origin(client):
    res = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert res.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"


def test_cors_rejects_other_origin(client):
    res = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "Access-Control-Allow-Origin" not in res.headers


def test_integrity_error_returns_409(app, client):
    @app.get("/api/_conflict")
    def conflict():
        raise IntegrityError("INSERT", {}, Exception("unique violation"))

    res = client.get("/api/_conflict")
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "CONFLICT"


def test_unexpected_exception_returns_500_envelope(app, client):
    @app.get("/api/_crash")
    def crash():
        raise RuntimeError("boom")

    res = client.get("/api/_crash")
    assert res.status_code == 500
    assert res.get_json()["error"] == {
        "code": "INTERNAL_ERROR",
        "message": "An unexpected error occurred.",
        "details": {},
    }
