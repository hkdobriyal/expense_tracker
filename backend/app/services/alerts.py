"""The alert / automation engine.

A rule reads as: WHEN <metric>(params) <operator> <threshold> THEN notify <channels>.

Two kinds of metrics:

* **state** metrics describe the current situation (budget usage, balance,
  days until a bill). They are re-evaluated after every ledger change and
  periodically by the worker, so date-driven alerts fire without a browser open.
* **event** metrics look at a single new transaction (large payment, new
  merchant, refund…) and fire once per matching transaction.

Cooldown policies stop repeated notifications:

* ``once_per_threshold`` – once per period (e.g. once per budget month) or,
  for period-less metrics like balance, once per "episode" until it recovers
* ``once_per_day``       – at most once per calendar day while true
* ``cooldown``           – at most once every ``cooldown_minutes``
* ``every_event``        – every matching transaction (event metrics)

Every firing is stored as an AlertEvent with a unique dedupe key, which makes
the engine idempotent and the history debuggable.
"""

from __future__ import annotations

import operator as op
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Account, AlertEvent, AlertRule, Bill, Budget, Category, Goal, Subscription, Transaction, User
from ..money import format_display, from_minor, percent
from . import budgets as budget_svc
from . import goals as goal_svc
from . import ledger, notifications
from .context import UserContext
from .periods import month_bounds, period_window

OPERATORS: dict[str, Callable[[Decimal, Decimal], bool]] = {
    ">": op.gt, ">=": op.ge, "<": op.lt, "<=": op.le, "=": op.eq, "!=": op.ne,
}
POLICIES = ("once_per_threshold", "once_per_day", "cooldown", "every_event")


@dataclass
class Metric:
    key: str
    label: str
    description: str
    category: str  # notification category (budget, spending, transaction, account, bills, subscriptions, goals, income, system)
    kind: str  # state|event
    unit: str  # money|percent|days|multiplier|none
    params: dict[str, str] = field(default_factory=dict)  # name -> budget|category|account|goal|period|day_of_month
    default_operator: str = ">="
    default_threshold: Decimal | None = None
    boolean: bool = False  # threshold not used (condition is the metric itself)

    def public(self) -> dict:
        return {
            "key": self.key, "label": self.label, "description": self.description, "category": self.category,
            "kind": self.kind, "unit": self.unit, "params": self.params, "default_operator": self.default_operator,
            "default_threshold": str(self.default_threshold) if self.default_threshold is not None else None,
            "boolean": self.boolean, "operators": [] if self.boolean else list(OPERATORS),
            "default_policy": "every_event" if self.kind == "event" else "once_per_threshold",
        }


METRICS: dict[str, Metric] = {m.key: m for m in [
    Metric("budget_usage", "Budget usage", "Percentage of a budget spent in its current period", "budget", "state", "percent", {"budget_id": "budget"}, ">=", Decimal(80)),
    Metric("category_spending", "Category spending", "Spending in a category this day/week/month", "spending", "state", "money", {"category_id": "category", "period": "period"}, ">", Decimal(5000)),
    Metric("total_spending", "Total spending", "All spending this day/week/month", "spending", "state", "money", {"period": "period"}, ">", Decimal(50000)),
    Metric("savings_rate", "Savings rate", "Savings as a share of income this month", "spending", "state", "percent", {}, "<", Decimal(20)),
    Metric("account_balance", "Account balance", "Current balance of an account (or any account)", "account", "state", "money", {"account_id": "account"}, "<", Decimal(1000)),
    Metric("bill_due_within", "Bill due soon", "A bill is due within N days (0 = due today)", "bills", "state", "days", {}, "<=", Decimal(3)),
    Metric("bill_overdue", "Bill overdue", "An unpaid bill is past its due date", "bills", "state", "days", {}, ">", Decimal(0)),
    Metric("subscription_renewal", "Subscription renewal", "A subscription renews within N days", "subscriptions", "state", "days", {}, "<=", Decimal(3)),
    Metric("goal_progress", "Goal milestone", "A goal reaches a percentage (100 = completed)", "goals", "state", "percent", {"goal_id": "goal"}, ">=", Decimal(50)),
    Metric("goal_behind_schedule", "Goal behind schedule", "Progress lags the time-based expectation by N percentage points", "goals", "state", "percent", {"goal_id": "goal"}, ">", Decimal(10)),
    Metric("expected_income_missing", "Expected income missing", "No income in a category (e.g. Salary) by a day of the month", "income", "state", "none", {"category_id": "category", "day_of_month": "day_of_month"}, boolean=True),
    Metric("large_transaction", "Large transaction", "A single expense above an amount", "transaction", "event", "money", {}, ">", Decimal(10000)),
    Metric("unusual_transaction", "Unusual transaction", "An expense N× larger than the category's typical (median) amount", "transaction", "event", "multiplier", {}, ">=", Decimal(3)),
    Metric("new_merchant", "New merchant", "First transaction with a merchant", "transaction", "event", "none", boolean=True),
    Metric("duplicate_transaction", "Possible duplicate", "Same account, date, amount and description as an existing transaction", "transaction", "event", "none", boolean=True),
    Metric("refund_received", "Refund received", "A refund was recorded", "transaction", "event", "money", {}, ">", Decimal(0)),
    Metric("salary_detected", "Salary detected", "An income transaction categorised as Salary", "income", "event", "money", {}, ">", Decimal(0)),
    Metric("subscription_price_changed", "Subscription price changed", "A subscription was charged a different amount", "subscriptions", "event", "none", boolean=True),
    Metric("sync_failed", "Bank sync failed", "A bank synchronisation failed", "system", "event", "none", boolean=True),
]}


