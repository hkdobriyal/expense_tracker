"""Transaction write path shared by manual entry, imports, SMS, bank sync and recurring rules."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TRANSACTION_TYPES, Account, Category, Tag, Transaction, TransactionSplit
from ..money import MoneyError, convert_minor, normalize_currency, to_minor
from .categorization import auto_categorize, get_or_create_merchant, normalize_merchant
from .extraction import extract, payment_method
from .fx import latest_rate


class TransactionError(ValueError):
    """Raised for invalid input; routers translate it into HTTP 422."""


@dataclass
class TransactionInput:
    type: str
    account_id: int
    date: date
    amount: Decimal | int | str  # major units in the account currency (sign only meaningful for adjustments)
    description: str
    merchant: str | None = None
    category_id: int | None = None
    notes: str = ""
    payment_method: str = ""
    tags: list[str] = field(default_factory=list)
    transfer_account_id: int | None = None
    transfer_amount: Decimal | None = None
    fx_rate: Decimal | None = None
    original_amount: Decimal | None = None
    original_currency: str | None = None
    is_recurring: bool = False
    reviewed: bool | None = None
    splits: list[dict] | None = None  # [{"category_id": 1, "amount": "100.00", "note": ""}]
    source: str = "manual"
    external_id: str | None = None
    raw_description: str = ""
    import_job_id: int | None = None
    recurring_id: int | None = None


INFLOW_TYPES = ("income", "refund")


def signed_for_fingerprint(txn_type: str, amount_minor: int) -> int:
    """Direction-signed amount: re-typing an expense as an investment keeps its fingerprint."""
    if txn_type == "adjustment":
        return amount_minor
    return abs(amount_minor) if txn_type in INFLOW_TYPES else -abs(amount_minor)


def fingerprint(account_id: int, day: date, signed_amount_minor: int, description: str) -> str:
    """Identity used for duplicate detection: account, date, signed amount and the (raw) description."""
    key = f"{account_id}|{day.isoformat()}|{signed_amount_minor}|{normalize_merchant(description)}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _owned_account(db: Session, user_id: int, account_id: int | None, label: str = "Account") -> Account:
    acc = db.get(Account, account_id) if account_id else None
    if acc is None or acc.user_id != user_id:
        raise TransactionError(f"{label} not found")
    return acc


def _owned_category(db: Session, user_id: int, category_id: int | None) -> Category | None:
    if category_id is None:
        return None
    cat = db.get(Category, category_id)
    if cat is None or cat.user_id != user_id:
        raise TransactionError("Category not found")
    return cat


def resolve_tags(db: Session, user_id: int, names: list[str]) -> list[Tag]:
    tags = []
    for raw in names:
        name = raw.strip().lstrip("#")[:48]
        if not name:
            continue
        tag = db.scalar(select(Tag).where(Tag.user_id == user_id, Tag.name == name))
        if tag is None:
            tag = Tag(user_id=user_id, name=name)
            db.add(tag)
            db.flush()
        if tag not in tags:
            tags.append(tag)
    return tags


def _base_amount(db: Session, user_id: int, amount_minor: int, currency: str, base_currency: str, on: date, fx_rate: Decimal | None) -> tuple[int, Decimal | None]:
    if currency == base_currency:
        return amount_minor, None
    rate = Decimal(fx_rate) if fx_rate else latest_rate(db, user_id, currency, base_currency, on)
    if rate is None or rate <= 0:
        raise TransactionError(
            f"No exchange rate for {currency}→{base_currency}. Add one under Settings → Exchange rates or enter the rate on this transaction."
        )
    return convert_minor(amount_minor, rate, currency, base_currency), rate


def _apply_splits(db: Session, user_id: int, txn: Transaction, splits: list[dict] | None) -> None:
    txn.splits.clear()
    if not splits:
        return
    if txn.type not in ("expense", "income", "refund"):
        raise TransactionError("Only expenses, income and refunds can be split")
    if len(splits) < 2:
        raise TransactionError("A split needs at least two parts")
    parts = []
    for part in splits:
        _owned_category(db, user_id, part.get("category_id"))
        try:
            minor = to_minor(part["amount"], txn.currency)
        except (MoneyError, KeyError) as exc:
            raise TransactionError(f"Invalid split amount: {exc}") from exc
        if minor <= 0:
            raise TransactionError("Split amounts must be positive")
        parts.append((part.get("category_id"), minor, str(part.get("note") or "")[:255]))
    if sum(p[1] for p in parts) != txn.amount_minor:
        raise TransactionError("Split amounts must add up to the transaction amount")
    # Convert each part to base currency; give the rounding remainder to the last part.
    allocated = 0
    for index, (category_id, minor, note) in enumerate(parts):
        if index == len(parts) - 1:
            base = txn.base_amount_minor - allocated
        else:
            base = round(txn.base_amount_minor * minor / txn.amount_minor)
            allocated += base
        txn.splits.append(TransactionSplit(category_id=category_id, amount_minor=minor, base_amount_minor=base, note=note))
    txn.category_id = None


def build_transaction(db: Session, user_id: int, base_currency: str, data: TransactionInput, txn: Transaction | None = None) -> Transaction:
    """Validate ``data`` and write it into ``txn`` (a new Transaction when None). Does not commit."""
    if data.type not in TRANSACTION_TYPES:
        raise TransactionError(f"Unknown transaction type '{data.type}'")
    description = (data.description or "").strip()
    if not description:
        raise TransactionError("Description is required")
    account = _owned_account(db, user_id, data.account_id)
    currency = account.currency
    try:
        amount_minor = to_minor(data.amount, currency)
    except MoneyError as exc:
        raise TransactionError(str(exc)) from exc

    if data.type == "adjustment":
        if amount_minor == 0:
            raise TransactionError("Adjustment amount cannot be zero")
    else:
        if amount_minor < 0:
            raise TransactionError("Enter a positive amount; the transaction type sets the direction")
        if amount_minor == 0:
            raise TransactionError("Amount must be greater than zero")
    if abs(amount_minor) > 10**15:
        raise TransactionError("Amount is unrealistically large")

    transfer_account = None
    transfer_amount_minor = None
    if data.type == "transfer":
        transfer_account = _owned_account(db, user_id, data.transfer_account_id, "Destination account")
        if transfer_account.id == account.id:
            raise TransactionError("Choose two different accounts for a transfer")
        if transfer_account.currency != currency:
            if data.transfer_amount is None:
                raise TransactionError(f"Enter the amount received in {transfer_account.currency} for a cross-currency transfer")
            transfer_amount_minor = abs(to_minor(data.transfer_amount, transfer_account.currency))

    category = _owned_category(db, user_id, data.category_id) if data.type not in ("transfer", "adjustment") else None
    base_minor, rate = _base_amount(db, user_id, amount_minor, currency, base_currency, data.date, data.fx_rate)

    if txn is None:
        txn = Transaction(user_id=user_id, source=data.source)
        db.add(txn)
    txn.account_id = account.id
    txn.type = data.type
    txn.date = data.date
    txn.amount_minor = amount_minor
    txn.currency = currency
    txn.base_amount_minor = base_minor
    txn.fx_rate = rate
    txn.transfer_account_id = transfer_account.id if transfer_account else None
    txn.transfer_amount_minor = transfer_amount_minor
    txn.description = description[:255]
    txn.notes = (data.notes or "")[:5000]
    txn.payment_method = (data.payment_method or "")[:32]
    txn.is_recurring = bool(data.is_recurring)
    txn.category_id = category.id if category else None
    txn.raw_description = (data.raw_description or "")[:5000]
    txn.external_id = data.external_id
    txn.import_job_id = data.import_job_id or txn.import_job_id
    txn.recurring_id = data.recurring_id or txn.recurring_id
    if data.original_amount is not None and data.original_currency:
        oc = normalize_currency(data.original_currency)
        txn.original_currency = oc
        txn.original_amount_minor = abs(to_minor(data.original_amount, oc))
    else:
        txn.original_currency = None
        txn.original_amount_minor = None

    # Entity extraction (mode, UPI id, reference, payee…) fills gaps the caller didn't provide.
    entities = extract(txn.raw_description or description)
    txn.extracted = {k: v for k, v in entities.items() if k != "suggestions"}
    if not txn.payment_method:
        txn.payment_method = payment_method(entities)
    merchant_name = data.merchant or (entities.get("merchant") if entities.get("counterparty") != "person" else None)
    merchant = get_or_create_merchant(db, user_id, merchant_name) if data.type not in ("transfer", "adjustment") else None
    txn.merchant_id = merchant.id if merchant else None
    txn.merchant = merchant
    txn.tags = resolve_tags(db, user_id, data.tags)
    txn.fingerprint = fingerprint(account.id, data.date, signed_for_fingerprint(data.type, amount_minor), txn.raw_description or description)
    if data.reviewed is not None:
        txn.reviewed = data.reviewed
    _apply_splits(db, user_id, txn, data.splits)
    if category is not None:
        txn.category_source, txn.category_confidence = "user", None
    elif txn.splits:
        txn.category_source, txn.category_confidence = "user", None
    else:
        txn.category_source, txn.category_confidence = "", None
        auto_categorize(db, user_id, txn)
    db.flush()
    return txn


def learn_merchant_category(db: Session, txn: Transaction) -> None:
    """When the user categorises a transaction, remember it as the merchant default."""
    if txn.merchant_id and txn.category_id and txn.merchant is not None and txn.merchant.default_category_id is None:
        txn.merchant.default_category_id = txn.category_id


def find_duplicate(db: Session, user_id: int, txn_fingerprint: str, external_id: str | None, exclude_id: int | None = None) -> Transaction | None:
    if external_id:
        found = db.scalar(select(Transaction).where(Transaction.user_id == user_id, Transaction.external_id == external_id))
        if found is not None and found.id != exclude_id:
            return found
    stmt = select(Transaction).where(Transaction.user_id == user_id, Transaction.fingerprint == txn_fingerprint)
    if exclude_id:
        stmt = stmt.where(Transaction.id != exclude_id)
    return db.scalar(stmt.limit(1))


def duplicate_of(txn: Transaction) -> Transaction:
    """Copy a transaction as a new one (the user adjusts the date afterwards)."""
    copy = Transaction(
        user_id=txn.user_id, account_id=txn.account_id, type=txn.type, date=txn.date, amount_minor=txn.amount_minor,
        currency=txn.currency, base_amount_minor=txn.base_amount_minor, fx_rate=txn.fx_rate,
        transfer_account_id=txn.transfer_account_id, transfer_amount_minor=txn.transfer_amount_minor,
        description=txn.description, merchant_id=txn.merchant_id, category_id=txn.category_id, notes=txn.notes,
        payment_method=txn.payment_method, is_recurring=txn.is_recurring, reviewed=True, source="manual",
        original_amount_minor=txn.original_amount_minor, original_currency=txn.original_currency,
    )
    copy.tags = list(txn.tags)
    copy.splits = [TransactionSplit(category_id=s.category_id, amount_minor=s.amount_minor, base_amount_minor=s.base_amount_minor, note=s.note) for s in txn.splits]
    copy.fingerprint = txn.fingerprint + "-copy"
    return copy
