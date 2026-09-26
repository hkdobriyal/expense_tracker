"""The financial engine: the single source of truth for balances and totals.

Every screen (dashboard, budgets, analytics, reports, alerts) calls these
functions instead of re-implementing sums, so a changed transaction is
reflected everywhere consistently.

Definitions (all in the user's base currency unless stated):

* ``income``          – sum of income transactions
* ``expenses``        – expense transactions minus refunds
* ``invested``        – money moved out to investments (SIPs, stocks)
* ``savings``         – income − expenses (investing counts as saving)
* ``net_cash_flow``   – income − expenses − invested (actual change in cash)
* ``savings_rate``    – savings ÷ income
* transfers between the user's own accounts are excluded from all of the above.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import Session

from ..models import Account, Category, Merchant, Transaction, TransactionSplit
from .fx import latest_rate
from ..money import convert_minor, percent

ACCOUNT_SIGN = case(
    (Transaction.type.in_(("income", "refund")), Transaction.amount_minor),
    (Transaction.type.in_(("expense", "investment", "transfer")), -Transaction.amount_minor),
    else_=Transaction.amount_minor,  # adjustment carries its own sign
)


# ---------------------------------------------------------------------------
# Balances (account currency)
# ---------------------------------------------------------------------------


def account_balances(db: Session, user_id: int, as_of: date | None = None, account_ids: list[int] | None = None) -> dict[int, int]:
    """Balance of each account in its own currency, optionally as of a date (inclusive)."""
    acc_stmt = select(Account).where(Account.user_id == user_id)
    if account_ids is not None:
        acc_stmt = acc_stmt.where(Account.id.in_(account_ids))
    accounts = db.scalars(acc_stmt).all()
    balances: dict[int, int] = {}
    for acc in accounts:
        opened = acc.opening_date is None or as_of is None or acc.opening_date <= as_of
        balances[acc.id] = acc.opening_balance_minor if opened else 0

    date_filter = [Transaction.date <= as_of] if as_of else []
    outgoing = db.execute(
        select(Transaction.account_id, func.coalesce(func.sum(ACCOUNT_SIGN), 0))
        .where(Transaction.user_id == user_id, *date_filter)
        .group_by(Transaction.account_id)
    ).all()
    for account_id, total in outgoing:
        if account_id in balances:
            balances[account_id] += int(total)

    incoming = db.execute(
        select(Transaction.transfer_account_id, func.coalesce(func.sum(func.coalesce(Transaction.transfer_amount_minor, Transaction.amount_minor)), 0))
        .where(Transaction.user_id == user_id, Transaction.type == "transfer", *date_filter)
        .group_by(Transaction.transfer_account_id)
    ).all()
    for account_id, total in incoming:
        if account_id in balances:
            balances[account_id] += int(total)
    return balances


@dataclass
class ConvertedBalance:
    account_id: int
    balance_minor: int
    currency: str
    base_minor: int | None  # None when no exchange rate is known


def balances_in_base(db: Session, user_id: int, base_currency: str, as_of: date | None = None, accounts: list[Account] | None = None) -> list[ConvertedBalance]:
    if accounts is None:
        accounts = db.scalars(select(Account).where(Account.user_id == user_id)).all()
    raw = account_balances(db, user_id, as_of, [a.id for a in accounts])
    out = []
    for acc in accounts:
        bal = raw.get(acc.id, 0)
        rate = latest_rate(db, user_id, acc.currency, base_currency, as_of)
        out.append(ConvertedBalance(acc.id, bal, acc.currency, convert_minor(bal, rate, acc.currency, base_currency) if rate is not None else None))
    return out


# ---------------------------------------------------------------------------
# Period totals (base currency)
# ---------------------------------------------------------------------------


@dataclass
class Totals:
    income: int = 0
    expenses_gross: int = 0
    refunds: int = 0
    invested: int = 0
    adjustments: int = 0
    transfers: int = 0
    transaction_count: int = 0

    @property
    def expenses(self) -> int:
        return self.expenses_gross - self.refunds

    @property
    def savings(self) -> int:
        return self.income - self.expenses

    @property
    def net_cash_flow(self) -> int:
        return self.income - self.expenses - self.invested

    @property
    def savings_rate(self) -> float:
        return percent(self.savings, self.income) if self.income > 0 else 0.0

    def as_dict(self) -> dict:
        data = asdict(self)
        data.update(expenses=self.expenses, savings=self.savings, net_cash_flow=self.net_cash_flow, savings_rate=self.savings_rate)
        return data


def _scope(user_id: int, start: date | None, end: date | None, account_id: int | None = None):
    conds = [Transaction.user_id == user_id]
    if start:
        conds.append(Transaction.date >= start)
    if end:
        conds.append(Transaction.date <= end)
    if account_id:
        conds.append(or_(Transaction.account_id == account_id, Transaction.transfer_account_id == account_id))
    return conds


def period_totals(db: Session, user_id: int, start: date | None, end: date | None, account_id: int | None = None) -> Totals:
    rows = db.execute(
        select(Transaction.type, func.coalesce(func.sum(Transaction.base_amount_minor), 0), func.count())
        .where(*_scope(user_id, start, end, account_id))
        .group_by(Transaction.type)
    ).all()
    t = Totals()
    for kind, total, count in rows:
        total = int(total)
        t.transaction_count += int(count)
        if kind == "income":
            t.income += total
        elif kind == "expense":
            t.expenses_gross += total
        elif kind == "refund":
            t.refunds += total
        elif kind == "investment":
            t.invested += total
        elif kind == "adjustment":
            t.adjustments += total
        elif kind == "transfer":
            t.transfers += total
    return t


def daily_series(db: Session, user_id: int, start: date, end: date, account_id: int | None = None) -> dict[date, Totals]:
    rows = db.execute(
        select(Transaction.date, Transaction.type, func.coalesce(func.sum(Transaction.base_amount_minor), 0), func.count())
        .where(*_scope(user_id, start, end, account_id))
        .group_by(Transaction.date, Transaction.type)
    ).all()
    series: dict[date, Totals] = defaultdict(Totals)
    for day, kind, total, count in rows:
        t = series[day]
        t.transaction_count += int(count)
        total = int(total)
        if kind == "income":
            t.income += total
        elif kind == "expense":
            t.expenses_gross += total
        elif kind == "refund":
            t.refunds += total
        elif kind == "investment":
            t.invested += total
    return series


def bucketed_series(db: Session, user_id: int, start: date, end: date, granularity: str, week_start: int = 0) -> list[dict]:
    """Income/expense/net per day, week or month, including empty buckets."""
    daily = daily_series(db, user_id, start, end)

    def bucket_key(d: date) -> date:
        if granularity == "month":
            return d.replace(day=1)
        if granularity == "week":
            return d - timedelta(days=(d.weekday() - week_start) % 7)
        return d

    buckets: dict[date, Totals] = {}
    cursor = start
    while cursor <= end:
        buckets.setdefault(bucket_key(cursor), Totals())
        cursor += timedelta(days=1)
    for d, t in daily.items():
        b = buckets.setdefault(bucket_key(d), Totals())
        b.income += t.income
        b.expenses_gross += t.expenses_gross
        b.refunds += t.refunds
        b.invested += t.invested
        b.transaction_count += t.transaction_count
    return [
        {"bucket": k.isoformat(), "income": v.income, "expenses": v.expenses, "invested": v.invested, "net": v.net_cash_flow, "savings": v.savings, "count": v.transaction_count}
        for k, v in sorted(buckets.items())
    ]


# ---------------------------------------------------------------------------
# Category / merchant / account breakdowns (base currency, net of refunds)
# ---------------------------------------------------------------------------

_has_splits = exists().where(TransactionSplit.transaction_id == Transaction.id)


def category_amounts(db: Session, user_id: int, start: date | None, end: date | None, kind: str = "expense", account_id: int | None = None) -> dict[int | None, int]:
    """Amount per leaf category. Splits override the transaction's own category."""
    types = ("expense", "refund") if kind == "expense" else ("income",)
    signed_txn = case((Transaction.type == "refund", -Transaction.base_amount_minor), else_=Transaction.base_amount_minor)
    signed_split = case((Transaction.type == "refund", -TransactionSplit.base_amount_minor), else_=TransactionSplit.base_amount_minor)
    scope = _scope(user_id, start, end, account_id) + [Transaction.type.in_(types)]

    totals: dict[int | None, int] = defaultdict(int)
    for cat_id, amount in db.execute(
        select(Transaction.category_id, func.sum(signed_txn)).where(*scope, ~_has_splits).group_by(Transaction.category_id)
    ).all():
        totals[cat_id] += int(amount or 0)
    for cat_id, amount in db.execute(
        select(TransactionSplit.category_id, func.sum(signed_split))
        .join(Transaction, TransactionSplit.transaction_id == Transaction.id)
        .where(*scope)
        .group_by(TransactionSplit.category_id)
    ).all():
        totals[cat_id] += int(amount or 0)
    return dict(totals)


