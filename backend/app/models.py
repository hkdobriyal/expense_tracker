"""ORM models.

Conventions
-----------
* Every user-owned table has ``user_id``; every query in the services layer
  filters on it (ownership isolation, and the reason multi-user is cheap later).
* Money columns end in ``_minor`` and hold integers (paise/cents).
* ``base_amount_minor`` on a transaction is the amount converted into the
  user's base currency at write time, so aggregations never add INR to USD.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, UTCDateTime, utcnow

# ---------------------------------------------------------------------------
# Enumerations (stored as short strings for portability and readable SQL)
# ---------------------------------------------------------------------------

TRANSACTION_TYPES = ("expense", "income", "transfer", "refund", "adjustment", "investment")
ACCOUNT_TYPES = (
    "current", "savings", "credit_card", "cash", "wallet", "investment", "loan", "mortgage", "asset", "liability",
)
LIABILITY_ACCOUNT_TYPES = ("credit_card", "loan", "mortgage", "liability")
FREQUENCIES = ("once", "weekly", "monthly", "quarterly", "half_yearly", "yearly")
BUDGET_PERIODS = ("weekly", "monthly", "yearly", "custom")
GOAL_TYPES = ("emergency_fund", "vacation", "house", "car", "education", "investment", "debt_payoff", "wedding", "custom")
TRANSACTION_SOURCES = ("manual", "import", "sms", "bank", "recurring", "bill", "demo", "restore")
CHANNELS = ("in_app", "email", "sms", "whatsapp", "push")


# ---------------------------------------------------------------------------
# Users, sessions, settings
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    settings: Mapped["UserSettings"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")

    user: Mapped[User] = relationship()


class AuthToken(Base):
    """Single-use tokens for password reset and email verification (only a hash is stored)."""

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(16))  # reset|verify
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PushSubscription(Base):
    """A browser's Web Push endpoint (one per browser/device)."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)


def default_notification_matrix() -> dict[str, dict[str, bool]]:
    categories = ("budget", "spending", "transaction", "account", "bills", "subscriptions", "goals", "income", "system")
    return {c: {"in_app": True, "email": c in {"budget", "bills", "account", "system"}, "sms": False, "whatsapp": False, "push": False} for c in categories}


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), default="INR")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    locale: Mapped[str] = mapped_column(String(16), default="en-IN")
    week_start: Mapped[int] = mapped_column(Integer, default=0)  # 0 = Monday
    default_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    theme: Mapped[str] = mapped_column(String(16), default="dark")
    reduce_motion: Mapped[bool] = mapped_column(Boolean, default=False)
    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)

    contact_email: Mapped[str] = mapped_column(String(255), default="")
    contact_phone: Mapped[str] = mapped_column(String(32), default="")
    whatsapp_number: Mapped[str] = mapped_column(String(32), default="")
    # Master switches per channel; per-category defaults live in notification_matrix.
    channel_in_app: Mapped[bool] = mapped_column(Boolean, default=True)
    channel_email: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_push: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_matrix: Mapped[dict[str, Any]] = mapped_column(JSON, default=default_notification_matrix)

    sms_webhook_token_hash: Mapped[Optional[str]] = mapped_column(String(128))
    sms_webhook_token_hint: Mapped[Optional[str]] = mapped_column(String(16))

    user: Mapped[User] = relationship(back_populates="settings")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[Optional[str]] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class Job(Base):
    """Database-backed job queue processed by ``python -m app.worker``."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued|running|done|failed
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)


class SystemState(Base):
    """Small key/value store (e.g. worker heartbeat)."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("user_id", "base_currency", "quote_currency", "as_of"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    base_currency: Mapped[str] = mapped_column(String(3))  # 1 unit of base_currency ...
    quote_currency: Mapped[str] = mapped_column(String(3))  # ... equals `rate` units of quote_currency
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    as_of: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(32), default="manual")


