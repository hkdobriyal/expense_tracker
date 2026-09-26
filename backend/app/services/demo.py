"""Demo mode: an isolated sample workspace.

The demo lives in its own user account (``is_demo=True``), so its data is
separated from real data by the same ``user_id`` isolation as everything
else. Transactions come from the sandbox bank provider through the real sync
pipeline, so dashboards, budgets and alerts behave exactly as they would with
real data.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, AlertRule, Bill, Budget, Category, Goal, GoalContribution, Subscription, User, UserSettings
from ..money import to_minor
from ..security import hash_password
from . import alerts, banking
from .catalog import seed_default_categories
from .categorization import get_or_create_merchant
from .context import UserContext
from .periods import add_months, month_bounds

DEMO_EMAIL = "demo@ledgerly.local"


def _category(db: Session, user_id: int, name: str) -> Category | None:
    return db.scalar(select(Category).where(Category.user_id == user_id, Category.name == name))


def reset_demo_user(db: Session) -> User:
    existing = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if existing is not None:
        db.delete(existing)
        db.flush()
    user = User(email=DEMO_EMAIL, password_hash=hash_password(secrets.token_urlsafe(24)), display_name="Demo", is_demo=True)
    db.add(user)
    db.flush()
    settings = UserSettings(user_id=user.id, base_currency="INR", timezone="Asia/Kolkata", contact_email=DEMO_EMAIL, channel_email=False)
    db.add(settings)
    db.flush()
    seed_default_categories(db, user.id)
    alerts.create_default_rules(db, user.id)
    ctx = UserContext.for_user(db, user)
    today = ctx.today

    # Linked sandbox bank: savings + credit card, populated by the real sync pipeline.
    conn, _ = banking.start_connection(db, ctx, user, "demo", "sandbox-bank", {})
    linked = banking.link_accounts(db, ctx, conn, [a.external_id for a in banking.get_provider("demo").list_accounts(conn)])
    savings = next(a for a in linked if a.type == "savings")
    savings.opening_balance_minor = to_minor(42_000, "INR")
    savings.opening_date = today - timedelta(days=banking.INITIAL_LOOKBACK_DAYS + 1)
    card = next(a for a in linked if a.type == "credit_card")
    card.credit_limit_minor = to_minor(150_000, "INR")
    card.opening_balance_minor = -to_minor(9_500, "INR")  # statement balance owed when the demo starts
    card.opening_date = savings.opening_date

    cash = Account(user_id=user.id, name="Cash wallet", type="cash", currency="INR", opening_balance_minor=to_minor(3_500, "INR"), opening_date=savings.opening_date)
    emergency = Account(user_id=user.id, name="Emergency fund (FD)", type="savings", institution="Sandbox Bank", currency="INR", opening_balance_minor=to_minor(180_000, "INR"), opening_date=savings.opening_date)
    mf = Account(user_id=user.id, name="Mutual funds", type="investment", institution="Sandbox AMC", currency="INR", opening_balance_minor=to_minor(310_000, "INR"), opening_date=savings.opening_date)
    loan = Account(user_id=user.id, name="Car loan", type="loan", institution="Sandbox Bank", currency="INR", opening_balance_minor=-to_minor(240_000, "INR"), opening_date=savings.opening_date)
    db.add_all([cash, emergency, mf, loan])
    db.flush()
    settings.default_account_id = savings.id

    food = _category(db, user.id, "Food")
    groceries = _category(db, user.id, "Groceries")
    transport = _category(db, user.id, "Transport")
    entertainment = _category(db, user.id, "Entertainment")
    streaming = _category(db, user.id, "Streaming")
    electricity = _category(db, user.id, "Electricity")
    internet = _category(db, user.id, "Internet")
    insurance = _category(db, user.id, "Health insurance")
    salary = _category(db, user.id, "Salary")

    db.add_all([
        Budget(user_id=user.id, name="Food", category_id=food.id, period="monthly", amount_minor=to_minor(12_000, "INR")),
        Budget(user_id=user.id, name="Groceries", category_id=groceries.id, period="monthly", amount_minor=to_minor(6_000, "INR")),
        Budget(user_id=user.id, name="Transport", category_id=transport.id, period="monthly", amount_minor=to_minor(4_000, "INR")),
        Budget(user_id=user.id, name="Entertainment", category_id=entertainment.id, period="monthly", amount_minor=to_minor(2_500, "INR")),
        Budget(user_id=user.id, name="Everything", category_id=None, period="monthly", amount_minor=to_minor(60_000, "INR")),
    ])
    db.flush()
    for budget in db.scalars(select(Budget).where(Budget.user_id == user.id)).all():
        db.add(AlertRule(user_id=user.id, name=f"{budget.name} budget 80%", metric="budget_usage", params={"budget_id": budget.id}, operator=">=", threshold=80))

    trip = Goal(user_id=user.id, name="Goa trip", goal_type="vacation", target_minor=to_minor(60_000, "INR"), currency="INR", start_date=add_months(today, -3), target_date=add_months(today, 4))
    efund = Goal(user_id=user.id, name="Emergency fund", goal_type="emergency_fund", target_minor=to_minor(300_000, "INR"), currency="INR", start_date=add_months(today, -6), target_date=add_months(today, 12), linked_account_id=emergency.id)
    db.add_all([trip, efund])
    db.flush()
    for months_ago, amount in ((3, 8_000), (2, 7_500), (1, 9_000)):
        db.add(GoalContribution(goal_id=trip.id, user_id=user.id, amount_minor=to_minor(amount, "INR"), date=add_months(today, -months_ago), note="Monthly transfer"))

    month_start, _ = month_bounds(today)
    db.add_all([
        Bill(user_id=user.id, name="Electricity (BESCOM)", provider="BESCOM", amount_minor=to_minor(1_900, "INR"), currency="INR", frequency="monthly", next_due_date=today + timedelta(days=2), account_id=savings.id, category_id=electricity.id),
        Bill(user_id=user.id, name="Broadband", provider="Airtel", amount_minor=to_minor(799, "INR"), currency="INR", frequency="monthly", next_due_date=today + timedelta(days=9), autopay=True, account_id=savings.id, category_id=internet.id),
        Bill(user_id=user.id, name="Health insurance premium", provider="Sandbox Insurance", amount_minor=to_minor(18_500, "INR"), currency="INR", frequency="yearly", next_due_date=today + timedelta(days=24), account_id=savings.id, category_id=insurance.id),
        Bill(user_id=user.id, name="Car loan EMI", provider="Sandbox Bank", amount_minor=to_minor(9_800, "INR"), currency="INR", frequency="monthly", next_due_date=today - timedelta(days=1), account_id=savings.id),
    ])
    netflix = get_or_create_merchant(db, user.id, "Netflix")
    spotify = get_or_create_merchant(db, user.id, "Spotify")
    db.add_all([
        Subscription(user_id=user.id, name="Netflix", merchant_id=netflix.id, amount_minor=to_minor(649, "INR"), currency="INR", frequency="monthly", account_id=card.id, category_id=streaming.id, started_on=add_months(today, -14)),
        Subscription(user_id=user.id, name="Spotify", merchant_id=spotify.id, amount_minor=to_minor(119, "INR"), currency="INR", frequency="monthly", account_id=card.id, category_id=streaming.id, started_on=add_months(today, -8)),
    ])
    db.add_all([
        AlertRule(user_id=user.id, name="Large transaction over ₹5,000", metric="large_transaction", operator=">", threshold=5000, cooldown_policy="every_event"),
        AlertRule(user_id=user.id, name="Low balance under ₹10,000", metric="account_balance", params={"account_id": savings.id}, operator="<", threshold=10000),
        AlertRule(user_id=user.id, name="Salary received", metric="salary_detected", operator=">", threshold=0, cooldown_policy="every_event"),
        AlertRule(user_id=user.id, name="Salary missing after the 3rd", metric="expected_income_missing", params={"category_id": salary.id, "day_of_month": 3}),
    ])
    db.flush()
    banking.sync_connection(db, ctx, user, conn, trigger="manual")
    return user