@dataclass
class Observation:
    entity: str
    value: Decimal
    period_key: str  # "-" = no period (episode-based)
    title: str
    message: str
    severity: str = "warning"
    link: str = ""
    context: dict = field(default_factory=dict)
    condition: bool | None = None  # precomputed for boolean metrics


def _money(ctx: UserContext, minor: int) -> str:
    return format_display(minor, ctx.base_currency)


def _major(minor: int, currency: str) -> Decimal:
    return from_minor(minor, currency)


# ---------------------------------------------------------------------------
# State evaluators
# ---------------------------------------------------------------------------


def _eval_budget_usage(db: Session, ctx: UserContext, rule: AlertRule) -> list[Observation]:
    stmt = select(Budget).where(Budget.user_id == ctx.user_id, Budget.active.is_(True))
    if rule.params.get("budget_id"):
        stmt = stmt.where(Budget.id == int(rule.params["budget_id"]))
    categories = db.scalars(select(Category).where(Category.user_id == ctx.user_id)).all()
    out = []
    for budget in db.scalars(stmt).all():
        st = budget_svc.budget_status(db, budget, ctx.today, ctx.week_start, categories)
        over = st["spent"] > st["limit"]
        out.append(Observation(
            entity=f"budget:{budget.id}", value=Decimal(str(st["usage_pct"])), period_key=st["window_start"],
            title=f"{'Budget exceeded' if over else 'Budget warning'}: {budget.name}",
            message=f"You have used {st['usage_pct']:.0f}% of your {budget.name} budget ({_money(ctx, st['spent'])} of {_money(ctx, st['limit'])}).",
            severity="critical" if over else "warning", link="/budgets", context={"budget_id": budget.id, **st},
        ))
    return out


def _eval_spending(db: Session, ctx: UserContext, rule: AlertRule) -> list[Observation]:
    period = rule.params.get("period", "month")
    start, end = period_window(period, ctx.today, ctx.week_start)
    cat_ids = None
    label = "Total"
    if rule.metric == "category_spending":
        cat_id = rule.params.get("category_id")
        if not cat_id:
            return []
        categories = db.scalars(select(Category).where(Category.user_id == ctx.user_id)).all()
        cat = next((c for c in categories if c.id == int(cat_id)), None)
        if cat is None:
            return []
        cat_ids = ledger.descendant_ids(categories, cat.id)
        label = cat.name
    spent = ledger.spent_in_categories(db, ctx.user_id, cat_ids, start, end)
    period_label = {"day": "today", "week": "this week"}.get(period, "this month")
    return [Observation(
        entity=f"spend:{rule.params.get('category_id', 'all')}:{period}", value=_major(spent, ctx.base_currency), period_key=start.isoformat(),
        title=f"{label} spending alert", message=f"{label} spending {period_label} is {_money(ctx, spent)}.",
        link="/analytics", context={"spent": spent, "start": start.isoformat(), "end": end.isoformat()},
    )]


