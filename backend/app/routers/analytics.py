"""Dashboard, analytics, cash flow, net worth, insights and reports – all derived from the ledger."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import serializers as ser
from ..db import get_db
from ..deps import CurrentUser, get_current_user
from ..models import Account, AlertRule, Bill, Budget, Goal, NetWorthSnapshot, Subscription, Transaction
from ..services import bills as bill_svc
from ..services import budgets as budget_svc
from ..services import insights as insight_svc
from ..services import ledger, networth, notifications, reports
from ..services import subscriptions as sub_svc
from ..services.periods import add_months, month_bounds, resolve_range
from .common import ctx_of

router = APIRouter(prefix="/api", tags=["analytics"])

LIQUID_TYPES = ("current", "savings", "cash", "wallet")


def _range(current: CurrentUser, preset: Optional[str], start: Optional[date], end: Optional[date]):
    ctx = ctx_of(current)
    try:
        return ctx, resolve_range(preset, start, end, ctx.today, ctx.week_start)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _delta(current: int | float, previous: int | float) -> dict:
    change = current - previous
    pct = round(change / abs(previous) * 100, 1) if previous else None
    return {"previous": previous, "change": change, "change_pct": pct}


@router.get("/dashboard")
def dashboard(preset: Optional[str] = "this_month", start: Optional[date] = None, end: Optional[date] = None,
              current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx, rng = _range(current, preset, start, end)
    uid, cur = current.id, current.base_currency
    today = ctx.today
    totals = ledger.period_totals(db, uid, rng.start, rng.end)
    prev = rng.previous()
    prev_totals = ledger.period_totals(db, uid, prev.start, prev.end)

    accounts = db.scalars(select(Account).where(Account.user_id == uid, Account.is_archived.is_(False))).all()
    balances = ledger.balances_in_base(db, uid, cur, None, accounts)
    by_id = {a.id: a for a in accounts}
    liquid = sum(b.base_minor or 0 for b in balances if by_id[b.account_id].type in LIQUID_TYPES)
    nw = networth.net_worth(db, uid, cur)

    budget_rows = budget_svc.all_budget_statuses(db, uid, today, ctx.week_start)
    overall = next(((b, st) for b, st in budget_rows if b.category_id is None and b.period == "monthly"), None)
    category_budgets = [(b, st) for b, st in budget_rows if b.category_id is not None]
    if overall:
        budget_summary = {"limit": overall[1]["limit"], "spent": overall[1]["spent"], "remaining": overall[1]["remaining"], "source": "overall"}
    else:
        budget_summary = {
            "limit": sum(st["limit"] for _, st in category_budgets), "spent": sum(st["spent"] for _, st in category_budgets),
            "remaining": sum(st["remaining"] for _, st in category_budgets), "source": "categories",
        }
    budget_summary.update(count=len(budget_rows), over_count=sum(1 for _, st in budget_rows if st["status"] == "over"),
                          top=[ser.budget(b, st) for b, st in sorted(category_budgets, key=lambda x: -x[1]["usage_pct"])[:5]])

    upcoming = db.scalars(select(Bill).where(Bill.user_id == uid, Bill.active.is_(True), Bill.next_due_date <= today + timedelta(days=14)).order_by(Bill.next_due_date)).all()
    subs = db.scalars(select(Subscription).where(Subscription.user_id == uid, Subscription.active.is_(True))).all()
    sub_monthly = sum(sub_svc.equivalents(s)["monthly_equivalent"] for s in subs if s.currency == cur)
    renewals = sorted([s for s in subs if s.next_payment_date and s.next_payment_date <= today + timedelta(days=14)], key=lambda s: s.next_payment_date)

    trend_start = month_bounds(add_months(today, -5))[0]
    recent = db.scalars(
        select(Transaction).where(Transaction.user_id == uid).order_by(Transaction.date.desc(), Transaction.id.desc()).limit(8)
        .options(selectinload(Transaction.tags), selectinload(Transaction.splits), selectinload(Transaction.attachments))
    ).all()
    counts = {
        "accounts": len(accounts),
        "transactions": db.scalar(select(func.count()).select_from(Transaction).where(Transaction.user_id == uid)) or 0,
        "budgets": len(budget_rows),
        "goals": db.scalar(select(func.count()).select_from(Goal).where(Goal.user_id == uid)) or 0,
        "custom_alerts": db.scalar(select(func.count()).select_from(AlertRule).where(AlertRule.user_id == uid, AlertRule.metric.in_(("budget_usage", "account_balance", "large_transaction", "category_spending", "total_spending")))) or 0,
        "unreviewed": db.scalar(select(func.count()).select_from(Transaction).where(Transaction.user_id == uid, Transaction.reviewed.is_(False))) or 0,
    }
    settings = current.settings
    notifications_ready = settings.channel_in_app and (settings.channel_email or counts["custom_alerts"] > 0)
    onboarding = [
        {"key": "currency", "label": "Choose base currency", "done": True},
        {"key": "account", "label": "Add an account", "done": counts["accounts"] > 0},
        {"key": "transactions", "label": "Add or import transactions", "done": counts["transactions"] > 0},
        {"key": "budget", "label": "Create your first budget", "done": counts["budgets"] > 0},
        {"key": "goal", "label": "Set a savings goal", "done": counts["goals"] > 0},
        {"key": "notifications", "label": "Configure alerts", "done": bool(notifications_ready)},
    ]
    return {
        "currency": cur,
        "period": {"start": rng.start.isoformat(), "end": rng.end.isoformat(), "label": rng.label, "previous_label": prev.label},
        "totals": totals.as_dict(),
        "comparison": {k: _delta(getattr(totals, k), getattr(prev_totals, k)) for k in ("income", "expenses", "savings", "net_cash_flow", "invested")},
        "total_balance": liquid,
        "net_worth": nw,
        "budget": budget_summary,
        "upcoming_bills": [{"id": b.id, "name": b.name, "amount_minor": b.amount_minor, "currency": b.currency, "next_due_date": b.next_due_date.isoformat(), "status": bill_svc.bill_status(b, today), "autopay": b.autopay} for b in upcoming],
        "subscriptions": {"monthly_total": sub_monthly, "active_count": len(subs), "renewals": [{"id": s.id, "name": s.name, "amount_minor": s.amount_minor, "currency": s.currency, "next_payment_date": s.next_payment_date.isoformat()} for s in renewals]},
        "trend": ledger.bucketed_series(db, uid, trend_start, today, "month"),
        "categories": ledger.category_breakdown(db, uid, rng.start, rng.end),
        "accounts": [{"id": b.account_id, "name": by_id[b.account_id].name, "type": by_id[b.account_id].type, "balance_minor": b.balance_minor, "currency": b.currency, "base_minor": b.base_minor} for b in balances],
        "recent": [ser.transaction(t) for t in recent],
        "insights": insight_svc.generate(db, ctx)[:6],
        "counts": counts,
        "onboarding": {"steps": onboarding, "dismissed": settings.onboarding_dismissed, "complete": all(s["done"] for s in onboarding)},
        "unread_notifications": notifications.unread_count(db, uid),
    }


@router.get("/analytics/summary")
def analytics_summary(preset: Optional[str] = "this_month", start: Optional[date] = None, end: Optional[date] = None,
                      current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx, rng = _range(current, preset, start, end)
    uid = current.id
    prev = rng.previous()
    totals = ledger.period_totals(db, uid, rng.start, rng.end)
    prev_totals = ledger.period_totals(db, uid, prev.start, prev.end)
    granularity = "day" if rng.days <= 31 else "week" if rng.days <= 120 else "month"
    prev_categories = {c["category_id"]: c["amount"] for c in ledger.category_breakdown(db, uid, prev.start, prev.end)}
    categories = ledger.category_breakdown(db, uid, rng.start, rng.end)
    for c in categories:
        before = prev_categories.get(c["category_id"], 0)
        c["previous"] = before
        c["change_pct"] = round((c["amount"] - before) / before * 100, 1) if before else None
    days = max(1, min(rng.days, (ctx.today - rng.start).days + 1))
    return {
        "currency": current.base_currency,
        "period": {"start": rng.start.isoformat(), "end": rng.end.isoformat(), "label": rng.label, "granularity": granularity, "previous": {"start": prev.start.isoformat(), "end": prev.end.isoformat(), "label": prev.label}},
        "totals": totals.as_dict(), "previous_totals": prev_totals.as_dict(),
        "average_daily_spend": totals.expenses // days,
        "series": ledger.bucketed_series(db, uid, rng.start, rng.end, granularity, ctx.week_start),
        "categories": categories,
        "merchants": ledger.merchant_breakdown(db, uid, rng.start, rng.end, 12),
        "accounts": ledger.account_spending(db, uid, rng.start, rng.end),
        "income_sources": ledger.income_sources(db, uid, rng.start, rng.end),
    }


@router.get("/analytics/series")
def analytics_series(granularity: Literal["day", "week", "month"] = "month", preset: Optional[str] = "1y", start: Optional[date] = None, end: Optional[date] = None,
                     current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx, rng = _range(current, preset, start, end)
    return {"currency": current.base_currency, "series": ledger.bucketed_series(db, current.id, rng.start, rng.end, granularity, ctx.week_start)}


@router.get("/analytics/budgets")
def budget_performance(months: int = 6, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Monthly budgets vs. actuals for the last N months."""
    ctx = ctx_of(current)
    budgets = db.scalars(select(Budget).where(Budget.user_id == current.id, Budget.active.is_(True), Budget.period == "monthly")).all()
    out = []
    for offset in range(min(max(months, 1), 24) - 1, -1, -1):
        day = add_months(ctx.today, -offset)
        month_end = month_bounds(day)[1]
        point = {"month": day.strftime("%Y-%m"), "budgets": []}
        for b in budgets:
            st = budget_svc.budget_status(db, b, min(month_end, ctx.today), ctx.week_start)
            point["budgets"].append({"budget_id": b.id, "name": b.name, "limit": st["limit"], "spent": st["spent"], "usage_pct": st["usage_pct"]})
        out.append(point)
    return {"currency": current.base_currency, "months": out}


