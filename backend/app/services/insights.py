"""Deterministic financial insights computed from the ledger.

Every insight carries the numbers it was derived from, so nothing is invented.
Thresholds are intentionally conservative to avoid noise.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Bill, Subscription, Transaction
from ..money import format_display, percent
from . import budgets as budget_svc
from . import ledger
from .context import UserContext
from .periods import add_months, month_bounds

MIN_CHANGE_PCT = 20
MIN_ABS_CHANGE_MINOR = 50_000  # ₹500 – below this a change is not worth mentioning


def generate(db: Session, ctx: UserContext) -> list[dict]:
    today = ctx.today
    fmt = lambda m: format_display(m, ctx.base_currency)  # noqa: E731
    cur_start, cur_end = month_bounds(today)
    prev_start, prev_end = month_bounds(add_months(today, -1))
    # Compare month-to-date with the same number of days last month (fair comparison).
    elapsed = (today - cur_start).days
    prev_same_end = min(prev_start + timedelta(days=elapsed), prev_end)
    insights: list[dict] = []

    current = {c["category_id"]: c for c in ledger.category_breakdown(db, ctx.user_id, cur_start, today)}
    previous = {c["category_id"]: c for c in ledger.category_breakdown(db, ctx.user_id, prev_start, prev_same_end)}
    for cid, cat in current.items():
        before = previous.get(cid, {}).get("amount", 0)
        now = cat["amount"]
        if before > 0 and abs(now - before) >= MIN_ABS_CHANGE_MINOR:
            change = percent(now - before, before)
            if abs(change) >= MIN_CHANGE_PCT:
                insights.append({
                    "kind": "category_change", "severity": "warning" if change > 0 else "success",
                    "title": f"{cat['name']} spending {'up' if change > 0 else 'down'} {abs(change):.0f}%",
                    "message": f"You spent {fmt(now)} on {cat['name']} so far this month vs {fmt(before)} by this point last month.",
                    "data": {"category_id": cid, "current": now, "previous": before, "change_pct": change},
                })

    # Versus the 6-month average (full months).
    six_start = month_bounds(add_months(today, -6))[0]
    history = {c["category_id"]: c["amount"] for c in ledger.category_breakdown(db, ctx.user_id, six_start, prev_end)}
    for cid, cat in current.items():
        avg = history.get(cid, 0) // 6
        if avg > 0 and cat["amount"] - avg >= MIN_ABS_CHANGE_MINOR and cat["amount"] > avg * 1.2:
            insights.append({
                "kind": "above_average", "severity": "info",
                "title": f"{cat['name']} above your 6-month average",
                "message": f"{fmt(cat['amount'] - avg)} more on {cat['name']} than your 6-month monthly average of {fmt(avg)}.",
                "data": {"category_id": cid, "current": cat["amount"], "average": avg},
            })

    for budget, st in budget_svc.all_budget_statuses(db, ctx.user_id, today, ctx.week_start):
        if st["usage_pct"] >= 80:
            insights.append({
                "kind": "budget", "severity": "critical" if st["usage_pct"] >= 100 else "warning",
                "title": f"{budget.name} budget {st['usage_pct']:.0f}% used",
                "message": f"{fmt(st['spent'])} of {fmt(st['limit'])} spent with {st['days_left']} day(s) left in the period.",
                "data": {"budget_id": budget.id, **st},
            })
        elif st["ahead_of_pace"] and st["spent"] - st["expected_spend_to_date"] >= MIN_ABS_CHANGE_MINOR:
            insights.append({
                "kind": "budget_pace", "severity": "info",
                "title": f"{budget.name} is ahead of pace",
                "message": f"You've spent {fmt(st['spent'])}; an even pace would be {fmt(st['expected_spend_to_date'])} by today.",
                "data": {"budget_id": budget.id, **st},
            })

    week_end = today + timedelta(days=7)
    renewing = db.scalars(select(Subscription).where(
        Subscription.user_id == ctx.user_id, Subscription.active.is_(True),
        Subscription.next_payment_date >= today, Subscription.next_payment_date <= week_end,
    )).all()
    if renewing:
        total = sum(s.amount_minor for s in renewing if s.currency == ctx.base_currency)
        names = ", ".join(s.name for s in renewing[:4])
        insights.append({
            "kind": "subscriptions_week", "severity": "info",
            "title": f"{len(renewing)} subscription{'s' if len(renewing) > 1 else ''} renew this week",
            "message": f"{names} – {fmt(total)} in total.", "data": {"count": len(renewing), "total": total},
        })

    overdue = db.scalar(select(func.count()).select_from(Bill).where(Bill.user_id == ctx.user_id, Bill.active.is_(True), Bill.next_due_date < today)) or 0
    if overdue:
        insights.append({"kind": "bills_overdue", "severity": "critical", "title": f"{overdue} overdue bill{'s' if overdue > 1 else ''}", "message": "Mark them paid or skip them on the Bills page.", "data": {"count": overdue}})

    this_month = ledger.period_totals(db, ctx.user_id, cur_start, today)
    last_month = ledger.period_totals(db, ctx.user_id, prev_start, prev_end)
    if this_month.income > 0 and last_month.income > 0 and today.day >= 20:
        delta = this_month.savings_rate - last_month.savings_rate
        if abs(delta) >= 5:
            insights.append({
                "kind": "savings_rate", "severity": "success" if delta > 0 else "warning",
                "title": f"Savings rate {'improved' if delta > 0 else 'dropped'} to {this_month.savings_rate:.0f}%",
                "message": f"Last month you saved {last_month.savings_rate:.0f}% of your income.",
                "data": {"current": this_month.savings_rate, "previous": last_month.savings_rate},
            })

    biggest = db.scalar(select(Transaction).where(
        Transaction.user_id == ctx.user_id, Transaction.type == "expense", Transaction.date >= cur_start, Transaction.date <= today
    ).order_by(Transaction.base_amount_minor.desc()).limit(1))
    if biggest is not None:
        insights.append({
            "kind": "largest_expense", "severity": "info", "title": "Largest expense this month",
            "message": f"{biggest.description} – {fmt(biggest.base_amount_minor)} on {biggest.date:%d %b}.",
            "data": {"transaction_id": biggest.id, "amount": biggest.base_amount_minor},
        })

    unreviewed = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.user_id == ctx.user_id, Transaction.reviewed.is_(False))) or 0
    if unreviewed:
        insights.append({"kind": "review", "severity": "info", "title": f"{unreviewed} transaction{'s' if unreviewed > 1 else ''} to review", "message": "Imported and synced transactions wait for a quick check of their category.", "data": {"count": unreviewed}})

    order = {"critical": 0, "warning": 1, "success": 2, "info": 3}
    insights.sort(key=lambda i: order.get(i["severity"], 9))
    return insights
