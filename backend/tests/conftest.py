import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.seed.categories import ensure_categories


@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()
        ensure_categories()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


class ApiClient:
    """Test client that sends the JWT and unwraps the {data, meta} envelope."""

    def __init__(self, client, token: str):
        self.client = client
        self.headers = {"Authorization": f"Bearer {token}"}

    def _call(self, method: str, url: str, **kwargs):
        return getattr(self.client, method)(url, headers=self.headers, **kwargs)

    def get(self, url, **kw):
        return self._call("get", url, **kw)

    def post(self, url, **kw):
        return self._call("post", url, **kw)

    def put(self, url, **kw):
        return self._call("put", url, **kw)

    def delete(self, url, **kw):
        return self._call("delete", url, **kw)


def register(client, email: str = "user@example.com", password: str = "secret123") -> ApiClient:
    res = client.post(
        "/api/auth/register", json={"email": email, "password": password, "full_name": "Test User"}
    )
    assert res.status_code == 201, res.get_json()
    return ApiClient(client, res.get_json()["data"]["access_token"])


@pytest.fixture
def api(client) -> ApiClient:
    return register(client)


@pytest.fixture
def category_ids(app) -> dict[str, int]:
    from app.models import ExpenseCategory

    return {c.name: c.id for c in db.session.scalars(db.select(ExpenseCategory))}
