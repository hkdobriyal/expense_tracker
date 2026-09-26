"""Bills, subscriptions, goals, recurring, reports, backup and migrations."""

from datetime import date, timedelta

from app.migrations import upgrade_database
from app.services.periods import add_months

from .conftest import add_txn, category_id, make_account


def test_pay_bill_creates_expense_and_rolls_due_date(api):
    acc = make_account(api)
    due = date.today() + timedelta(days=2)
    bill = api.post("/api/bills", json={"name": "Electricity", "provider": "BESCOM", "amount": "1850", "next_due_date": due.isoformat(), "account_id": acc["id"], "category_id": category_id(api, "Electricity")})
    assert bill["status"] == "due_soon"
    paid = api.post(f"/api/bills/{bill['id']}/pay", json={"amount": "1920.40"})
    assert paid["bill"]["next_due_date"] == add_months(due, 1).isoformat()
    txn = api.get(f"/api/transactions/{paid['transaction_id']}")
    assert (txn["amount_minor"], txn["category"], txn["source"]) == (192_040, "Electricity", "bill")
    once = api.post("/api/bills", json={"name": "Visa fee", "amount": "500", "frequency": "once", "next_due_date": date.today().isoformat(), "account_id": acc["id"]})
    api.post(f"/api/bills/{once['id']}/pay", json={})
    assert all(b["id"] != once["id"] for b in api.get("/api/bills"))


def test_subscription_equivalents_detection_and_price_change(api):
    acc = make_account(api, opening="50000")
    today = date.today()
    for months_ago in (3, 2, 1):
        add_txn(api, acc["id"], "649", "expense", "NETFLIX.COM", merchant="Netflix", day=add_months(today, -months_ago))
    detected = api.get("/api/subscriptions/detected")
    assert [(d["name"], d["frequency"], d["amount_minor"]) for d in detected] == [("Netflix", "monthly", 64_900)]
    sub = api.post("/api/subscriptions", json={"name": "Netflix", "merchant": "Netflix", "amount": "649", "frequency": "monthly", "next_payment_date": today.isoformat(), "detected": True})
    assert sub["annual_equivalent_minor"] == 778_800
    api.post("/api/alerts/rules", json={"name": "Price", "metric": "subscription_price_changed", "cooldown_policy": "every_event"})
    add_txn(api, acc["id"], "799", "expense", "NETFLIX.COM", merchant="Netflix")
    updated = api.get("/api/subscriptions")["items"][0]
    assert (updated["amount_minor"], updated["previous_amount_minor"]) == (79_900, 64_900)
    assert any(n["title"] == "Netflix price changed" for n in api.get("/api/notifications")["items"])


def test_goal_contributions_and_linked_account(api):
    acc = make_account(api, "Emergency FD", opening="60000")
    goal = api.post("/api/goals", json={"name": "Trip", "goal_type": "vacation", "target": "50000", "initial_amount": "10000"})
    assert goal["progress_pct"] == 20.0
    res = api.post(f"/api/goals/{goal['id']}/contributions", json={"amount": "40000", "date": date.today().isoformat()})
    assert res["goal"]["is_complete"] and res["goal"]["status"] == "completed"
    linked = api.post("/api/goals", json={"name": "Emergency", "target": "120000", "linked_account_id": acc["id"]})
    assert linked["current"] == 6_000_000 and linked["progress_pct"] == 50.0


def test_recurring_generates_due_transactions_once(api):
    acc = make_account(api)
    start = add_months(date.today(), -2)
    rec = api.post("/api/recurring", json={"name": "Salary", "type": "income", "account_id": acc["id"], "amount": "90000", "frequency": "monthly", "next_date": start.isoformat()})
    assert rec["generated"] == 3
    assert api.get("/api/transactions", params={"q": "Salary"})["total"] == 3


def test_reports_export_csv_and_xlsx(api):
    acc = make_account(api)
    add_txn(api, acc["id"], "1234.56", "expense", "Groceries run", category_id=category_id(api, "Groceries"))
    summary = api.get("/api/reports/monthly_summary")
    assert ["Expenses", "1234.56"] in [[r[0], str(r[1])] for r in summary["rows"]]
    csv_resp = api.get("/api/reports/transactions", params={"format": "csv"})
    assert "Groceries run" in csv_resp.text and "1234.56" in csv_resp.text
    xlsx = api.get("/api/reports/expenses", params={"format": "xlsx"})
    assert xlsx.content[:2] == b"PK"
    api.get("/api/reports/nope", expected=404)


def test_backup_roundtrip_and_legacy_restore(api):
    acc = make_account(api)
    add_txn(api, acc["id"], "500", "expense", "Dinner", category_id=category_id(api, "Restaurants"), tags=["friends"])
    api.post("/api/budgets", json={"name": "Food", "category_id": category_id(api, "Food"), "amount": "8000"})
    backup = api.client.get("/api/backup").content
    add_txn(api, acc["id"], "999", "expense", "After backup")
    api.post("/api/backup/restore", files={"file": ("b.json", backup, "application/json")}, expected=400)  # confirm required
    result = api.post("/api/backup/restore?confirm=true", files={"file": ("b.json", backup, "application/json")})
    assert result["transactions"] == 1
    txns = api.get("/api/transactions")["items"]
    assert [(t["description"], t["category"], [x["name"] for x in t["tags"]]) for t in txns] == [("Dinner", "Restaurants", ["friends"])]

    legacy = b'{"version": 1, "data": {"transactions": [{"title": "Chai", "amount": 20.0, "category": "Eating out", "kind": "expense", "date": "2026-09-01T12:00:00"}], "accounts": [{"name": "SBI", "account_type": "savings", "opening_balance": 1000.5}], "budgets": [], "goals": [], "bills": []}}'
    assert api.post("/api/backup/restore?confirm=true", files={"file": ("old.json", legacy, "application/json")})["format"] == "v1"
    t = api.get("/api/transactions")["items"][0]
    assert (t["description"], t["amount_minor"], t["category"]) == ("Chai", 2000, "Restaurants")


def test_insights_are_derived_from_data(api):
    acc = make_account(api, opening="100000")
    food = category_id(api, "Food")
    api.post("/api/budgets", json={"name": "Food", "category_id": food, "amount": "1000"})
    add_txn(api, acc["id"], "950", "expense", "Restaurant", category_id=category_id(api, "Restaurants"))
    kinds = {i["kind"] for i in api.get("/api/insights")}
    assert "budget" in kinds and "largest_expense" in kinds


def test_onboarding_checklist_tracks_real_state(api):
    steps = {s["key"]: s["done"] for s in api.get("/api/dashboard")["onboarding"]["steps"]}
    assert steps["account"] is False
    make_account(api)
    steps = {s["key"]: s["done"] for s in api.get("/api/dashboard")["onboarding"]["steps"]}
    assert steps["account"] is True and steps["transactions"] is False


def test_migrations_build_the_schema(tmp_path):
    url = f"sqlite:///{(tmp_path / 'migrated.sqlite3').as_posix()}"
    upgrade_database(url)
    import sqlite3

    tables = {r[0] for r in sqlite3.connect(tmp_path / "migrated.sqlite3").execute("select name from sqlite_master where type='table'")}
    assert {"transactions", "alert_rules", "notification_deliveries", "bank_connections", "jobs"} <= tables
