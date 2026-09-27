"""Password reset, email verification, remember-me, email/push delivery and the live event stream."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import account_tokens

from .conftest import PASSWORD, Api, make_account


def _capture(monkeypatch, kind):
    sent = []
    fn = "send_reset_email" if kind == "reset" else "send_verification_email"
    monkeypatch.setattr(account_tokens, fn, lambda email, name, raw: sent.append((email, raw)))
    return sent


def test_forgot_and_reset_password(api, monkeypatch):
    sent = _capture(monkeypatch, "reset")
    unknown = api.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    known = api.post("/api/auth/forgot-password", json={"email": "ME@example.com"})
    assert unknown["message"] == known["message"]  # no account enumeration
    assert len(sent) == 1 and sent[0][0] == "me@example.com"
    token = sent[0][1]

    api.post("/api/auth/reset-password", json={"token": token, "password": "weak"}, expected=422)
    api.post("/api/auth/reset-password", json={"token": token, "password": "BrandNewPass9"})
    api.get("/api/auth/me", expected=401)  # every session was signed out
    api.post("/api/auth/reset-password", json={"token": token, "password": "AnotherPass99"}, expected=400)  # single use
    api.post("/api/auth/login", json={"email": "me@example.com", "password": PASSWORD}, expected=401)
    data = api.post("/api/auth/login", json={"email": "me@example.com", "password": "BrandNewPass9"})
    assert data["user"]["email_verified"] is True  # resetting proves inbox access


def test_expired_or_bogus_reset_token(api):
    api.post("/api/auth/reset-password", json={"token": "x" * 40, "password": "BrandNewPass9"}, expected=400)


def test_email_verification(anon, monkeypatch):
    sent = _capture(monkeypatch, "verify")
    data = anon.post("/api/auth/register", json={"email": "new@example.com", "password": PASSWORD})
    assert data["user"]["email_verified"] is False and len(sent) == 1
    anon.csrf = data["csrf_token"]
    anon.post("/api/auth/verify-email", json={"token": sent[0][1]})
    assert anon.get("/api/auth/me")["user"]["email_verified"] is True


def test_remember_me_controls_cookie_lifetime(anon):
    anon.post("/api/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD, "remember": False})
        assert "Max-Age" not in r.headers["set-cookie"]
        r = client.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD, "remember": True})
        assert "Max-Age=1209600" in r.headers["set-cookie"]


def test_placeholder_smtp_is_reported_not_faked(api):
    result = api.post("/api/notifications/test-email")
    assert result["status"] == "logged" and "not configured" in result["error"]


def test_web_push_subscribe_send_and_prune(api, monkeypatch):
    import pywebpush

    key = api.get("/api/push/public-key")["public_key"]
    assert len(key) == 87  # 65-byte uncompressed P-256 point, base64url without padding
    calls = []

    def fake_webpush(subscription_info, data, **kw):
        calls.append((subscription_info["endpoint"], data))

    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)
    sub = {"endpoint": "https://push.example.test/abc", "keys": {"p256dh": "BEl6", "auth": "c2VjcmV0"}}
    api.post("/api/push/subscribe", json=sub)
    assert api.get("/api/settings")["settings"]["channels"]["push"] is True
    assert api.post("/api/push/test")["delivered"] == 1
    assert "Push notifications are working" in calls[0][1]

    # Alerts reach push too
    acc = make_account(api, opening="100000")
    api.post("/api/alerts/rules", json={"name": "Big", "metric": "large_transaction", "operator": ">", "threshold": "100", "channels": ["in_app", "push"], "cooldown_policy": "every_event"})
    api.post("/api/transactions", json={"account_id": acc["id"], "amount": "500", "description": "TV", "date": "2026-09-20"})
    event = next(e for e in api.get("/api/alerts/events") if e["metric"] == "large_transaction")
    assert {d["channel"]: d["status"] for d in event["deliveries"]}["push"] == "sent"

    class Gone(Exception):
        pass

    def gone(**kw):
        raise pywebpush.WebPushException("gone", response=type("R", (), {"status_code": 410})())

    monkeypatch.setattr(pywebpush, "webpush", lambda subscription_info, data, **kw: gone())
    api.post("/api/push/test", expected=422)
    assert api.get("/api/push/devices") == []


def test_event_stream_reports_unread(api):
    r = api.client.get("/api/events/stream?once=true")
    assert r.status_code == 200 and "event: unread" in r.text and '"unread": 0' in r.text
