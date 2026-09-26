"""Budget progress: limit vs. actual spend in the budget's current window."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Budget, Category
from ..money import percent
from . import ledger
from .periods import period_window


def budget_window(budget: Budget, today: date, week_start: int = 0) -> tuple[date, date]:
    if budget.period == "custom" and budget.start_date and budget.end_date:
        return budget.start_date, budget.end_date
    return period_window(budget.period, today, week_start)


def budget_category_ids(budget: Budget, categories: list[Category]) -> set[int] | None:
    if budget.category_id is None:
        return None
    if budget.include_subcategories:
        return ledger.descendant_ids(categories, budget.category_id)
    return {budget.category_id}


def budget_status(db: Session, budget: Budget, today: date, week_start: int = 0, categories: list[Category] | None = None) -> dict:
    if categories is None:
        categories = db.scalars(select(Category).where(Category.user_id == budget.user_id)).all()
    start, end = budget_window(budget, today, week_start)
    spent = ledger.spent_in_categories(db, budget.user_id, budget_category_ids(budget, categories), start, end)
    remaining = budget.amount_minor - spent
    days_total = (end - start).days + 1
    days_elapsed = max(0, min(days_total, (today - start).days + 1))
    # Pace: how much of the window has passed vs. how much of the budget is used.
    expected = round(budget.amount_minor * days_elapsed / days_total) if days_total else 0
    usage = percent(spent, budget.amount_minor)
    status = "over" if spent > budget.amount_minor else "warning" if usage >= 80 else "on_track"
    return {
        "budget_id": budget.id,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "limit": budget.amount_minor,
        "spent": spent,
        "remaining": remaining,
        "usage_pct": usage,
        "expected_spend_to_date": expected,
        "ahead_of_pace": spent > expected,
        "days_left": max(0, (end - today).days),
        "status": status,
    }


def all_budget_statuses(db: Session, user_id: int, today: date, week_start: int = 0) -> list[tuple[Budget, dict]]:
    budgets = db.scalars(select(Budget).where(Budget.user_id == user_id, Budget.active.is_(True)).order_by(Budget.id)).all()
    categories = db.scalars(select(Category).where(Category.user_id == user_id)).all()
    return [(b, budget_status(db, b, today, week_start, categories)) for b in budgets]