def _eval_savings_rate(db: Session, ctx: UserContext, rule: AlertRule) -> list[Observation]:
    start, end = month_bounds(ctx.today)
    totals = ledger.period_totals(db, ctx.user_id, start, end)
    if totals.income <= 0:
        return []
    return [Observation(
        entity="savings_rate", value=Decimal(str(totals.savings_rate)), period_key=start.isoformat(),
        title="Savings rate alert", message=f"Your savings rate this month is {totals.savings_rate:.0f}% ({_money(ctx, totals.savings)} saved of {_money(ctx, totals.income)} income).",
        link="/cash-flow",
    )]


def _eval_account_balance(db: Session, ctx: UserContext, rule: AlertRule) -> list[Observation]:
    stmt = select(Account).where(Account.user_id == ctx.user_id, Account.is_archived.is_(False))
    if rule.params.get("account_id"):
        stmt = stmt.where(Account.id == int(rule.params["account_id"]))
    else:
        stmt = stmt.where(Account.type.in_(("current", "savings", "cash", "wallet")))
    accounts = db.scalars(stmt).all()
    balances = ledger.account_balances(db, ctx.user_id, account_ids=[a.id for a in accounts])
    return [Observation(
        entity=f"account:{a.id}", value=_major(balances.get(a.id, 0), a.currency), period_key="-",
        title=f"Low balance: {a.name}", message=f"{a.name} balance is {format_display(balances.get(a.id, 0), a.currency)}.",
        link="/accounts", context={"account_id": a.id, "balance": balances.get(a.id, 0)},
    ) for a in accounts]


def _eval_bills(db: Session, ctx: UserContext, rule: AlertRule) -> list[Observation]:
    bills = db.scalars(select(Bill).where(Bill.user_id == ctx.user_id, Bill.active.is_(True))).all()
    out = []
    for bill in bills:
        days = (bill.next_due_date - ctx.today).days
        amount = format_display(bill.amount_minor, bill.currency)
        if rule.metric == "bill_overdue":
            if days >= 0:
                out.append(Observation(f"bill:{bill.id}:{bill.next_due_date}", Decimal(0), "-", "", ""))
                continue
            out.append(Observation(
                entity=f"bill:{bill.id}:{bill.next_due_date}", value=Decimal(-days), period_key="-",
                title=f"Bill overdue: {bill.name}", message=f"{bill.name} ({amount}) was due on {bill.next_due_date:%d %b} and is {-days} day(s) overdue.",
                severity="critical", link="/bills", context={"bill_id": bill.id},
            ))
        else:
            if days < 0:
                continue
            when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
            out.append(Observation(
                entity=f"bill:{bill.id}:{bill.next_due_date}", value=Decimal(days), period_key="-",
                title=f"Bill due {when}: {bill.name}", message=f"{bill.name} ({amount}) is due {when} ({bill.next_due_date:%d %b}).{' Auto-pay is on.' if bill.autopay else ''}",
                severity="warning" if days <= 1 else "info", link="/bills", context={"bill_id": bill.id},
            ))
    return out


def _eval_subscriptions(db: Session, ctx: UserContext, rule: AlertRule) -> list[Observation]:
    subs = db.scalars(select(Subscription).where(Subscription.user_id == ctx.user_id, Subscription.active.is_(True), Subscription.next_payment_date.is_not(None))).all()
    out = []
    for sub in subs:
        days = (sub.next_payment_date - ctx.today).days
        if days < 0:
            continue
        when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        out.append(Observation(
            entity=f"sub:{sub.id}:{sub.next_payment_date}", value=Decimal(days), period_key="-",
            title=f"{sub.name} renews {when}", message=f"{sub.name} renews {when} for {format_display(sub.amount_minor, sub.currency)}.",
            severity="info", link="/subscriptions", context={"subscription_id": sub.id},
        ))
    return out