def descendant_ids(categories: list[Category], root_id: int) -> set[int]:
    children: dict[int | None, list[int]] = defaultdict(list)
    for c in categories:
        children[c.parent_id].append(c.id)
    result, stack = {root_id}, [root_id]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in result:
                result.add(child)
                stack.append(child)
    return result


def category_breakdown(db: Session, user_id: int, start: date | None, end: date | None, kind: str = "expense") -> list[dict]:
    """Top-level categories with their subcategories, sorted by amount."""
    amounts = category_amounts(db, user_id, start, end, kind)
    categories = db.scalars(select(Category).where(Category.user_id == user_id)).all()
    by_id = {c.id: c for c in categories}

    def top_of(cid: int | None) -> Category | None:
        cat = by_id.get(cid) if cid is not None else None
        while cat is not None and cat.parent_id is not None and cat.parent_id in by_id:
            cat = by_id[cat.parent_id]
        return cat

    groups: dict[int | None, dict] = {}
    total = sum(v for v in amounts.values() if v > 0)
    for cid, amount in amounts.items():
        if amount == 0:
            continue
        top = top_of(cid)
        key = top.id if top else None
        group = groups.setdefault(key, {
            "category_id": key,
            "name": top.name if top else "Uncategorised",
            "color": top.color if top else "#8a94a6",
            "icon": top.icon if top else "",
            "amount": 0,
            "children": [],
        })
        group["amount"] += amount
        leaf = by_id.get(cid) if cid is not None else None
        if leaf is not None and leaf.id != key:
            group["children"].append({"category_id": leaf.id, "name": leaf.name, "amount": amount})
    result = sorted(groups.values(), key=lambda g: g["amount"], reverse=True)
    for g in result:
        g["share"] = percent(g["amount"], total)
        g["children"].sort(key=lambda c: c["amount"], reverse=True)
    return result


