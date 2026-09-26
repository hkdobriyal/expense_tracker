"""Bills: status computation and pay/skip actions that roll the due date forward."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..models import Bill, BillPayment, Transaction
from ..money import from_minor, to_minor
from .periods import OCCURRENCES_PER_YEAR, advance
from .transactions import TransactionInput, build_transaction

DUE_SOON_DAYS = 3


def bill_status(bill: Bill, today: date) -> str:
    if not bill.active:
        return "paid" if any(p.status == "paid" for p in bill.payments) else "skipped"
    days = (bill.next_due_date - today).days
    if days < 0:
        return "overdue"
    if days == 0:
        return "due_today"
    if days <= DUE_SOON_DAYS:
        return "due_soon"
    return "upcoming"


def monthly_equivalent(amount_minor: int, frequency: str) -> int:
    per_year = OCCURRENCES_PER_YEAR.get(frequency, 12)
    return round(amount_minor * per_year / 12)


def _roll_forward(bill: Bill) -> None:
    if bill.frequency == "once":
        bill.active = False
    else:
        bill.next_due_date = advance(bill.next_due_date, bill.frequency)


def pay_bill(db: Session, user_id: int, base_currency: str, bill: Bill, paid_on: date, amount=None, account_id: int | None = None, create_transaction: bool = True) -> BillPayment:
    amount_minor = to_minor(amount, bill.currency) if amount is not None else bill.amount_minor
    txn: Transaction | None = None
    target_account = account_id or bill.account_id
    if create_transaction:
        if not target_account:
            raise ValueError("Choose the account this bill was paid from")
        txn = build_transaction(db, user_id, base_currency, TransactionInput(
            type="expense", account_id=target_account, date=paid_on, amount=from_minor(amount_minor, bill.currency),
            description=bill.name, merchant=bill.provider or bill.name, category_id=bill.category_id,
            payment_method="Auto-debit" if bill.autopay else "", source="bill", reviewed=True,
        ))
    payment = BillPayment(bill_id=bill.id, user_id=user_id, due_date=bill.next_due_date, status="paid", amount_minor=amount_minor, transaction_id=txn.id if txn else None)
    db.add(payment)
    _roll_forward(bill)
    return payment


def skip_bill(db: Session, user_id: int, bill: Bill) -> BillPayment:
    payment = BillPayment(bill_id=bill.id, user_id=user_id, due_date=bill.next_due_date, status="skipped", amount_minor=0)
    db.add(payment)
    _roll_forward(bill)
    return payment