def _eval_goals(db: Session, ctx: UserContext, rule: AlertRule) -> list[Observation]:
    stmt = select(Goal).where(Goal.user_id == ctx.user_id, Goal.status != "archived")
    if rule.params.get("goal_id"):
        stmt = stmt.where(Goal.id == int(rule.params["goal_id"]))
    out = []
    for goal in db.scalars(stmt).all():
        st = goal_svc.goal_status(db, goal, ctx.today)
        if rule.metric == "goal_progress":
            complete = st["progress_pct"] >= 100
            out.append(Observation(
                entity=f"goal:{goal.id}", value=Decimal(str(st["progress_pct"])), period_key=f"milestone-{rule.threshold}",
                title=f"Goal {'completed' if complete else 'milestone'}: {goal.name}",
                message=f"{goal.name} is {st['progress_pct']:.0f}% funded ({format_display(st['current'], goal.currency)} of {format_display(goal.target_minor, goal.currency)}).",
                severity="success", link="/goals", context={"goal_id": goal.id},
            ))
        elif st["behind_by_pct"] is not None:
            out.append(Observation(
                entity=f"goal:{goal.id}", value=Decimal(str(st["behind_by_pct"])), period_key=ctx.today.strftime("%Y-%m"),
                title=f"Goal behind schedule: {goal.name}",
                message=f"{goal.name} is {st['progress_pct']:.0f}% funded but should be about {st['expected_pct']:.0f}% by now. Saving {format_display(st['monthly_needed'] or 0, goal.currency)}/month gets it back on track.",
                link="/goals", context={"goal_id": goal.id},
            ))
    return out


def _eval_income_missing(db: Session, ctx: UserContext, rule: AlertRule) -> list[Observation]:
    day = int(rule.params.get("day_of_month") or 5)
    cat_id = rule.params.get("category_id")
    start, end = month_bounds(ctx.today)
    if ctx.today.day <= day:
        return [Observation("income", Decimal(0), start.isoformat(), "", "", condition=False)]
    stmt = select(func.count()).select_from(Transaction).where(
        Transaction.user_id == ctx.user_id, Transaction.type == "income", Transaction.date >= start, Transaction.date <= end
    )
    label = "income"
    if cat_id:
        categories = db.scalars(select(Category).where(Category.user_id == ctx.user_id)).all()
        ids = ledger.descendant_ids(categories, int(cat_id))
        stmt = stmt.where(Transaction.category_id.in_(ids))
        label = next((c.name for c in categories if c.id == int(cat_id)), "income")
    missing = (db.scalar(stmt) or 0) == 0
    return [Observation(
        entity=f"income:{cat_id or 'any'}", value=Decimal(1 if missing else 0), period_key=start.isoformat(),
        title=f"Expected {label} not received", message=f"No {label} has been recorded this month and it is past day {day}.",
        link="/transactions", condition=missing,
    )]


STATE_EVALUATORS: dict[str, Callable[[Session, UserContext, AlertRule], list[Observation]]] = {
    "budget_usage": _eval_budget_usage,
    "category_spending": _eval_spending,
    "total_spending": _eval_spending,
    "savings_rate": _eval_savings_rate,
    "account_balance": _eval_account_balance,
    "bill_due_within": _eval_bills,
    "bill_overdue": _eval_bills,
    "subscription_renewal": _eval_subscriptions,
    "goal_progress": _eval_goals,
    "goal_behind_schedule": _eval_goals,
    "expected_income_missing": _eval_income_missing,
}


# ---------------------------------------------------------------------------
# Event evaluators (one new transaction)
# ---------------------------------------------------------------------------


def _txn_obs(ctx: UserContext, txn: Transaction, value: Decimal, title: str, message: str, severity: str = "info", condition: bool | None = None) -> Observation:
    return Observation(f"txn:{txn.id}", value, "-", title, message, severity, f"/transactions?focus={txn.id}", {"transaction_id": txn.id}, condition)


def _merchant_label(txn: Transaction) -> str:
    return txn.merchant.name if txn.merchant is not None else txn.description


def _ev_large(db, ctx, rule, txn):
    if txn.type != "expense":
        return None
    return _txn_obs(ctx, txn, _major(txn.base_amount_minor, ctx.base_currency), "Large transaction",
                    f"{_money(ctx, txn.base_amount_minor)} payment detected at {_merchant_label(txn)}.", "warning")


