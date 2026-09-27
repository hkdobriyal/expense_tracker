"""The alert engine end to end, including the brief's §76 scenario."""

from datetime import date

from app.models import AlertRule, NotificationDelivery
from app.services import alerts
from app.services.context import UserContext
from app.models import User

from .conftest import add_txn, category_id, make_account


def _food_budget_with_alert(api, spent_before: str):
    bank = make_account(api, opening="100000")
    food = category_id(api, "Food")
    groceries = category_id(api, "Groceries")
    budget = api.post("/api/budgets", json={"name": "Food", "category_id": food, "amount": "500", "period": "monthly"})
    if spent_before:
        add_txn(api, bank["id"], spent_before, "expense", "Earlier groceries", category_id=groceries)
    api.patch("/api/settings", json={"channels": {"email": True}})
    rule = api.post("/api/alerts/rules", json={"name": "Food 80%", "metric": "budget_usage", "params": {"budget_id": budget["id"]}, "operator": ">=", "threshold": "80", "channels": ["in_app", "email"]})
    return bank, groceries, budget, rule


def test_budget_alert_scenario_from_brief(api, db):
    # Food budget €500 (here ₹500), existing spending 390, new expense 20 → 410 = 82% → alert.
    bank, groceries, budget, rule = _food_budget_with_alert(api, "390")
    assert rule["fired_now"] == []  # 78% – below the threshold
    created = add_txn(api, bank["id"], "20", "expense", "Milk", category_id=groceries)
    assert created["alerts_triggered"] == ["Budget warning: Food"]

    budgets = api.get("/api/budgets")
    assert budgets[0]["spent"] == 41_000 and budgets[0]["usage_pct"] == 82.0

    inbox = api.get("/api/notifications")
    assert inbox["unread"] == 1
    assert inbox["items"][0]["message"] == "You have used 82% of your Food budget (₹410 of ₹500)."

    events = api.get("/api/alerts/events")
    budget_events = [e for e in events if e["metric"] == "budget_usage"]
    assert len(budget_events) == 1
    channels = {d["channel"]: d["status"] for d in budget_events[0]["deliveries"]}
    # SMTP is not configured in tests: the email is honestly marked "logged", not "sent".
    assert channels == {"in_app": "sent", "email": "logged"}

    # Cooldown: more spending in the same month must not re-send the same warning.
    add_txn(api, bank["id"], "30", "expense", "Bread", category_id=groceries)
    api.post("/api/alerts/evaluate")
    assert len([e for e in api.get("/api/alerts/events") if e["metric"] == "budget_usage"]) == 1


def test_budget_alert_fires_again_next_period(api, db):
    bank, groceries, budget, rule = _food_budget_with_alert(api, "450")
    assert len(rule["fired_now"]) == 1
    next_month = date(2030, 1, 15)
    add_txn(api, bank["id"], "450", "expense", "Next month", category_id=groceries, day=next_month)
    user = db.query(User).filter_by(email="me@example.com").one()
    ctx = UserContext.for_user(db, user, today=next_month)
    fired = alerts.evaluate_state_rules(db, ctx)
    db.commit()
    assert [e.title for e in fired] == ["Budget warning: Food"]


def test_low_balance_episode_resets_after_recovery(api):
    bank = make_account(api, opening="1500")
    api.post("/api/alerts/rules", json={"name": "Low", "metric": "account_balance", "params": {"account_id": bank["id"]}, "operator": "<", "threshold": "1000"})
    add_txn(api, bank["id"], "800", "expense", "Rent share")          # 700 → fires
    add_txn(api, bank["id"], "100", "expense", "Snacks")              # 600 → still low, no repeat
    add_txn(api, bank["id"], "5000", "income", "Salary")              # recovers
    add_txn(api, bank["id"], "5000", "expense", "Laptop")             # 600 → new episode, fires again
    low = [e for e in api.get("/api/alerts/events") if e["metric"] == "account_balance"]
    assert len(low) == 2


def test_large_transaction_event_and_rule_channels(api):
    bank = make_account(api, opening="100000")
    api.post("/api/alerts/rules", json={"name": "Big", "metric": "large_transaction", "operator": ">", "threshold": "500", "cooldown_policy": "every_event", "channels": ["in_app"]})
    add_txn(api, bank["id"], "850", "expense", "IKEA", merchant="IKEA")
    add_txn(api, bank["id"], "100", "expense", "Tea")
    add_txn(api, bank["id"], "900", "expense", "IKEA again", merchant="IKEA")
    msgs = [n["message"] for n in api.get("/api/notifications")["items"] if n["title"] == "Large transaction"]
    assert msgs == ["₹900 payment detected at IKEA.", "₹850 payment detected at IKEA."]


def test_cooldown_policy_limits_event_alerts(api):
    bank = make_account(api, opening="100000")
    api.post("/api/alerts/rules", json={"name": "Big", "metric": "large_transaction", "operator": ">", "threshold": "500", "cooldown_policy": "cooldown", "cooldown_minutes": 60})
    add_txn(api, bank["id"], "850", "expense", "A")
    add_txn(api, bank["id"], "950", "expense", "B")
    assert len([e for e in api.get("/api/alerts/events") if e["metric"] == "large_transaction"]) == 1


def test_bill_due_default_rule_and_disabled_channel(api):
    make_account(api)
    api.patch("/api/settings", json={"channels": {"in_app": False}})
    api.post("/api/bills", json={"name": "Electricity", "amount": "1800", "next_due_date": date.today().isoformat()})
    events = [e for e in api.get("/api/alerts/events") if e["metric"] == "bill_due_within"]
    assert len(events) == 1 and events[0]["title"] == "Bill due today: Electricity"
    assert api.get("/api/notifications")["unread"] == 0  # in-app switched off: history only


def test_failed_email_is_retried_then_marked_failed(api, db, monkeypatch):
    from app.services import notifications

    class Broken:
        name = "smtp"

        def send(self, destination, message):
            return notifications.DeliveryResult("failed", "smtp", "Connection refused")

    monkeypatch.setattr(notifications, "provider_for", lambda channel, db=None: Broken())
    bank, groceries, budget, rule = _food_budget_with_alert(api, "")
    add_txn(api, bank["id"], "450", "expense", "Big shop", category_id=groceries)
    delivery = db.query(NotificationDelivery).filter_by(channel="email").one()
    assert delivery.status == "failed" and "Connection refused" in delivery.error and delivery.attempts == 1


def test_rule_validation(api):
    api.post("/api/alerts/rules", json={"name": "x", "metric": "nope"}, expected=422)
    api.post("/api/alerts/rules", json={"name": "x", "metric": "budget_usage", "params": {"budget_id": 999}, "threshold": "80"}, expected=422)
    api.post("/api/alerts/rules", json={"name": "x", "metric": "category_spending", "threshold": "80"}, expected=422)
    assert any(m["key"] == "unusual_transaction" for m in api.get("/api/alerts/metrics"))


def test_default_rules_created_on_registration(api, db):
    names = {r.metric for r in db.query(AlertRule).all()}
    assert {"bill_due_within", "bill_overdue", "subscription_renewal", "sync_failed"} <= names