def spent_in_categories(db: Session, user_id: int, category_ids: set[int] | None, start: date, end: date) -> int:
    """Net expense in a set of categories (None = all spending) – used by budgets and alerts."""
    amounts = category_amounts(db, user_id, start, end, "expense")
    if category_ids is None:
        return sum(amounts.values())
    return sum(v for k, v in amounts.items() if k in category_ids)


def merchant_breakdown(db: Session, user_id: int, start: date | None, end: date | None, limit: int = 10) -> list[dict]:
    signed = case((Transaction.type == "refund", -Transaction.base_amount_minor), else_=Transaction.base_amount_minor)
    rows = db.execute(
        select(Merchant.id, Merchant.name, func.sum(signed), func.count())
        .join(Merchant, Transaction.merchant_id == Merchant.id)
        .where(*_scope(user_id, start, end), Transaction.type.in_(("expense", "refund")))
        .group_by(Merchant.id, Merchant.name)
        .order_by(func.sum(signed).desc())
        .limit(limit)
    ).all()
    return [{"merchant_id": mid, "name": name, "amount": int(total or 0), "count": int(count)} for mid, name, total, count in rows]


def account_spending(db: Session, user_id: int, start: date | None, end: date | None) -> list[dict]:
    signed = case((Transaction.type == "refund", -Transaction.base_amount_minor), else_=Transaction.base_amount_minor)
    rows = db.execute(
        select(Account.id, Account.name, func.sum(signed), func.count())
        .join(Account, Transaction.account_id == Account.id)
        .where(*_scope(user_id, start, end), Transaction.type.in_(("expense", "refund")))
        .group_by(Account.id, Account.name)
        .order_by(func.sum(signed).desc())
    ).all()
    return [{"account_id": aid, "name": name, "amount": int(total or 0), "count": int(count)} for aid, name, total, count in rows]


def income_sources(db: Session, user_id: int, start: date | None, end: date | None) -> list[dict]:
    return category_breakdown(db, user_id, start, end, kind="income")


def cash_flow(db: Session, user_id: int, base_currency: str, start: date, end: date) -> dict:
    """Opening balance + income − expenses − invested (+ adjustments) = closing balance.

    Opening/closing cover liquid accounts only (current, savings, cash, wallet,
    credit cards) because that is where cash flow happens.
    """
    liquid_types = ("current", "savings", "cash", "wallet", "credit_card")
    accounts = db.scalars(select(Account).where(Account.user_id == user_id, Account.type.in_(liquid_types))).all()
    opening = balances_in_base(db, user_id, base_currency, start - timedelta(days=1), accounts)
    closing = balances_in_base(db, user_id, base_currency, end, accounts)
    missing = sorted({b.currency for b in opening + closing if b.base_minor is None})
    totals = period_totals(db, user_id, start, end)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "opening_balance": sum(b.base_minor or 0 for b in opening),
        "income": totals.income,
        "expenses": totals.expenses,
        "invested": totals.invested,
        "adjustments": totals.adjustments,
        "net_cash_flow": totals.net_cash_flow,
        "closing_balance": sum(b.base_minor or 0 for b in closing),
        "missing_rates": missing,
    }


def median(values: list[int]) -> Decimal:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return Decimal(0)
    mid = n // 2
    return Decimal(ordered[mid]) if n % 2 else (Decimal(ordered[mid - 1]) + Decimal(ordered[mid])) / 2


def category_history(db: Session, user_id: int, category_ids: set[int], start: date, end: date) -> list[int]:
    rows = db.execute(
        select(Transaction.base_amount_minor)
        .where(*_scope(user_id, start, end), Transaction.type == "expense", Transaction.category_id.in_(category_ids))
    ).all()
    return [int(r[0]) for r in rows]


__all__ = [
    "account_balances", "balances_in_base", "period_totals", "Totals", "daily_series", "bucketed_series",
    "category_amounts", "category_breakdown", "spent_in_categories", "merchant_breakdown", "account_spending",
    "income_sources", "cash_flow", "descendant_ids", "median", "category_history",
]
