"""Bank connections behind a provider interface, plus the synchronisation pipeline.

Flow:  Add bank → authenticate/consent → select accounts → connect → sync.

Providers
---------
* ``demo``    – deterministic sandbox bank. Only usable inside Demo mode so
                sample transactions can never mix with real data.
* ``setu_aa`` – RBI Account Aggregator via Setu. Registered but unavailable:
                pulling data as a Financial Information User (FIU) requires a
                registered business entity and verified API documentation.
                See docs/bank-integration.md for what is needed.

Real-world ingestion that works today for an individual in India: statement
import (CSV/XLSX/PDF/OFX) and bank SMS parsing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import Account, BankConnection, SyncLog, Transaction, User
from ..money import from_minor, to_minor
from . import alerts, ledger
from .context import UserContext
from .transactions import TransactionError, TransactionInput, build_transaction, fingerprint, signed_for_fingerprint


class ProviderError(Exception):
    """A sync/connection failure that should be shown to the user."""


class ProviderUnavailable(ProviderError):
    pass


class ProviderAuthExpired(ProviderError):
    pass


@dataclass
class ProviderAccount:
    external_id: str
    name: str
    type: str
    currency: str
    mask: str = ""
    balance: Decimal | None = None
    institution: str = ""


@dataclass
class ProviderTransaction:
    external_id: str
    date: date
    amount: Decimal  # signed: + money in, − money out
    description: str
    merchant: str | None = None
    payment_method: str = ""
    category_hint: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class ConnectStep:
    status: str  # pending|active
    message: str
    next_action: str | None = None  # select_accounts|redirect|None
    redirect_url: str | None = None
    accounts: list[ProviderAccount] = field(default_factory=list)


class BankProvider(Protocol):
    key: str
    label: str
    description: str
    is_sandbox: bool

    def availability(self, user: User) -> tuple[bool, str]: ...
    def institutions(self) -> list[dict]: ...
    def start(self, conn: BankConnection, params: dict) -> ConnectStep: ...
    def list_accounts(self, conn: BankConnection) -> list[ProviderAccount]: ...
    def fetch_transactions(self, conn: BankConnection, account_external_id: str, since: date, until: date) -> list[ProviderTransaction]: ...
    def disconnect(self, conn: BankConnection) -> None: ...


# ---------------------------------------------------------------------------
# Demo sandbox provider
# ---------------------------------------------------------------------------


class DemoBankProvider:
    key = "demo"
    label = "Sandbox Bank (demo data)"
    description = "Generates realistic sample transactions for Demo mode. Never available for real workspaces."
    is_sandbox = True

    _MERCHANTS = [
        ("Zepto", "UPI", 250, 900, 0.30), ("Swiggy", "UPI", 180, 750, 0.35), ("Uber", "UPI", 120, 450, 0.25),
        ("Amazon", "Card", 400, 3500, 0.10), ("Blinkit", "UPI", 150, 700, 0.20), ("Starbucks", "Card", 250, 600, 0.10),
        ("Apollo Pharmacy", "UPI", 150, 1200, 0.05), ("HPCL Fuel", "Card", 800, 2500, 0.06), ("BookMyShow", "UPI", 300, 1200, 0.04),
    ]

    def availability(self, user: User) -> tuple[bool, str]:
        if not user.is_demo:
            return False, "The sandbox bank only works in Demo mode, so sample transactions never mix with your real data."
        return True, ""

    def institutions(self) -> list[dict]:
        return [{"id": "sandbox-bank", "name": "Sandbox Bank", "country": "IN", "sandbox": True}]

    def start(self, conn: BankConnection, params: dict) -> ConnectStep:
        return ConnectStep("pending", "Sandbox bank authorised. Choose the accounts to link.", "select_accounts", accounts=self.list_accounts(conn))

    def list_accounts(self, conn: BankConnection) -> list[ProviderAccount]:
        return [
            ProviderAccount(f"demo-{conn.id}-savings", "Sandbox Savings", "savings", "INR", "4821", None, "Sandbox Bank"),
            ProviderAccount(f"demo-{conn.id}-card", "Sandbox Credit Card", "credit_card", "INR", "9043", None, "Sandbox Bank"),
        ]

    def fetch_transactions(self, conn: BankConnection, account_external_id: str, since: date, until: date) -> list[ProviderTransaction]:
        # Deterministic per connection+day, so repeated syncs return identical ids (exercising dedupe).
        out: list[ProviderTransaction] = []
        is_card = account_external_id.endswith("card")
        day = since
        while day <= until:
            rng = random.Random(f"{account_external_id}:{day.isoformat()}")
            seq = 0

            def add(amount: int, description: str, merchant: str | None, method: str, hint: str | None = None):
                nonlocal seq
                seq += 1
                out.append(ProviderTransaction(f"{account_external_id}:{day.isoformat()}:{seq}", day, Decimal(amount), description, merchant, method, hint))

            if not is_card:
                if day.day == 1:
                    add(95_000, "NEFT CR PAYROLL SANDBOX CORP SALARY", "Sandbox Corp", "Net banking", "salary")
                if day.day == 5:
                    add(-28_000, "IMPS DR RENT LANDLORD", "Landlord", "Net banking", "rent")
                if day.day == 7:
                    add(-15_000, "ACH D ZERODHA MUTUAL FUND SIP", "Zerodha", "Auto-debit", "investment")
                if day.day == 12:
                    add(-rng.randint(1_400, 2_600), "BBPS BESCOM ELECTRICITY", "BESCOM", "Net banking")
                if day.day == 18:
                    add(-799, "ACH D AIRTEL BROADBAND", "Airtel", "Auto-debit")
                if day.day == 20:
                    add(-7_000, "CC PAYMENT SANDBOX CREDIT CARD", None, "Net banking", "card_payment")
            else:
                if day.day == 3:
                    add(-649, "NETFLIX.COM SUBSCRIPTION", "Netflix", "Card")
                if day.day == 9:
                    add(-119, "SPOTIFY INDIA", "Spotify", "Card")
                if day.day == 20:
                    add(7_000, "PAYMENT RECEIVED THANK YOU", None, "Net banking", "card_payment")
            for name, method, low, high, prob in self._MERCHANTS:
                on_card = method == "Card"
                if on_card == is_card and rng.random() < prob:
                    prefix = "POS" if on_card else "UPI/DR"
                    add(-rng.randint(low, high), f"{prefix}/{rng.randint(10**9, 10**10 - 1)}/{name.upper()}", name, method)
            day += timedelta(days=1)
        return out

    def disconnect(self, conn: BankConnection) -> None:
        return None


class SetuAAProvider:
    key = "setu_aa"
    label = "Account Aggregator (Setu)"
    description = "RBI Account Aggregator via Setu. Requires FIU registration and API credentials."
    is_sandbox = False

    def availability(self, user: User) -> tuple[bool, str]:
        s = get_settings()
        if not (s.setu_client_id and s.setu_client_secret and s.setu_product_instance_id):
            return False, "Not configured. Needs Setu FIU credentials (SETU_CLIENT_ID, SETU_CLIENT_SECRET, SETU_PRODUCT_INSTANCE_ID)."
        return False, "Credentials found, but the adapter is not implemented yet: it needs the Setu AA API documentation and a sample FI data response to be built and verified."

    def institutions(self) -> list[dict]:
        return []

    def start(self, conn, params):
        raise ProviderUnavailable(self.availability(User())[1])

    def list_accounts(self, conn):
        raise ProviderUnavailable("Account Aggregator adapter is not implemented")

    def fetch_transactions(self, conn, account_external_id, since, until):
        raise ProviderUnavailable("Account Aggregator adapter is not implemented")

    def disconnect(self, conn):
        return None


PROVIDERS: dict[str, BankProvider] = {p.key: p for p in (DemoBankProvider(), SetuAAProvider())}


def get_provider(key: str) -> BankProvider:
    provider = PROVIDERS.get(key)
    if provider is None:
        raise ProviderUnavailable(f"Unknown bank provider '{key}'")
    return provider


def provider_catalog(user: User) -> list[dict]:
    out = []
    for p in PROVIDERS.values():
        available, reason = p.availability(user)
        out.append({"key": p.key, "label": p.label, "description": p.description, "sandbox": p.is_sandbox, "available": available, "reason": reason, "institutions": p.institutions() if available else []})
    return out


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------


def start_connection(db: Session, ctx: UserContext, user: User, provider_key: str, institution_id: str, params: dict) -> tuple[BankConnection, ConnectStep]:
    provider = get_provider(provider_key)
    available, reason = provider.availability(user)
    if not available:
        raise ProviderUnavailable(reason)
    inst = next((i for i in provider.institutions() if i["id"] == institution_id), None)
    conn = BankConnection(user_id=ctx.user_id, provider=provider.key, institution_id=institution_id, institution_name=inst["name"] if inst else institution_id, status="pending")
    db.add(conn)
    db.flush()
    step = provider.start(conn, params)
    return conn, step


def link_accounts(db: Session, ctx: UserContext, conn: BankConnection, external_ids: list[str]) -> list[Account]:
    provider = get_provider(conn.provider)
    discovered = {a.external_id: a for a in provider.list_accounts(conn)}
    if not external_ids:
        raise ProviderError("Select at least one account to link")
    linked = []
    for ext in external_ids:
        pa = discovered.get(ext)
        if pa is None:
            raise ProviderError(f"Account {ext} was not offered by the bank")
        acc = db.scalar(select(Account).where(Account.user_id == ctx.user_id, Account.external_account_id == ext))
        if acc is None:
            acc = Account(user_id=ctx.user_id, name=pa.name, type=pa.type, institution=pa.institution or conn.institution_name,
                          currency=pa.currency, account_number_mask=pa.mask, opening_balance_minor=0)
            db.add(acc)
        acc.bank_connection_id = conn.id
        acc.external_account_id = ext
        linked.append(acc)
    conn.status = "active"
    db.flush()
    return linked


def disconnect(db: Session, conn: BankConnection) -> None:
    try:
        get_provider(conn.provider).disconnect(conn)
    except ProviderError:
        pass
    conn.status = "disconnected"
    conn.credentials_encrypted = None
    conn.auto_sync = False
    for acc in db.scalars(select(Account).where(Account.bank_connection_id == conn.id)).all():
        acc.bank_connection_id = None  # keep the account and its history


# ---------------------------------------------------------------------------
# Synchronisation pipeline
# ---------------------------------------------------------------------------

INITIAL_LOOKBACK_DAYS = 90
OVERLAP_DAYS = 7  # re-fetch a week to catch late-posted/changed transactions


def _provider_type(pt: ProviderTransaction) -> str:
    if pt.category_hint == "investment":
        return "investment"
    if pt.category_hint == "card_payment":
        # A credit-card bill payment moves money between the user's own accounts: it is not
        # income or spending, so each side is stored as a balance adjustment.
        return "adjustment"
    return "income" if pt.amount > 0 else "expense"


def sync_connection(db: Session, ctx: UserContext, user: User, conn: BankConnection, trigger: str = "manual") -> SyncLog:
    log = SyncLog(user_id=ctx.user_id, connection_id=conn.id, trigger=trigger, status="running")
    db.add(log)
    db.flush()
    created: list[Transaction] = []
    try:
        if conn.status == "disconnected":
            raise ProviderError("This connection was disconnected. Reconnect the bank to sync again.")
        provider = get_provider(conn.provider)
        available, reason = provider.availability(user)
        if not available:
            raise ProviderUnavailable(reason)
        accounts = db.scalars(select(Account).where(Account.user_id == ctx.user_id, Account.bank_connection_id == conn.id)).all()
        if not accounts:
            raise ProviderError("No accounts are linked to this connection yet")
        today = ctx.today
        for acc in accounts:
            since = (acc.last_synced_at.date() - timedelta(days=OVERLAP_DAYS)) if acc.last_synced_at else today - timedelta(days=INITIAL_LOOKBACK_DAYS)
            fetched = provider.fetch_transactions(conn, acc.external_account_id or "", since, today)
            log.fetched_count += len(fetched)
            existing_rows = db.execute(select(Transaction.fingerprint).where(Transaction.user_id == ctx.user_id, Transaction.account_id == acc.id, Transaction.date >= since, Transaction.external_id.is_(None))).all()
            unmatched_fps: dict[str, int] = {}
            for (fp,) in existing_rows:
                unmatched_fps[fp] = unmatched_fps.get(fp, 0) + 1
            for pt in fetched:
                txn_type = _provider_type(pt)
                existing = db.scalar(select(Transaction).where(Transaction.user_id == ctx.user_id, Transaction.account_id == acc.id, Transaction.external_id == pt.external_id))
                data = TransactionInput(
                    type=txn_type, account_id=acc.id, date=pt.date, amount=pt.amount if txn_type == "adjustment" else abs(pt.amount),
                    description=pt.merchant or pt.description, merchant=pt.merchant, payment_method=pt.payment_method,
                    source="bank", external_id=pt.external_id, raw_description=pt.description,
                )
                if existing is not None:
                    changed = existing.amount_minor != to_minor(data.amount, acc.currency) or existing.date != pt.date or existing.raw_description != pt.description
                    if changed:
                        data.category_id = existing.category_id
                        data.tags = [t.name for t in existing.tags]
                        data.notes = existing.notes
                        data.reviewed = existing.reviewed
                        build_transaction(db, ctx.user_id, ctx.base_currency, data, existing)
                        log.updated_count += 1
                    else:
                        log.duplicate_count += 1
                    continue
                fp = fingerprint(acc.id, pt.date, signed_for_fingerprint(txn_type, to_minor(data.amount, acc.currency)), pt.description)
                if unmatched_fps.get(fp, 0) > 0:
                    # Same transaction already entered manually or imported from a statement: link it, don't duplicate.
                    unmatched_fps[fp] -= 1
                    match = db.scalar(select(Transaction).where(Transaction.user_id == ctx.user_id, Transaction.account_id == acc.id, Transaction.fingerprint == fp, Transaction.external_id.is_(None)).limit(1))
                    if match is not None:
                        match.external_id = pt.external_id
                    log.duplicate_count += 1
                    continue
                try:
                    with db.begin_nested():
                        created.append(build_transaction(db, ctx.user_id, ctx.base_currency, data))
                    log.imported_count += 1
                except TransactionError as exc:
                    log.error_count += 1
                    log.message = f"Some transactions could not be stored: {exc}"
            balances = {pa.external_id: pa.balance for pa in provider.list_accounts(conn)}
            if balances.get(acc.external_account_id) is not None:
                acc.reported_balance_minor = to_minor(balances[acc.external_account_id], acc.currency)
                acc.reported_balance_at = utcnow()
            acc.last_synced_at = utcnow()
        conn.status = "active"
        conn.last_error = None
        conn.last_synced_at = utcnow()
        log.status = "success"
        log.message = log.message or (
            f"{log.imported_count} imported, {log.updated_count} updated, {log.duplicate_count} duplicates skipped"
        )
        db.flush()
        alerts.after_ledger_change(db, ctx, created)
    except ProviderError as exc:
        _fail(db, ctx, conn, log, exc)
    except Exception as exc:  # noqa: BLE001 - unexpected provider/network errors are recorded, not raised
        _fail(db, ctx, conn, log, exc, unexpected=True)
    log.finished_at = utcnow()
    return log


def _fail(db: Session, ctx: UserContext, conn: BankConnection, log: SyncLog, exc: Exception, unexpected: bool = False) -> None:
    message = str(exc) if not unexpected else f"Unexpected error during sync ({type(exc).__name__}). Details were logged."
    log.status = "failed"
    log.message = message[:1000]
    conn.status = "expired" if isinstance(exc, ProviderAuthExpired) else "error"
    conn.last_error = message[:1000]
    alerts.emit(db, ctx, "sync_failed", alerts.Observation(
        entity=f"sync:{log.id}", value=Decimal(0), period_key="-", title=f"Bank sync failed: {conn.institution_name}",
        message=message, severity="critical", link="/banks",
    ))


def sync_connection_by_id(db: Session, connection_id: int, trigger: str = "scheduled") -> SyncLog | None:
    conn = db.get(BankConnection, connection_id)
    if conn is None:
        return None
    user = db.get(User, conn.user_id)
    ctx = UserContext.for_user(db, user)
    return sync_connection(db, ctx, user, conn, trigger)


def reconciliation(db: Session, acc: Account) -> dict | None:
    if acc.reported_balance_minor is None:
        return None
    computed = ledger.account_balances(db, acc.user_id, account_ids=[acc.id]).get(acc.id, 0)
    return {
        "reported": acc.reported_balance_minor,
        "computed": computed,
        "difference": acc.reported_balance_minor - computed,
        "reported_at": acc.reported_balance_at.isoformat() if acc.reported_balance_at else None,
        "display": str(from_minor(acc.reported_balance_minor - computed, acc.currency)),
    }