# ---------------------------------------------------------------------------
# Ledger: accounts, categories, merchants, tags, transactions
# ---------------------------------------------------------------------------


class BankConnection(Base):
    __tablename__ = "bank_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    institution_id: Mapped[str] = mapped_column(String(64), default="")
    institution_name: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|active|expired|error|disconnected
    # Provider tokens/consent ids, Fernet-encrypted. Never serialised to the frontend.
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    consent_expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    auto_sync: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(24), default="savings")
    institution: Mapped[str] = mapped_column(String(120), default="")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    # Liabilities are stored with a negative opening balance (money owed).
    opening_balance_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    opening_date: Mapped[Optional[date]] = mapped_column(Date)
    credit_limit_minor: Mapped[Optional[int]] = mapped_column(BigInteger)
    account_number_mask: Mapped[str] = mapped_column(String(16), default="")
    color: Mapped[str] = mapped_column(String(16), default="")
    include_in_net_worth: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    bank_connection_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bank_connections.id", ondelete="SET NULL"))
    external_account_id: Mapped[Optional[str]] = mapped_column(String(128))
    reported_balance_minor: Mapped[Optional[int]] = mapped_column(BigInteger)
    reported_balance_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    bank_connection: Mapped[Optional[BankConnection]] = relationship()

    @property
    def is_liability(self) -> bool:
        return self.type in LIABILITY_ACCOUNT_TYPES


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "parent_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16), default="expense")  # expense|income
    color: Mapped[str] = mapped_column(String(16), default="")
    icon: Mapped[str] = mapped_column(String(32), default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    parent: Mapped[Optional["Category"]] = relationship(remote_side="Category.id", back_populates="children")
    children: Mapped[list["Category"]] = relationship(back_populates="parent")


class Merchant(Base):
    __tablename__ = "merchants"
    __table_args__ = (UniqueConstraint("user_id", "normalized_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    normalized_name: Mapped[str] = mapped_column(String(120))
    default_category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(48))
    color: Mapped[str] = mapped_column(String(16), default="")


transaction_tags = Table(
    "transaction_tags",
    Base.metadata,
    Column("transaction_id", ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount_minor > 0 OR type = 'adjustment'", name="ck_transactions_amount_positive"),
        CheckConstraint("type != 'transfer' OR transfer_account_id IS NOT NULL", name="ck_transactions_transfer_target"),
        Index("ix_transactions_user_date", "user_id", "date"),
        Index("ix_transactions_user_account_date", "user_id", "account_id", "date"),
        Index("ix_transactions_user_category", "user_id", "category_id"),
        Index("ix_transactions_user_fingerprint", "user_id", "fingerprint"),
        Index("ix_transactions_user_external", "user_id", "external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(16), default="expense")
    date: Mapped[date] = mapped_column(Date)

    amount_minor: Mapped[int] = mapped_column(BigInteger)  # in `currency`; positive except adjustments
    currency: Mapped[str] = mapped_column(String(3))
    base_amount_minor: Mapped[int] = mapped_column(BigInteger)  # converted to the user's base currency
    fx_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 10))  # 1 account currency = fx_rate base currency
    # What was actually charged when paying in a foreign currency (e.g. USD 12.99 on an INR card).
    original_amount_minor: Mapped[Optional[int]] = mapped_column(BigInteger)
    original_currency: Mapped[Optional[str]] = mapped_column(String(3))

    # Transfers: money moves from account_id to transfer_account_id (optionally in another currency).
    transfer_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    transfer_amount_minor: Mapped[Optional[int]] = mapped_column(BigInteger)

    description: Mapped[str] = mapped_column(String(255))
    merchant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("merchants.id", ondelete="SET NULL"), index=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    notes: Mapped[str] = mapped_column(Text, default="")
    payment_method: Mapped[str] = mapped_column(String(32), default="")
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurring_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recurring_transactions.id", ondelete="SET NULL"))
    reviewed: Mapped[bool] = mapped_column(Boolean, default=True)

    source: Mapped[str] = mapped_column(String(16), default="manual")
    import_job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("import_jobs.id", ondelete="SET NULL"))
    external_id: Mapped[Optional[str]] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    raw_description: Mapped[str] = mapped_column(Text, default="")
    # Entities pulled out of the narration (mode, UPI id, reference, card, payee…).
    extracted: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Who chose the category: user|rule|merchant|ml|keyword|llm, and how confident (0–1) automated ones were.
    category_source: Mapped[str] = mapped_column(String(16), default="")
    category_confidence: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    account: Mapped[Account] = relationship(foreign_keys=[account_id])
    transfer_account: Mapped[Optional[Account]] = relationship(foreign_keys=[transfer_account_id])
    merchant: Mapped[Optional[Merchant]] = relationship()
    category: Mapped[Optional[Category]] = relationship()
    tags: Mapped[list[Tag]] = relationship(secondary=transaction_tags)
    splits: Mapped[list["TransactionSplit"]] = relationship(back_populates="transaction", cascade="all, delete-orphan")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="transaction", cascade="all, delete-orphan")


class TransactionSplit(Base):
    __tablename__ = "transaction_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    base_amount_minor: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str] = mapped_column(String(255), default="")

    transaction: Mapped[Transaction] = relationship(back_populates="splits")
    category: Mapped[Optional[Category]] = relationship()


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(255))  # relative path inside DATA_DIR/uploads
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    transaction: Mapped[Transaction] = relationship(back_populates="attachments")


