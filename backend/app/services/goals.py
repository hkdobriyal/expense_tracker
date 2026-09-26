"""Savings-goal progress, projections and schedule tracking."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Goal, GoalContribution
from ..money import percent
from . import ledger


def goal_current(db: Session, goal: Goal) -> int:
    if goal.linked_account_id:
        return ledger.account_balances(db, goal.user_id, account_ids=[goal.linked_account_id]).get(goal.linked_account_id, 0)
    total = db.scalar(select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(GoalContribution.goal_id == goal.id))
    return int(total or 0)


def goal_status(db: Session, goal: Goal, today: date) -> dict:
    current = goal_current(db, goal)
    remaining = max(goal.target_minor - current, 0)
    progress = min(percent(current, goal.target_minor), 100.0) if goal.target_minor else 0.0
    expected_pct = None
    behind_by_pct = None
    monthly_needed = None
    if goal.target_date:
        total_days = (goal.target_date - goal.start_date).days
        elapsed = (today - goal.start_date).days
        if total_days > 0:
            expected_pct = round(min(max(elapsed / total_days, 0), 1) * 100, 1)
            behind_by_pct = round(max(expected_pct - progress, 0), 1)
        months_left = max((goal.target_date.year - today.year) * 12 + goal.target_date.month - today.month, 1)
        monthly_needed = -(-remaining // months_left) if remaining else 0  # ceiling division
    return {
        "goal_id": goal.id,
        "current": current,
        "remaining": remaining,
        "progress_pct": progress,
        "expected_pct": expected_pct,
        "behind_by_pct": behind_by_pct,
        "monthly_needed": monthly_needed,
        "is_complete": current >= goal.target_minor,
        "days_left": (goal.target_date - today).days if goal.target_date else None,
    }