def _ev_unusual(db, ctx, rule, txn):
    if txn.type != "expense" or txn.category_id is None:
        return None
    history = [v for v in ledger.category_history(db, ctx.user_id, {txn.category_id}, txn.date - timedelta(days=90), txn.date) if v > 0]
    history_without = list(history)
    if txn.base_amount_minor in history_without:
        history_without.remove(txn.base_amount_minor)
    if len(history_without) < 5:
        return None
    typical = ledger.median(history_without)
    if typical <= 0:
        return None
    ratio = (Decimal(txn.base_amount_minor) / typical).quantize(Decimal("0.1"))
    return _txn_obs(ctx, txn, ratio, "Unusual transaction",
                    f"{_money(ctx, txn.base_amount_minor)} at {_merchant_label(txn)} is {ratio}× your typical {txn.category.name if txn.category else ''} spend ({_money(ctx, int(typical))}).", "warning")


def _ev_new_merchant(db, ctx, rule, txn):
    if not txn.merchant_id or txn.type not in ("expense", "income"):
        return None
    earlier = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.user_id == ctx.user_id, Transaction.merchant_id == txn.merchant_id, Transaction.id != txn.id)) or 0
    return _txn_obs(ctx, txn, Decimal(0), "New merchant", f"First transaction with {_merchant_label(txn)}: {_money(ctx, txn.base_amount_minor)}.", condition=earlier == 0)


def _ev_duplicate(db, ctx, rule, txn):
    other = db.scalar(select(func.count()).select_from(Transaction).where(
        Transaction.user_id == ctx.user_id, Transaction.fingerprint == txn.fingerprint, Transaction.id != txn.id))
    return _txn_obs(ctx, txn, Decimal(0), "Possible duplicate transaction",
                    f"{txn.description} ({_money(ctx, txn.base_amount_minor)} on {txn.date:%d %b}) matches an existing transaction.", "warning", condition=bool(other))


def _ev_refund(db, ctx, rule, txn):
    if txn.type != "refund":
        return None
    return _txn_obs(ctx, txn, _major(txn.base_amount_minor, ctx.base_currency), "Refund received", f"Refund of {_money(ctx, txn.base_amount_minor)} from {_merchant_label(txn)}.", "success")


def _ev_salary(db, ctx, rule, txn):
    if txn.type != "income":
        return None
    is_salary = "salary" in (txn.description or "").lower() or "payroll" in (txn.raw_description or "").lower()
    if txn.category is not None:
        cat = txn.category
        while cat.parent is not None:
            cat = cat.parent
        is_salary = is_salary or cat.name.lower() == "salary"
    if not is_salary:
        return None
    return _txn_obs(ctx, txn, _major(txn.base_amount_minor, ctx.base_currency), "Salary received", f"Salary of {_money(ctx, txn.base_amount_minor)} credited to {txn.account.name}.", "success")


EVENT_EVALUATORS = {
    "large_transaction": _ev_large,
    "unusual_transaction": _ev_unusual,
    "new_merchant": _ev_new_merchant,
    "duplicate_transaction": _ev_duplicate,
    "refund_received": _ev_refund,
    "salary_detected": _ev_salary,
}


# ---------------------------------------------------------------------------
# Firing, cooldowns and entry points
# ---------------------------------------------------------------------------


def condition_met(rule: AlertRule, metric: Metric, obs: Observation) -> bool:
    if obs.condition is not None:
        return obs.condition
    if metric.boolean:
        return True
    threshold = Decimal(rule.threshold if rule.threshold is not None else (metric.default_threshold or 0))
    return OPERATORS.get(rule.operator, op.ge)(obs.value, threshold)