class CategorizationRule(Base):
    __tablename__ = "categorization_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower runs first
    field: Mapped[str] = mapped_column(String(16), default="any")  # description|merchant|notes|any
    match_type: Mapped[str] = mapped_column(String(16), default="contains")  # contains|equals|starts_with|ends_with|regex
    pattern: Mapped[str] = mapped_column(String(255))
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    amount_min_minor: Mapped[Optional[int]] = mapped_column(BigInteger)
    amount_max_minor: Mapped[Optional[int]] = mapped_column(BigInteger)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    transaction_type: Mapped[Optional[str]] = mapped_column(String(16))
    set_category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    set_merchant_name: Mapped[Optional[str]] = mapped_column(String(120))
    add_tag_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    mark_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    apply_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RecurringTransaction(Base):
    """A template the worker materialises into real transactions on schedule (e.g. salary, SIP, rent)."""

    __tablename__ = "recurring_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(16), default="expense")
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    transfer_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    merchant_name: Mapped[str] = mapped_column(String(120), default="")
    payment_method: Mapped[str] = mapped_column(String(32), default="")
    frequency: Mapped[str] = mapped_column(String(16), default="monthly")
    next_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    auto_create: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_generated_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Planning: budgets, goals, bills, subscriptions
# ---------------------------------------------------------------------------


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))  # NULL = all spending
    period: Mapped[str] = mapped_column(String(16), default="monthly")
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    start_date: Mapped[Optional[date]] = mapped_column(Date)  # required for custom periods
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    include_subcategories: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    category: Mapped[Optional[Category]] = relationship()


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    goal_type: Mapped[str] = mapped_column(String(24), default="custom")
    target_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    start_date: Mapped[date] = mapped_column(Date)
    # When linked, progress = the account balance; otherwise the sum of contributions.
    linked_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    color: Mapped[str] = mapped_column(String(16), default="")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|completed|archived
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    contributions: Mapped[list["GoalContribution"]] = relationship(back_populates="goal", cascade="all, delete-orphan")


class GoalContribution(Base):
    __tablename__ = "goal_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    amount_minor: Mapped[int] = mapped_column(BigInteger)  # negative = withdrawal
    date: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    goal: Mapped[Goal] = relationship(back_populates="contributions")


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(120), default="")
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    frequency: Mapped[str] = mapped_column(String(16), default="monthly")
    next_due_date: Mapped[date] = mapped_column(Date)
    autopay: Mapped[bool] = mapped_column(Boolean, default=False)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # one-off bills become inactive once paid
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    payments: Mapped[list["BillPayment"]] = relationship(back_populates="bill", cascade="all, delete-orphan")


