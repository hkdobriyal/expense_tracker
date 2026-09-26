"""Materialise recurring templates (salary, rent, SIP…) into transactions when they fall due."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RecurringTransaction, Transaction
from ..money import from_minor
from .periods import advance
from .transactions import TransactionInput, build_transaction


def generate_due(db: Session, user_id: int, base_currency: str, today: date, max_per_rule: int = 24) -> list[Transaction]:
    created: list[Transaction] = []
    rules = db.scalars(
        select(RecurringTransaction).where(
            RecurringTransaction.user_id == user_id,
            RecurringTransaction.active.is_(True),
            RecurringTransaction.auto_create.is_(True),
            RecurringTransaction.next_date <= today,
        )
    ).all()
    for rule in rules:
        count = 0
        while rule.next_date <= today and count < max_per_rule:
            if rule.end_date and rule.next_date > rule.end_date:
                rule.active = False
                break
            txn = build_transaction(db, user_id, base_currency, TransactionInput(
                type=rule.type, account_id=rule.account_id, date=rule.next_date, amount=from_minor(rule.amount_minor, rule.currency),
                description=rule.name, merchant=rule.merchant_name or None, category_id=rule.category_id,
                payment_method=rule.payment_method, transfer_account_id=rule.transfer_account_id,
                is_recurring=True, source="recurring", reviewed=True, recurring_id=rule.id,
            ))
            created.append(txn)
            rule.last_generated_date = rule.next_date
            if rule.frequency == "once":
                rule.active = False
                break
            rule.next_date = advance(rule.next_date, rule.frequency)
            count += 1
    return created