def _decide(rule: AlertRule, obs: Observation, now: datetime, today_iso: str, event_mode: bool, state: dict | None = None) -> tuple[bool, str | None, str]:
    """Return (fire, new_state_marker, dedupe_key) according to the cooldown policy."""
    state = rule.state or {} if state is None else state
    policy = rule.cooldown_policy if rule.cooldown_policy in POLICIES else "once_per_threshold"
    state_key = "event" if event_mode and policy != "every_event" else obs.entity
    previous = state.get(state_key)
    base = f"r{rule.id}:{obs.entity}"
    if policy == "every_event":
        return True, None, base if event_mode else f"{base}:{obs.period_key}"
    if policy == "once_per_day":
        return previous != today_iso, today_iso, f"{base}:{today_iso}"
    if policy == "cooldown":
        minutes = max(rule.cooldown_minutes or 0, 1)
        try:
            fire = previous is None or now - datetime.fromisoformat(previous) >= timedelta(minutes=minutes)
        except (TypeError, ValueError):  # state written by a different policy
            fire = True
        return fire, now.isoformat(), f"{base}:{now.isoformat()}"
    # once_per_threshold
    if event_mode:
        return True, None, base
    if obs.period_key != "-":
        return previous != obs.period_key, obs.period_key, f"{base}:{obs.period_key}"
    return previous is None, now.isoformat(), f"{base}:{now.isoformat()}"


def _fire(db: Session, ctx: UserContext, rule: AlertRule | None, metric: Metric, obs: Observation, dedupe_key: str) -> AlertEvent | None:
    exists = db.scalar(select(AlertEvent.id).where(AlertEvent.user_id == ctx.user_id, AlertEvent.dedupe_key == dedupe_key))
    if exists:
        return None
    threshold = "" if rule is None or rule.threshold is None else str(rule.threshold)
    event = AlertEvent(
        user_id=ctx.user_id, rule_id=rule.id if rule else None, metric=metric.key, category=metric.category,
        dedupe_key=dedupe_key[:255], title=obs.title[:200], message=obs.message, severity=obs.severity,
        value=str(obs.value), threshold=threshold, context={**obs.context, "link": obs.link, "entity": obs.entity},
    )
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
    except IntegrityError:
        return None  # a concurrent evaluation fired it first
    user = db.get(User, ctx.user_id)
    channels = notifications.resolve_channels(ctx.settings, metric.category, rule.channels if rule else None)
    notifications.dispatch(db, user, ctx.settings, event, channels)
    if rule is not None:
        rule.last_triggered_at = utcnow()
    return event


def evaluate_state_rules(db: Session, ctx: UserContext, metrics: set[str] | None = None) -> list[AlertEvent]:
    now = utcnow()
    today_iso = ctx.today.isoformat()
    fired: list[AlertEvent] = []
    rules = db.scalars(select(AlertRule).where(AlertRule.user_id == ctx.user_id, AlertRule.enabled.is_(True))).all()
    for rule in rules:
        metric = METRICS.get(rule.metric)
        if metric is None or metric.kind != "state" or (metrics and rule.metric not in metrics):
            continue
        evaluator = STATE_EVALUATORS[rule.metric]
        state = dict(rule.state or {})
        seen = set()
        for obs in evaluator(db, ctx, rule):
            seen.add(obs.entity)
            if not condition_met(rule, metric, obs):
                if obs.period_key == "-":
                    state.pop(obs.entity, None)  # recovered: allow the next episode to fire
                continue
            fire, marker, key = _decide(rule, obs, now, today_iso, event_mode=False, state=state)
            if fire:
                event = _fire(db, ctx, rule, metric, obs, key)
                if event is not None:
                    fired.append(event)
            if marker is not None:
                state[obs.entity] = marker
        # Always assign a *new* dict: _fire() flushes mid-loop, and mutating a dict SQLAlchemy
        # has already flushed would make the change invisible to its dirty-checking.
        rule.state = {k: v for k, v in state.items() if k in seen}
        rule.last_evaluated_at = now
    db.flush()
    return fired


def evaluate_event_rules(db: Session, ctx: UserContext, txns: list[Transaction]) -> list[AlertEvent]:
    if not txns:
        return []
    now = utcnow()
    today_iso = ctx.today.isoformat()
    fired: list[AlertEvent] = []
    rules = db.scalars(select(AlertRule).where(AlertRule.user_id == ctx.user_id, AlertRule.enabled.is_(True), AlertRule.metric.in_(list(EVENT_EVALUATORS)))).all()
    for rule in rules:
        metric = METRICS[rule.metric]
        evaluator = EVENT_EVALUATORS[rule.metric]
        for txn in txns:
            obs = evaluator(db, ctx, rule, txn)
            if obs is None or not condition_met(rule, metric, obs):
                continue
            fire, marker, key = _decide(rule, obs, now, today_iso, event_mode=True)
            if not fire:
                continue
            event = _fire(db, ctx, rule, metric, obs, key)
            if event is not None:
                fired.append(event)
                if marker is not None:
                    rule.state = {**(rule.state or {}), "event": marker}
    db.flush()
    return fired


