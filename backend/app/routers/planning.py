"""Budgets, goals, bills, subscriptions and recurring transactions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..db import get_db, utcnow
from ..deps import CurrentUser, get_current_user, get_owned
from ..models import AlertRule, Account, Bill, Budget, Category, Goal, GoalContribution, RecurringTransaction, Subscription
from ..money import MoneyError, normalize_currency, to_minor
from ..schemas import BillIn, BillPayIn, BudgetIn, ContributionIn, GoalIn, RecurringIn, SubscriptionIn
from ..services import alerts, recurring
from ..services import bills as bill_svc
from ..services import budgets as budget_svc
from ..services import goals as goal_svc
from ..services import subscriptions as sub_svc
from ..services.categorization import get_or_create_merchant
from .common import ctx_of

router = APIRouter(prefix="/api", tags=["planning"])


def _minor(value, currency: str) -> int:
    try:
        minor = to_minor(value, currency)
    except MoneyError as exc:
        raise HTTPException(422, str(exc)) from exc
    if minor <= 0:
        raise HTTPException(422, "Amount must be greater than zero")
    return minor


def _check_refs(db: Session, current: CurrentUser, account_id=None, category_id=None) -> None:
    if account_id is not None:
        get_owned(db, Account, account_id, current, "Account")
    if category_id is not None:
        get_owned(db, Category, category_id, current, "Category")


# --- Budgets ------------------------------------------------------------------------------------

@router.get("/budgets")
def list_budgets(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx = ctx_of(current)
    return [ser.budget(b, st) for b, st in budget_svc.all_budget_statuses(db, current.id, ctx.today, ctx.week_start)]


def _apply_budget(db: Session, current: CurrentUser, b: Budget, body: BudgetIn) -> None:
    _check_refs(db, current, category_id=body.category_id)
    if body.period == "custom" and not (body.start_date and body.end_date and body.start_date <= body.end_date):
        raise HTTPException(422, "Custom budgets need a start and end date")
    b.name, b.category_id, b.period = body.name, body.category_id, body.period
    b.amount_minor = _minor(body.amount, current.base_currency)
    b.start_date, b.end_date = body.start_date, body.end_date
    b.include_subcategories, b.active = body.include_subcategories, body.active


@router.post("/budgets", status_code=201)
def create_budget(body: BudgetIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    b = Budget(user_id=current.id)
    _apply_budget(db, current, b, body)
    db.add(b)
    db.flush()
    for pct in sorted(set(body.alert_thresholds or [])):
        if not 1 <= pct <= 200:
            raise HTTPException(422, "Alert thresholds must be between 1 and 200%")
        db.add(AlertRule(user_id=current.id, name=f"{b.name} budget {pct}%", metric="budget_usage", params={"budget_id": b.id}, operator=">=", threshold=pct))
    db.flush()
    ctx = ctx_of(current)
    alerts.evaluate_state_rules(db, ctx, {"budget_usage"})
    db.commit()
    return ser.budget(b, budget_svc.budget_status(db, b, ctx.today, ctx.week_start))


@router.put("/budgets/{budget_id}")
def update_budget(budget_id: int, body: BudgetIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    b = get_owned(db, Budget, budget_id, current, "Budget")
    _apply_budget(db, current, b, body)
    ctx = ctx_of(current)
    alerts.evaluate_state_rules(db, ctx, {"budget_usage"})
    db.commit()
    return ser.budget(b, budget_svc.budget_status(db, b, ctx.today, ctx.week_start))


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    b = get_owned(db, Budget, budget_id, current, "Budget")
    for rule in db.scalars(select(AlertRule).where(AlertRule.user_id == current.id, AlertRule.metric == "budget_usage")).all():
        if str(rule.params.get("budget_id")) == str(b.id):
            db.delete(rule)
    db.delete(b)
    db.commit()
    return {"deleted": True}


# --- Goals --------------------------------------------------------------------------------------

@router.get("/goals")
def list_goals(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    today = ctx_of(current).today
    goals = db.scalars(select(Goal).where(Goal.user_id == current.id).order_by(Goal.status, Goal.target_date)).all()
    return [ser.goal(g, goal_svc.goal_status(db, g, today)) for g in goals]


def _apply_goal(db: Session, current: CurrentUser, g: Goal, body: GoalIn) -> None:
    currency = normalize_currency(body.currency or current.base_currency)
    if body.linked_account_id is not None:
        acc = get_owned(db, Account, body.linked_account_id, current, "Account")
        if acc.currency != currency:
            raise HTTPException(422, "A linked account must use the goal's currency")
    g.name, g.goal_type, g.currency = body.name, body.goal_type, currency
    g.target_minor = _minor(body.target, currency)
    g.target_date = body.target_date
    g.start_date = body.start_date or g.start_date or ctx_of(current).today
    if g.target_date and g.target_date < g.start_date:
        raise HTTPException(422, "Target date must be after the start date")
    g.linked_account_id, g.color, g.status = body.linked_account_id, body.color, body.status


@router.post("/goals", status_code=201)
def create_goal(body: GoalIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    g = Goal(user_id=current.id)
    _apply_goal(db, current, g, body)
    db.add(g)
    db.flush()
    today = ctx_of(current).today
    if body.initial_amount and not body.linked_account_id:
        db.add(GoalContribution(goal_id=g.id, user_id=current.id, amount_minor=_minor(body.initial_amount, g.currency), date=today, note="Starting amount"))
    db.flush()
    db.commit()
    return ser.goal(g, goal_svc.goal_status(db, g, today))


@router.put("/goals/{goal_id}")
def update_goal(goal_id: int, body: GoalIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    g = get_owned(db, Goal, goal_id, current, "Goal")
    _apply_goal(db, current, g, body)
    db.commit()
    return ser.goal(g, goal_svc.goal_status(db, g, ctx_of(current).today))


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_owned(db, Goal, goal_id, current, "Goal"))
    db.commit()
    return {"deleted": True}


@router.get("/goals/{goal_id}/contributions")
def list_contributions(goal_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    g = get_owned(db, Goal, goal_id, current, "Goal")
    return [ser.contribution(c) for c in sorted(g.contributions, key=lambda c: c.date, reverse=True)]


@router.post("/goals/{goal_id}/contributions", status_code=201)
def add_contribution(goal_id: int, body: ContributionIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    g = get_owned(db, Goal, goal_id, current, "Goal")
    if g.linked_account_id:
        raise HTTPException(422, "This goal tracks a linked account balance; add money to that account instead")
    amount = to_minor(body.amount, g.currency)
    if amount == 0:
        raise HTTPException(422, "Amount cannot be zero")
    today = ctx_of(current).today
    if amount < 0 and goal_svc.goal_current(db, g) + amount < 0:
        raise HTTPException(422, "Cannot withdraw more than the goal holds")
    c = GoalContribution(goal_id=g.id, user_id=current.id, amount_minor=amount, date=body.date, note=body.note)
    db.add(c)
    db.flush()
    status = goal_svc.goal_status(db, g, today)
    if status["is_complete"] and g.status == "active":
        g.status, g.completed_at = "completed", utcnow()
    alerts.evaluate_state_rules(db, ctx_of(current), {"goal_progress", "goal_behind_schedule"})
    db.commit()
    return {"contribution": ser.contribution(c), "goal": ser.goal(g, status)}


@router.delete("/goals/{goal_id}/contributions/{contribution_id}")
def delete_contribution(goal_id: int, contribution_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    c = get_owned(db, GoalContribution, contribution_id, current, "Contribution")
    if c.goal_id != goal_id:
        raise HTTPException(404, "Contribution not found")
    db.delete(c)
    db.commit()
    return {"deleted": True}


# --- Bills --------------------------------------------------------------------------------------

def _bill_out(b: Bill, today) -> dict:
    return ser.bill(b, bill_svc.bill_status(b, today), bill_svc.monthly_equivalent(b.amount_minor, b.frequency))


@router.get("/bills")
def list_bills(include_inactive: bool = False, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Bill).where(Bill.user_id == current.id)
    if not include_inactive:
        stmt = stmt.where(Bill.active.is_(True))
    today = ctx_of(current).today
    return [_bill_out(b, today) for b in db.scalars(stmt.order_by(Bill.next_due_date)).all()]


def _apply_bill(db: Session, current: CurrentUser, b: Bill, body: BillIn) -> None:
    _check_refs(db, current, body.account_id, body.category_id)
    currency = normalize_currency(body.currency or current.base_currency)
    b.name, b.provider, b.currency, b.frequency = body.name, body.provider, currency, body.frequency
    b.amount_minor = _minor(body.amount, currency)
    b.next_due_date, b.autopay, b.account_id, b.category_id, b.notes, b.active = body.next_due_date, body.autopay, body.account_id, body.category_id, body.notes, body.active


@router.post("/bills", status_code=201)
def create_bill(body: BillIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    b = Bill(user_id=current.id)
    _apply_bill(db, current, b, body)
    db.add(b)
    db.flush()
    alerts.evaluate_state_rules(db, ctx_of(current), {"bill_due_within", "bill_overdue"})
    db.commit()
    return _bill_out(b, ctx_of(current).today)


@router.put("/bills/{bill_id}")
def update_bill(bill_id: int, body: BillIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    b = get_owned(db, Bill, bill_id, current, "Bill")
    _apply_bill(db, current, b, body)
    db.commit()
    return _bill_out(b, ctx_of(current).today)


@router.delete("/bills/{bill_id}")
def delete_bill(bill_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_owned(db, Bill, bill_id, current, "Bill"))
    db.commit()
    return {"deleted": True}


@router.post("/bills/{bill_id}/pay")
def pay_bill(bill_id: int, body: BillPayIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    b = get_owned(db, Bill, bill_id, current, "Bill")
    if not b.active:
        raise HTTPException(422, "This bill is no longer active")
    ctx = ctx_of(current)
    if body.account_id is not None:
        get_owned(db, Account, body.account_id, current, "Account")
    try:
        payment = bill_svc.pay_bill(db, current.id, current.base_currency, b, body.paid_on or ctx.today, body.amount, body.account_id, body.create_transaction)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.flush()
    alerts.after_ledger_change(db, ctx, [])
    db.commit()
    db.refresh(b)
    return {"bill": _bill_out(b, ctx.today), "transaction_id": payment.transaction_id}


@router.post("/bills/{bill_id}/skip")
def skip_bill(bill_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    b = get_owned(db, Bill, bill_id, current, "Bill")
    bill_svc.skip_bill(db, current.id, b)
    db.commit()
    db.refresh(b)
    return _bill_out(b, ctx_of(current).today)


# --- Subscriptions ------------------------------------------------------------------------------

@router.get("/subscriptions")
def list_subscriptions(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    subs = db.scalars(select(Subscription).where(Subscription.user_id == current.id).order_by(Subscription.active.desc(), Subscription.next_payment_date)).all()
    items = [ser.subscription(s, sub_svc.equivalents(s)) for s in subs]
    active = [i for i in items if i["active"] and i["currency"] == current.base_currency]
    return {
        "items": items,
        "totals": {"monthly": sum(i["monthly_equivalent_minor"] for i in active), "annual": sum(i["annual_equivalent_minor"] for i in active), "active_count": len([i for i in items if i["active"]]), "currency": current.base_currency},
    }


@router.get("/subscriptions/detected")
def detect_subscriptions(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return sub_svc.detect_recurring(db, current.id, ctx_of(current).today)


def _apply_sub(db: Session, current: CurrentUser, s: Subscription, body: SubscriptionIn) -> None:
    _check_refs(db, current, body.account_id, body.category_id)
    currency = normalize_currency(body.currency or current.base_currency)
    s.name, s.currency, s.frequency = body.name, currency, body.frequency
    new_amount = _minor(body.amount, currency)
    if s.amount_minor is not None and s.id is not None and new_amount != s.amount_minor:
        s.previous_amount_minor, s.price_changed_at = s.amount_minor, utcnow()
    s.amount_minor = new_amount
    s.next_payment_date, s.account_id, s.category_id, s.notes, s.detected = body.next_payment_date, body.account_id, body.category_id, body.notes, body.detected
    s.started_on = body.started_on
    if s.active and not body.active:
        s.cancelled_on = ctx_of(current).today
    elif body.active:
        s.cancelled_on = None
    s.active = body.active
    merchant = get_or_create_merchant(db, current.id, body.merchant or body.name)
    s.merchant_id = merchant.id if merchant else None


@router.post("/subscriptions", status_code=201)
def create_subscription(body: SubscriptionIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    s = Subscription(user_id=current.id)
    _apply_sub(db, current, s, body)
    db.add(s)
    db.flush()
    db.commit()
    return ser.subscription(s, sub_svc.equivalents(s))


@router.put("/subscriptions/{sub_id}")
def update_subscription(sub_id: int, body: SubscriptionIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_owned(db, Subscription, sub_id, current, "Subscription")
    _apply_sub(db, current, s, body)
    db.commit()
    return ser.subscription(s, sub_svc.equivalents(s))


@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_owned(db, Subscription, sub_id, current, "Subscription"))
    db.commit()
    return {"deleted": True}


# --- Recurring transactions ---------------------------------------------------------------------

@router.get("/recurring")
def list_recurring(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return [ser.recurring(r) for r in db.scalars(select(RecurringTransaction).where(RecurringTransaction.user_id == current.id).order_by(RecurringTransaction.next_date)).all()]


def _apply_recurring(db: Session, current: CurrentUser, r: RecurringTransaction, body: RecurringIn) -> None:
    acc = get_owned(db, Account, body.account_id, current, "Account")
    _check_refs(db, current, body.transfer_account_id, body.category_id)
    if body.type == "transfer" and not body.transfer_account_id:
        raise HTTPException(422, "Choose the destination account for a recurring transfer")
    if body.type == "adjustment":
        raise HTTPException(422, "Adjustments cannot recur")
    for key in ("name", "type", "account_id", "transfer_account_id", "category_id", "merchant_name", "payment_method", "frequency", "next_date", "end_date", "auto_create", "active"):
        setattr(r, key, getattr(body, key))
    r.currency = acc.currency
    r.amount_minor = _minor(body.amount, acc.currency)


@router.post("/recurring", status_code=201)
def create_recurring(body: RecurringIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    r = RecurringTransaction(user_id=current.id)
    _apply_recurring(db, current, r, body)
    db.add(r)
    db.flush()
    ctx = ctx_of(current)
    created = recurring.generate_due(db, current.id, current.base_currency, ctx.today)
    alerts.after_ledger_change(db, ctx, created)
    db.commit()
    return {**ser.recurring(r), "generated": len(created)}


@router.put("/recurring/{rec_id}")
def update_recurring(rec_id: int, body: RecurringIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    r = get_owned(db, RecurringTransaction, rec_id, current, "Recurring transaction")
    _apply_recurring(db, current, r, body)
    db.commit()
    return ser.recurring(r)


@router.delete("/recurring/{rec_id}")
def delete_recurring(rec_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_owned(db, RecurringTransaction, rec_id, current, "Recurring transaction"))
    db.commit()
    return {"deleted": True}
