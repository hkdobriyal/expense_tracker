"""Portable JSON backup/restore.

Format v2 references accounts/categories by name (not database ids) so a
backup can be restored into a fresh installation, SQLite or PostgreSQL.
Restoring also accepts the v1 files exported by the previous version of the app.
For a byte-for-byte backup, copy the SQLite file in DATA_DIR while the app is stopped.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import (
    Account, AlertRule, Bill, Budget, CategorizationRule, Category, Goal, GoalContribution, Merchant, RecurringTransaction,
    Subscription, Tag, Transaction,
)
from ..money import format_decimal, to_minor
from .alerts import create_default_rules
from .catalog import seed_default_categories
from .categorization import get_or_create_merchant
from .context import UserContext
from .transactions import TransactionInput, build_transaction

VERSION = 2


def _cat_path(cat: Category | None, by_id: dict[int, Category]) -> str | None:
    if cat is None:
        return None
    if cat.parent_id and cat.parent_id in by_id:
        return f"{by_id[cat.parent_id].name}/{cat.name}"
    return cat.name


def export(db: Session, ctx: UserContext) -> dict:
    uid = ctx.user_id
    cats = db.scalars(select(Category).where(Category.user_id == uid)).all()
    by_id = {c.id: c for c in cats}
    accounts = db.scalars(select(Account).where(Account.user_id == uid)).all()
    acc_name = {a.id: a.name for a in accounts}
    path = lambda cid: _cat_path(by_id.get(cid), by_id) if cid else None  # noqa: E731
    return {
        "app": "ledgerly", "version": VERSION, "exported_at": utcnow().isoformat(), "base_currency": ctx.base_currency,
        "categories": [{"path": _cat_path(c, by_id), "kind": c.kind, "color": c.color, "icon": c.icon} for c in cats],
        "accounts": [{"name": a.name, "type": a.type, "institution": a.institution, "currency": a.currency,
                      "opening_balance": format_decimal(a.opening_balance_minor, a.currency), "opening_date": a.opening_date.isoformat() if a.opening_date else None,
                      "credit_limit": format_decimal(a.credit_limit_minor, a.currency) if a.credit_limit_minor is not None else None,
                      "include_in_net_worth": a.include_in_net_worth, "is_archived": a.is_archived} for a in accounts],
        "transactions": [{
            "date": t.date.isoformat(), "type": t.type, "account": acc_name.get(t.account_id), "transfer_account": acc_name.get(t.transfer_account_id),
            "amount": format_decimal(t.amount_minor, t.currency), "transfer_amount": format_decimal(t.transfer_amount_minor, t.transfer_account.currency) if t.transfer_amount_minor and t.transfer_account else None,
            "fx_rate": str(t.fx_rate) if t.fx_rate is not None else None, "description": t.description, "merchant": t.merchant.name if t.merchant else None,
            "category": path(t.category_id), "notes": t.notes, "payment_method": t.payment_method, "tags": [x.name for x in t.tags],
            "reviewed": t.reviewed, "source": t.source, "external_id": t.external_id, "raw_description": t.raw_description,
            "splits": [{"category": path(s.category_id), "amount": format_decimal(s.amount_minor, t.currency), "note": s.note} for s in t.splits] or None,
        } for t in db.scalars(select(Transaction).where(Transaction.user_id == uid).order_by(Transaction.date, Transaction.id)).all()],
        "budgets": [{"name": b.name, "category": path(b.category_id), "period": b.period, "amount": format_decimal(b.amount_minor, ctx.base_currency),
                     "start_date": b.start_date.isoformat() if b.start_date else None, "end_date": b.end_date.isoformat() if b.end_date else None,
                     "include_subcategories": b.include_subcategories, "active": b.active} for b in db.scalars(select(Budget).where(Budget.user_id == uid)).all()],
        "goals": [{"name": g.name, "goal_type": g.goal_type, "target": format_decimal(g.target_minor, g.currency), "currency": g.currency,
                   "target_date": g.target_date.isoformat() if g.target_date else None, "start_date": g.start_date.isoformat(), "linked_account": acc_name.get(g.linked_account_id),
                   "status": g.status, "contributions": [{"amount": format_decimal(c.amount_minor, g.currency), "date": c.date.isoformat(), "note": c.note} for c in g.contributions]}
                  for g in db.scalars(select(Goal).where(Goal.user_id == uid)).all()],
        "bills": [{"name": b.name, "provider": b.provider, "amount": format_decimal(b.amount_minor, b.currency), "currency": b.currency, "frequency": b.frequency,
                   "next_due_date": b.next_due_date.isoformat(), "autopay": b.autopay, "account": acc_name.get(b.account_id), "category": path(b.category_id), "active": b.active}
                  for b in db.scalars(select(Bill).where(Bill.user_id == uid)).all()],
        "subscriptions": [{"name": s.name, "merchant": s.merchant.name if s.merchant else None, "amount": format_decimal(s.amount_minor, s.currency), "currency": s.currency,
                           "frequency": s.frequency, "next_payment_date": s.next_payment_date.isoformat() if s.next_payment_date else None, "account": acc_name.get(s.account_id),
                           "category": path(s.category_id), "active": s.active} for s in db.scalars(select(Subscription).where(Subscription.user_id == uid)).all()],
        "rules": [{"name": r.name, "priority": r.priority, "field": r.field, "match_type": r.match_type, "pattern": r.pattern, "case_sensitive": r.case_sensitive,
                   "set_category": path(r.set_category_id), "set_merchant_name": r.set_merchant_name, "enabled": r.enabled}
                  for r in db.scalars(select(CategorizationRule).where(CategorizationRule.user_id == uid)).all()],
    }


def wipe(db: Session, user_id: int) -> None:
    for model in (Transaction, RecurringTransaction, Budget, GoalContribution, Goal, Bill, Subscription, CategorizationRule, AlertRule, Tag, Merchant):
        db.execute(delete(model).where(model.user_id == user_id))
    db.execute(delete(Category).where(Category.user_id == user_id, Category.parent_id.is_not(None)))
    db.execute(delete(Category).where(Category.user_id == user_id))
    db.execute(delete(Account).where(Account.user_id == user_id))
    db.flush()


class RestoreError(ValueError):
    pass


def _d(value) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def restore(db: Session, ctx: UserContext, payload: dict) -> dict:
    if payload.get("app") == "ledgerly" and payload.get("version") == VERSION:
        return _restore_v2(db, ctx, payload)
    envelope = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if isinstance(envelope, dict) and "transactions" in envelope and payload.get("version") in (1, None):
        return _restore_v1(db, ctx, envelope)
    raise RestoreError("Unrecognised backup file")


def _category_resolver(db: Session, user_id: int):
    cache: dict[str, int] = {}

    def resolve(path: str | None, kind: str = "expense") -> int | None:
        if not path:
            return None
        if path in cache:
            return cache[path]
        parent_name, _, child_name = path.partition("/")
        parent = db.scalar(select(Category).where(Category.user_id == user_id, Category.parent_id.is_(None), Category.name == parent_name))
        if parent is None:
            parent = Category(user_id=user_id, name=parent_name, kind=kind)
            db.add(parent)
            db.flush()
        target = parent
        if child_name:
            target = db.scalar(select(Category).where(Category.user_id == user_id, Category.parent_id == parent.id, Category.name == child_name))
            if target is None:
                target = Category(user_id=user_id, name=child_name, kind=parent.kind, parent_id=parent.id, color=parent.color, icon=parent.icon)
                db.add(target)
                db.flush()
        cache[path] = target.id
        return target.id

    return resolve


def _restore_v2(db: Session, ctx: UserContext, p: dict) -> dict:
    uid = ctx.user_id
    if p.get("base_currency") and p["base_currency"] != ctx.base_currency:
        raise RestoreError(f"Backup uses base currency {p['base_currency']} but this workspace uses {ctx.base_currency}")
    wipe(db, uid)
    for c in p.get("categories", []):
        cat_id = _category_resolver(db, uid)(c["path"], c.get("kind", "expense"))
        cat = db.get(Category, cat_id)
        cat.kind, cat.color, cat.icon = c.get("kind", cat.kind), c.get("color", ""), c.get("icon", "")
    resolve = _category_resolver(db, uid)
    accounts: dict[str, Account] = {}
    for a in p.get("accounts", []):
        acc = Account(user_id=uid, name=a["name"], type=a.get("type", "savings"), institution=a.get("institution", ""), currency=a.get("currency", ctx.base_currency),
                      opening_balance_minor=to_minor(a.get("opening_balance", "0"), a.get("currency", ctx.base_currency)), opening_date=_d(a.get("opening_date")),
                      credit_limit_minor=to_minor(a["credit_limit"], a.get("currency", ctx.base_currency)) if a.get("credit_limit") else None,
                      include_in_net_worth=a.get("include_in_net_worth", True), is_archived=a.get("is_archived", False))
        db.add(acc)
        accounts[acc.name] = acc
    db.flush()
    count = 0
    for t in p.get("transactions", []):
        acc = accounts.get(t.get("account"))
        if acc is None:
            continue
        splits = [{"category_id": resolve(s["category"]), "amount": s["amount"], "note": s.get("note", "")} for s in t["splits"]] if t.get("splits") else None
        transfer = accounts.get(t.get("transfer_account")) if t.get("transfer_account") else None
        build_transaction(db, uid, ctx.base_currency, TransactionInput(
            type=t["type"], account_id=acc.id, date=_d(t["date"]), amount=t["amount"], description=t["description"], merchant=t.get("merchant"),
            category_id=resolve(t.get("category"), "income" if t["type"] == "income" else "expense"), notes=t.get("notes", ""),
            payment_method=t.get("payment_method", ""), tags=t.get("tags", []), transfer_account_id=transfer.id if transfer else None,
            transfer_amount=Decimal(t["transfer_amount"]) if t.get("transfer_amount") else None, fx_rate=Decimal(t["fx_rate"]) if t.get("fx_rate") else None,
            reviewed=t.get("reviewed", True), splits=splits, source="restore", external_id=t.get("external_id"), raw_description=t.get("raw_description", ""),
        ))
        count += 1
    for b in p.get("budgets", []):
        db.add(Budget(user_id=uid, name=b["name"], category_id=resolve(b.get("category")), period=b.get("period", "monthly"), amount_minor=to_minor(b["amount"], ctx.base_currency),
                      start_date=_d(b.get("start_date")), end_date=_d(b.get("end_date")), include_subcategories=b.get("include_subcategories", True), active=b.get("active", True)))
    for g in p.get("goals", []):
        linked = accounts.get(g.get("linked_account"))
        goal = Goal(user_id=uid, name=g["name"], goal_type=g.get("goal_type", "custom"), target_minor=to_minor(g["target"], g["currency"]), currency=g["currency"],
                    target_date=_d(g.get("target_date")), start_date=_d(g.get("start_date")) or ctx.today, linked_account_id=linked.id if linked else None, status=g.get("status", "active"))
        db.add(goal)
        db.flush()
        for c in g.get("contributions", []):
            db.add(GoalContribution(goal_id=goal.id, user_id=uid, amount_minor=to_minor(c["amount"], g["currency"]), date=_d(c["date"]), note=c.get("note", "")))
    for b in p.get("bills", []):
        acc = accounts.get(b.get("account"))
        db.add(Bill(user_id=uid, name=b["name"], provider=b.get("provider", ""), amount_minor=to_minor(b["amount"], b["currency"]), currency=b["currency"], frequency=b.get("frequency", "monthly"),
                    next_due_date=_d(b["next_due_date"]), autopay=b.get("autopay", False), account_id=acc.id if acc else None, category_id=resolve(b.get("category")), active=b.get("active", True)))
    for s in p.get("subscriptions", []):
        acc = accounts.get(s.get("account"))
        merchant = get_or_create_merchant(db, uid, s.get("merchant") or s["name"])
        db.add(Subscription(user_id=uid, name=s["name"], merchant_id=merchant.id if merchant else None, amount_minor=to_minor(s["amount"], s["currency"]), currency=s["currency"],
                            frequency=s.get("frequency", "monthly"), next_payment_date=_d(s.get("next_payment_date")), account_id=acc.id if acc else None,
                            category_id=resolve(s.get("category")), active=s.get("active", True)))
    for r in p.get("rules", []):
        db.add(CategorizationRule(user_id=uid, name=r.get("name", ""), priority=r.get("priority", 100), field=r.get("field", "any"), match_type=r.get("match_type", "contains"),
                                  pattern=r["pattern"], case_sensitive=r.get("case_sensitive", False), set_category_id=resolve(r.get("set_category")),
                                  set_merchant_name=r.get("set_merchant_name"), enabled=r.get("enabled", True)))
    create_default_rules(db, uid)
    db.flush()
    return {"format": "v2", "accounts": len(accounts), "transactions": count}


# Old category names from the previous app → new category paths.
_V1_CATEGORIES = {
    "groceries": "Food/Groceries", "eating out": "Food/Restaurants", "food & dining": "Food/Restaurants", "rent & utilities": "Housing/Rent",
    "utilities": "Bills & utilities/Electricity", "transport": "Transport", "transit": "Transport", "shopping": "Shopping",
    "health": "Health", "subscriptions": "Entertainment/Streaming", "entertainment": "Entertainment", "education": "Education",
    "family": "Personal & family", "salary": "Salary", "other": "Other",
}


def _restore_v1(db: Session, ctx: UserContext, data: dict) -> dict:
    """Import a backup from the previous (float-based, single-table) version of the app."""
    uid = ctx.user_id
    wipe(db, uid)
    seed_default_categories(db, uid)
    resolve = _category_resolver(db, uid)
    accounts = []
    for a in data.get("accounts") or []:
        acc = Account(user_id=uid, name=str(a.get("name") or "Account")[:120], type={"credit": "credit_card"}.get(a.get("account_type"), a.get("account_type") or "savings"),
                      institution=a.get("institution") or "", currency="INR", opening_balance_minor=to_minor(Decimal(str(a.get("opening_balance") or 0)).quantize(Decimal("0.01")), "INR"))
        db.add(acc)
        accounts.append(acc)
    db.flush()
    default = accounts[0] if accounts else None
    if default is None:
        default = Account(user_id=uid, name="Imported (legacy)", type="savings", currency="INR")
        db.add(default)
        db.flush()
    count = 0
    for t in data.get("transactions") or []:
        kind = t.get("kind") or "expense"
        category = _V1_CATEGORIES.get(str(t.get("category") or "").lower())
        try:
            build_transaction(db, uid, ctx.base_currency, TransactionInput(
                type=kind if kind in ("expense", "income", "investment") else "expense", account_id=default.id,
                date=_d(t.get("date")) or ctx.today, amount=Decimal(str(t.get("amount") or 0)).quantize(Decimal("0.01")),
                description=str(t.get("title") or "Transaction")[:255], merchant=t.get("merchant"),
                category_id=resolve(category, "income" if kind == "income" else "expense") if category else None, notes=t.get("notes") or "",
                payment_method=t.get("payment_method") or "", is_recurring=bool(t.get("recurring")), source="restore",
            ))
            count += 1
        except ValueError:
            continue
    for b in data.get("budgets") or []:
        category = _V1_CATEGORIES.get(str(b.get("category") or "").lower())
        db.add(Budget(user_id=uid, name=str(b.get("name") or "Budget"), category_id=resolve(category) if category else None, period=b.get("period") if b.get("period") in ("weekly", "monthly", "yearly") else "monthly",
                      amount_minor=to_minor(Decimal(str(b.get("amount") or 1)).quantize(Decimal("0.01")), "INR")))
    for g in data.get("goals") or []:
        goal = Goal(user_id=uid, name=str(g.get("name") or "Goal"), target_minor=to_minor(Decimal(str(g.get("target_amount") or 1)).quantize(Decimal("0.01")), "INR"),
                    currency="INR", target_date=_d(g.get("target_date")), start_date=_d(g.get("created_at")) or ctx.today)
        db.add(goal)
        db.flush()
        if g.get("current_amount"):
            db.add(GoalContribution(goal_id=goal.id, user_id=uid, amount_minor=to_minor(Decimal(str(g["current_amount"])).quantize(Decimal("0.01")), "INR"), date=ctx.today, note="Imported balance"))
    for b in data.get("bills") or []:
        due = _d(b.get("due_date"))
        if due is None:
            continue
        db.add(Bill(user_id=uid, name=str(b.get("name") or "Bill"), amount_minor=to_minor(Decimal(str(b.get("amount") or 1)).quantize(Decimal("0.01")), "INR"), currency="INR",
                    frequency=b.get("frequency") if b.get("frequency") in ("weekly", "monthly", "yearly") else "monthly", next_due_date=due, active=b.get("status") != "paid"))
    create_default_rules(db, uid)
    db.flush()
    return {"format": "v1", "accounts": len(accounts), "transactions": count, "restored_at": datetime.now().isoformat()}
