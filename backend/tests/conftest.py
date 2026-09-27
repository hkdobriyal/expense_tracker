"""Test fixtures: every test gets a fresh SQLite database and an authenticated API client."""

from __future__ import annotations

import os
import tempfile
from datetime import date

import pytest

# Configure the app *before* importing it.
_TMP = tempfile.mkdtemp(prefix="ledgerly-tests-")
os.environ.update({
    "DATA_DIR": _TMP, "AUTO_MIGRATE": "false", "JOBS_INLINE": "true", "SMTP_HOST": "", "SMTP_USER": "", "SMTP_PASSWORD": "",
    "APP_URL": "http://testserver", "DEFAULT_TIMEZONE": "Asia/Kolkata", "LLM_ENABLED": "false", "ALLOW_REGISTRATION": "true",
    "APP_NAME": "Hisaab",
})

from fastapi.testclient import TestClient  # noqa: E402

from app import db as db_module  # noqa: E402
from app.db import Base, SessionLocal, init_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import rate_limiter  # noqa: E402

PASSWORD = "Sup3rSecretPass"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    engine = init_engine(f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    rate_limiter.reset()
    yield engine
    engine.dispose()
    db_module._engine = None


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


class Api:
    """Thin wrapper that sends the CSRF header automatically and raises on unexpected status codes."""

    def __init__(self, client: TestClient):
        self.client = client
        self.csrf = ""

    def _headers(self):
        return {"X-CSRF-Token": self.csrf} if self.csrf else {}

    def request(self, method: str, url: str, expected: int | tuple = (200, 201), **kwargs):
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        response = self.client.request(method, url, headers=headers, **kwargs)
        expected = (expected,) if isinstance(expected, int) else expected
        assert response.status_code in expected, f"{method} {url} -> {response.status_code}: {response.text}"
        return response.json() if response.headers.get("content-type", "").startswith("application/json") else response

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def put(self, url, **kw):
        return self.request("PUT", url, **kw)

    def patch(self, url, **kw):
        return self.request("PATCH", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


@pytest.fixture
def anon():
    with TestClient(app) as client:
        yield Api(client)


@pytest.fixture
def api():
    with TestClient(app) as client:
        a = Api(client)
        data = a.post("/api/auth/register", json={"email": "me@example.com", "password": PASSWORD, "display_name": "Me"})
        a.csrf = data["csrf_token"]
        a.user = data["user"]
        yield a


def category_id(api: Api, name: str, parent: str | None = None) -> int:
    cats = api.get("/api/categories")
    parent_id = next(c["id"] for c in cats if c["name"] == parent and c["parent_id"] is None) if parent else None
    return next(c["id"] for c in cats if c["name"] == name and (parent is None or c["parent_id"] == parent_id))


def make_account(api: Api, name="HDFC Savings", type="savings", opening="10000", currency="INR", **extra) -> dict:
    return api.post("/api/accounts", json={"name": name, "type": type, "opening_balance": opening, "currency": currency, **extra})


def add_txn(api: Api, account_id: int, amount, type="expense", description="Test", day: date | None = None, **extra) -> dict:
    return api.post("/api/transactions", json={
        "account_id": account_id, "amount": str(amount), "type": type, "description": description,
        "date": (day or date.today()).isoformat(), **extra,
    })