def emit(db: Session, ctx: UserContext, metric_key: str, obs: Observation) -> list[AlertEvent]:
    """Fire an externally detected event (sync failure, price change) through matching rules."""
    metric = METRICS[metric_key]
    now = utcnow()
    fired = []
    rules = db.scalars(select(AlertRule).where(AlertRule.user_id == ctx.user_id, AlertRule.enabled.is_(True), AlertRule.metric == metric_key)).all()
    for rule in rules:
        fire, marker, key = _decide(rule, obs, now, ctx.today.isoformat(), event_mode=True)
        if fire:
            event = _fire(db, ctx, rule, metric, obs, key)
            if event is not None:
                fired.append(event)
                if marker is not None:
                    rule.state = {**(rule.state or {}), "event": marker}
    return fired


def after_ledger_change(db: Session, ctx: UserContext, new_transactions: list[Transaction] | None = None) -> list[AlertEvent]:
    """Hook called after transactions are created/updated/deleted/imported."""
    from . import subscriptions as sub_svc

    fired: list[AlertEvent] = []
    for txn in new_transactions or []:
        for sub, old_amount in sub_svc.observe_transaction(db, txn):
            fired += emit(db, ctx, "subscription_price_changed", Observation(
                entity=f"sub:{sub.id}:{sub.amount_minor}", value=Decimal(0), period_key="-",
                title=f"{sub.name} price changed", severity="warning", link="/subscriptions",
                message=f"{sub.name} charged {format_display(sub.amount_minor, sub.currency)} instead of {format_display(old_amount, sub.currency)} ({percent(sub.amount_minor - old_amount, old_amount):+.0f}%).",
            ))
    fired += evaluate_event_rules(db, ctx, new_transactions or [])
    fired += evaluate_state_rules(db, ctx)
    return fired


DEFAULT_RULES = [
    {"name": "Bill due within 3 days", "metric": "bill_due_within", "operator": "<=", "threshold": Decimal(3)},
    {"name": "Bill overdue", "metric": "bill_overdue", "operator": ">", "threshold": Decimal(0)},
    {"name": "Subscription renews within 3 days", "metric": "subscription_renewal", "operator": "<=", "threshold": Decimal(3)},
    {"name": "Bank sync failed", "metric": "sync_failed", "operator": ">=", "threshold": None, "cooldown_policy": "every_event"},
]


def create_default_rules(db: Session, user_id: int) -> None:
    for spec in DEFAULT_RULES:
        db.add(AlertRule(user_id=user_id, params={}, channels=None, **{"cooldown_policy": "once_per_threshold", **spec}))


def validate_rule(db: Session, user_id: int, metric_key: str, params: dict, operator_key: str, threshold, policy: str) -> str | None:
    metric = METRICS.get(metric_key)
    if metric is None:
        return f"Unknown metric '{metric_key}'"
    if not metric.boolean and operator_key not in OPERATORS:
        return f"Unknown operator '{operator_key}'"
    if policy not in POLICIES:
        return f"Unknown cooldown policy '{policy}'"
    if not metric.boolean and threshold is None and metric.default_threshold is None:
        return "Threshold is required"
    owned = {"budget": Budget, "category": Category, "account": Account, "goal": Goal}
    for name, kind in metric.params.items():
        value = params.get(name)
        if kind in owned and value not in (None, ""):
            obj = db.get(owned[kind], int(value))
            if obj is None or obj.user_id != user_id:
                return f"{kind.title()} not found"
        if kind == "period" and value not in (None, "day", "week", "month"):
            return "Period must be day, week or month"
    if metric_key == "category_spending" and not params.get("category_id"):
        return "Choose a category"
    return None