@router.get("/cash-flow")
def cash_flow(preset: Optional[str] = "this_month", start: Optional[date] = None, end: Optional[date] = None,
              current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx, rng = _range(current, preset, start, end)
    result = ledger.cash_flow(db, current.id, current.base_currency, rng.start, rng.end)
    trend_start = month_bounds(add_months(ctx.today, -11))[0]
    return {**result, "currency": current.base_currency, "label": rng.label,
            "monthly": ledger.bucketed_series(db, current.id, trend_start, ctx.today, "month"),
            "daily": ledger.bucketed_series(db, current.id, rng.start, rng.end, "day") if rng.days <= 92 else []}


@router.get("/net-worth")
def net_worth(months: int = 12, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx = ctx_of(current)
    accounts = db.scalars(select(Account).where(Account.user_id == current.id, Account.include_in_net_worth.is_(True))).all()
    balances = {b.account_id: b for b in ledger.balances_in_base(db, current.id, current.base_currency, None, accounts)}
    snapshots = db.scalars(select(NetWorthSnapshot).where(NetWorthSnapshot.user_id == current.id).order_by(NetWorthSnapshot.date.desc()).limit(400)).all()
    return {
        **networth.net_worth(db, current.id, current.base_currency, ctx.today),
        "history": networth.history(db, current.id, current.base_currency, ctx.today, min(max(months, 1), 60)),
        "accounts": [{"id": a.id, "name": a.name, "type": a.type, "is_liability": a.is_liability, "balance_minor": balances[a.id].balance_minor, "currency": a.currency, "base_minor": balances[a.id].base_minor} for a in accounts],
        "snapshots": [{"date": s.date.isoformat(), "net_worth": s.net_worth_minor, "assets": s.assets_minor, "liabilities": s.liabilities_minor} for s in reversed(snapshots)],
    }


@router.get("/insights")
def insights(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return insight_svc.generate(db, ctx_of(current))


@router.get("/reports/{report}")
def report(report: str, preset: Optional[str] = "this_month", start: Optional[date] = None, end: Optional[date] = None,
           format: Literal["json", "csv", "xlsx"] = "json", current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if report not in reports.REPORT_TYPES:
        raise HTTPException(404, "Unknown report")
    ctx, rng = _range(current, preset, start, end)
    data = reports.build(db, ctx, report, rng.start, rng.end)
    data.update(period={"start": rng.start.isoformat(), "end": rng.end.isoformat(), "label": rng.label}, currency=current.base_currency)
    filename = f"ledgerly-{report}-{rng.start.isoformat()}-{rng.end.isoformat()}"
    if format == "csv":
        return Response(reports.to_csv(data), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'})
    if format == "xlsx":
        return Response(reports.to_xlsx(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'})
    return data
