"""Subscriptions: cost equivalents, detection from history, and price-change tracking."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import median as stat_median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Merchant, Subscription, Transaction
from .bills import monthly_equivalent
from .periods import OCCURRENCES_PER_YEAR, advance

# Typical interval (days) and tolerance for each frequency.
_FREQUENCY_WINDOWS = [("weekly", 7, 2), ("monthly", 30, 4), ("quarterly", 91, 8), ("yearly", 365, 15)]


def equivalents(sub: Subscription) -> dict:
    return {
        "monthly_equivalent": monthly_equivalent(sub.amount_minor, sub.frequency),
        "annual_equivalent": sub.amount_minor * OCCURRENCES_PER_YEAR.get(sub.frequency, 12),
    }


def detect_recurring(db: Session, user_id: int, today: date, lookback_days: int = 400) -> list[dict]:
    """Find merchants charged at a regular interval with a stable amount.

    Deterministic heuristic: ≥3 charges, median gap matching a known frequency,
    every gap within tolerance, and every amount within 15% of the median.
    Merchants already tracked as subscriptions are excluded.
    """
    since = today - timedelta(days=lookback_days)
    rows = db.execute(
        select(Transaction.merchant_id, Transaction.date, Transaction.amount_minor, Transaction.currency, Transaction.account_id, Transaction.category_id)
        .where(Transaction.user_id == user_id, Transaction.type == "expense", Transaction.merchant_id.is_not(None), Transaction.date >= since)
        .order_by(Transaction.merchant_id, Transaction.date)
    ).all()
    tracked = {m for (m,) in db.execute(select(Subscription.merchant_id).where(Subscription.user_id == user_id, Subscription.merchant_id.is_not(None))).all()}
    by_merchant: dict[int, list] = defaultdict(list)
    for row in rows:
        by_merchant[row.merchant_id].append(row)

    suggestions = []
    for merchant_id, charges in by_merchant.items():
        if merchant_id in tracked or len(charges) < 3:
            continue
        gaps = [(b.date - a.date).days for a, b in zip(charges, charges[1:])]
        if not gaps or min(gaps) == 0:
            continue
        median_gap = stat_median(gaps)
        match = next(((f, d, tol) for f, d, tol in _FREQUENCY_WINDOWS if abs(median_gap - d) <= tol), None)
        if match is None:
            continue
        frequency, days, tol = match
        if any(abs(g - days) > tol * 2 for g in gaps):
            continue
        amounts = [c.amount_minor for c in charges]
        med = stat_median(amounts)
        if any(abs(a - med) > med * 0.15 for a in amounts):
            continue
        last = charges[-1]
        merchant = db.get(Merchant, merchant_id)
        suggestions.append({
            "merchant_id": merchant_id,
            "name": merchant.name if merchant else "Unknown",
            "frequency": frequency,
            "amount_minor": last.amount_minor,
            "currency": last.currency,
            "occurrences": len(charges),
            "last_charged": last.date.isoformat(),
            "next_expected": advance(last.date, frequency).isoformat(),
            "account_id": last.account_id,
            "category_id": last.category_id,
            "price_changed": amounts[-1] != amounts[-2],
        })
    suggestions.sort(key=lambda s: s["amount_minor"], reverse=True)
    return suggestions


def observe_transaction(db: Session, txn: Transaction) -> list[tuple[Subscription, int]]:
    """Link an expense to an active subscription with the same merchant.

    Rolls the next payment date forward and records price changes. Returns
    (subscription, old_amount) pairs whose price changed so alerts can fire.
    """
    if txn.type != "expense" or not txn.merchant_id:
        return []
    subs = db.scalars(select(Subscription).where(Subscription.user_id == txn.user_id, Subscription.merchant_id == txn.merchant_id, Subscription.active.is_(True))).all()
    changed = []
    for sub in subs:
        if sub.currency != txn.currency:
            continue
        if txn.amount_minor != sub.amount_minor:
            changed.append((sub, sub.amount_minor))
            sub.previous_amount_minor = sub.amount_minor
            sub.amount_minor = txn.amount_minor
            sub.price_changed_at = utcnow()
        if sub.next_payment_date is None or txn.date >= sub.next_payment_date - timedelta(days=5):
            sub.next_payment_date = advance(txn.date, sub.frequency)
    return changed