class BillPayment(Base):
    __tablename__ = "bill_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))  # paid|skipped
    amount_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    transaction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    bill: Mapped[Bill] = relationship(back_populates="payments")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    merchant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("merchants.id", ondelete="SET NULL"))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    frequency: Mapped[str] = mapped_column(String(16), default="monthly")
    next_payment_date: Mapped[Optional[date]] = mapped_column(Date)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    started_on: Mapped[Optional[date]] = mapped_column(Date)
    cancelled_on: Mapped[Optional[date]] = mapped_column(Date)
    previous_amount_minor: Mapped[Optional[int]] = mapped_column(BigInteger)
    price_changed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    detected: Mapped[bool] = mapped_column(Boolean, default=False)  # created from recurring-pattern detection
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    merchant: Mapped[Optional[Merchant]] = relationship()


# ---------------------------------------------------------------------------
# Imports and bank synchronisation
# ---------------------------------------------------------------------------


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(8))  # csv|xlsx|ofx|qfx|pdf
    status: Mapped[str] = mapped_column(String(16), default="preview")  # preview|validated|completed|failed|cancelled
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    bank_detected: Mapped[str] = mapped_column(String(120), default="")
    headers: Mapped[list[str]] = mapped_column(JSON, default=list)
    raw_rows: Mapped[list[list[str]]] = mapped_column(JSON, default=list)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    normalized: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
    # How rows were read (csv, pdf-table, pdf-text, pdf-ocr, image-ocr, docx-table…) and parser notes.
    parse_info: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("bank_connections.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual|scheduled
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|failed
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)


# ---------------------------------------------------------------------------
# Alerts, notifications, net worth
# ---------------------------------------------------------------------------


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    metric: Mapped[str] = mapped_column(String(48))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    operator: Mapped[str] = mapped_column(String(8), default=">=")
    threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 4))  # major units / percent / days by metric
    channels: Mapped[Optional[list[str]]] = mapped_column(JSON)  # None = use the category defaults
    cooldown_policy: Mapped[str] = mapped_column(String(24), default="once_per_threshold")
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Per-entity firing state used by the cooldown policies, e.g. {"budget:3": "2026-09-01"}.
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("alert_rules.id", ondelete="SET NULL"), index=True)
    metric: Mapped[str] = mapped_column(String(48))
    category: Mapped[str] = mapped_column(String(24), default="system")
    dedupe_key: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info|success|warning|critical
    value: Mapped[str] = mapped_column(String(64), default="")
    threshold: Mapped[str] = mapped_column(String(64), default="")
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    triggered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    deliveries: Mapped[list["NotificationDelivery"]] = relationship(back_populates="alert_event", cascade="all, delete-orphan")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    alert_event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("alert_events.id", ondelete="SET NULL"))
    category: Mapped[str] = mapped_column(String(24), default="system")
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(String(255), default="")
    read_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    alert_event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("alert_events.id", ondelete="CASCADE"), index=True)
    notification_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notifications.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(32), default="")
    # queued|sent|failed|skipped|mocked|logged — "mocked"/"logged" are explicit so nothing pretends to be delivered.
    status: Mapped[str] = mapped_column(String(16), default="queued")
    destination: Mapped[str] = mapped_column(String(64), default="")  # masked
    error: Mapped[Optional[str]] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    alert_event: Mapped[Optional[AlertEvent]] = relationship(back_populates="deliveries")


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    assets_minor: Mapped[int] = mapped_column(BigInteger)
    liabilities_minor: Mapped[int] = mapped_column(BigInteger)
    net_worth_minor: Mapped[int] = mapped_column(BigInteger)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
