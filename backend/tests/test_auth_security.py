from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import User, UserSettings
from app.security import hash_password

from .conftest import PASSWORD, Api, add_txn, make_account


def test_registration_open_by_default(anon):
    status = anon.get("/api/auth/status")
    assert status["has_account"] is False and status["registration_open"] is True and status["app_name"] == "Hisaab"
    anon.post("/api/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    assert anon.get("/api/auth/status")["registration_open"] is True
    anon.post("/api/auth/register", json={"email": "b@example.com", "password": PASSWORD})
    anon.post("/api/auth/register", json={"email": "B@example.com", "password": PASSWORD}, expected=409)


def test_registration_can_be_closed(anon, monkeypatch):
    from app.config import get_settings

    anon.post("/api/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    monkeypatch.setenv("ALLOW_REGISTRATION", "false")
    get_settings.cache_clear()
    try:
        assert anon.get("/api/auth/status")["registration_open"] is False
        anon.post("/api/auth/register", json={"email": "b@example.com", "password": PASSWORD}, expected=403)
    finally:
        monkeypatch.delenv("ALLOW_REGISTRATION")
        get_settings.cache_clear()


def test_weak_password_rejected(anon):
    anon.post("/api/auth/register", json={"email": "a@example.com", "password": "alllowercase1"}, expected=422)


def test_requires_login(anon):
    anon.get("/api/transactions", expected=401)
    anon.get("/api/dashboard", expected=401)


def test_login_logout_and_bad_password(api):
    api.post("/api/auth/logout")
    api.get("/api/auth/me", expected=401)
    api.post("/api/auth/login", json={"email": "me@example.com", "password": "WrongPassword1"}, expected=401)
    data = api.post("/api/auth/login", json={"email": "ME@example.com", "password": PASSWORD})
    api.csrf = data["csrf_token"]
    assert api.get("/api/auth/me")["user"]["email"] == "me@example.com"


def test_login_rate_limited(anon):
    anon.post("/api/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    for _ in range(5):
        anon.post("/api/auth/login", json={"email": "a@example.com", "password": "Nope12345678"}, expected=401)
    anon.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}, expected=429)


def test_csrf_required_for_writes(api):
    csrf, api.csrf = api.csrf, ""
    api.post("/api/accounts", json={"name": "X", "type": "cash"}, expected=403)
    api.csrf = "wrong"
    api.post("/api/accounts", json={"name": "X", "type": "cash"}, expected=403)
    api.csrf = csrf
    api.post("/api/accounts", json={"name": "X", "type": "cash"})


def test_users_cannot_see_each_others_data(api, db):
    acc = make_account(api)
    txn = add_txn(api, acc["id"], "250", description="Private")
    other = User(email="other@example.com", password_hash=hash_password(PASSWORD))
    db.add(other)
    db.flush()
    db.add(UserSettings(user_id=other.id))
    db.commit()
    with TestClient(app) as client:
        intruder = Api(client)
        intruder.csrf = intruder.post("/api/auth/login", json={"email": "other@example.com", "password": PASSWORD})["csrf_token"]
        assert intruder.get("/api/transactions")["total"] == 0
        intruder.get(f"/api/transactions/{txn['id']}", expected=404)
        intruder.delete(f"/api/transactions/{txn['id']}", expected=404)
        intruder.post("/api/transactions", json={"account_id": acc["id"], "amount": "1", "description": "x", "date": date.today().isoformat()}, expected=422)
        assert intruder.get("/api/accounts") == []
    assert api.get(f"/api/transactions/{txn['id']}")["description"] == "Private"


def test_security_headers_and_no_store(api):
    response = api.client.get("/api/dashboard")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_audit_log_never_contains_passwords(api):
    api.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "An0therStrongOne"})
    for entry in api.get("/api/audit-log"):
        assert "password" not in str(entry["details"]).lower() or entry["action"] == "auth.password_changed"
        assert PASSWORD not in str(entry)
