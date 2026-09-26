"""Request bodies (validation boundary). Money arrives as decimal strings/numbers in major units."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import ACCOUNT_TYPES, BUDGET_PERIODS, CHANNELS, FREQUENCIES, GOAL_TYPES, TRANSACTION_TYPES


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Money = Decimal
TxnType = Literal[TRANSACTION_TYPES]  # type: ignore[valid-type]
AccountType = Literal[ACCOUNT_TYPES]  # type: ignore[valid-type]
Frequency = Literal[FREQUENCIES]  # type: ignore[valid-type]


# --- Auth & settings ----------------------------------------------------------------------------

class RegisterIn(Input):
    email: str = Field(max_length=255)
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(default="", max_length=120)
    base_currency: str = Field(default="INR", min_length=3, max_length=3)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1] or len(v) < 5:
            raise ValueError("Enter a valid email address")
        return v


class LoginIn(Input):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)


class ChangePasswordIn(Input):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class SettingsIn(Input):
    base_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    timezone: Optional[str] = Field(default=None, max_length=64)
    locale: Optional[str] = Field(default=None, max_length=16)
    week_start: Optional[int] = Field(default=None, ge=0, le=6)
    default_account_id: Optional[int] = None
    theme: Optional[Literal["dark", "light", "system"]] = None
    reduce_motion: Optional[bool] = None
    sound_enabled: Optional[bool] = None
    onboarding_dismissed: Optional[bool] = None
    display_name: Optional[str] = Field(default=None, max_length=120)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    contact_phone: Optional[str] = Field(default=None, max_length=32)
    whatsapp_number: Optional[str] = Field(default=None, max_length=32)
    channels: Optional[dict[str, bool]] = None
    notification_matrix: Optional[dict[str, dict[str, bool]]] = None


# --- Ledger -------------------------------------------------------------------------------------

class AccountIn(Input):
    name: str = Field(min_length=1, max_length=120)
    type: AccountType = "savings"
    institution: str = Field(default="", max_length=120)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    opening_balance: Money = Decimal(0)  # for liabilities: the amount owed (positive)
    opening_date: Optional[date] = None
    credit_limit: Optional[Money] = None
    account_number_mask: str = Field(default="", max_length=16)
    color: str = Field(default="", max_length=16)
    include_in_net_worth: bool = True
    is_archived: bool = False


class CategoryIn(Input):
    name: str = Field(min_length=1, max_length=80)
    parent_id: Optional[int] = None
    kind: Literal["expense", "income"] = "expense"
    color: str = Field(default="", max_length=16)
    icon: str = Field(default="", max_length=32)
    is_archived: bool = False


class TagIn(Input):
    name: str = Field(min_length=1, max_length=48)
    color: str = Field(default="", max_length=16)


class SplitIn(Input):
    category_id: Optional[int] = None
    amount: Money
    note: str = Field(default="", max_length=255)


class TransactionIn(Input):
    type: TxnType = "expense"
    account_id: int
    date: date
    amount: Money
    description: str = Field(min_length=1, max_length=255)
    merchant: Optional[str] = Field(default=None, max_length=120)
    category_id: Optional[int] = None
    notes: str = Field(default="", max_length=5000)
    payment_method: str = Field(default="", max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=20)
    transfer_account_id: Optional[int] = None
    transfer_amount: Optional[Money] = None
    fx_rate: Optional[Decimal] = Field(default=None, gt=0)
    original_amount: Optional[Money] = None
    original_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    is_recurring: bool = False
    reviewed: Optional[bool] = True
    splits: Optional[list[SplitIn]] = None


class BulkIn(Input):
    ids: list[int] = Field(min_length=1, max_length=1000)
    action: Literal["delete", "categorize", "mark_reviewed", "mark_unreviewed", "add_tag", "remove_tag"]
    category_id: Optional[int] = None
    tag: Optional[str] = Field(default=None, max_length=48)


class RuleIn(Input):
    name: str = Field(default="", max_length=120)
    priority: int = Field(default=100, ge=0, le=10000)
    field: Literal["description", "merchant", "notes", "any"] = "any"
    match_type: Literal["contains", "equals", "starts_with", "ends_with", "regex"] = "contains"
    pattern: str = Field(min_length=1, max_length=255)
    case_sensitive: bool = False
    amount_min: Optional[Money] = None
    amount_max: Optional[Money] = None
    account_id: Optional[int] = None
    transaction_type: Optional[TxnType] = None
    set_category_id: Optional[int] = None
    set_merchant_name: Optional[str] = Field(default=None, max_length=120)
    add_tags: list[str] = Field(default_factory=list, max_length=10)
    mark_reviewed: bool = False
    enabled: bool = True


class RecurringIn(Input):
    name: str = Field(min_length=1, max_length=120)
    type: TxnType = "expense"
    account_id: int
    transfer_account_id: Optional[int] = None
    amount: Money
    category_id: Optional[int] = None
    merchant_name: str = Field(default="", max_length=120)
    payment_method: str = Field(default="", max_length=32)
    frequency: Frequency = "monthly"
    next_date: date
    end_date: Optional[date] = None
    auto_create: bool = True
    active: bool = True


class ExchangeRateIn(Input):
    base_currency: str = Field(min_length=3, max_length=3)
    quote_currency: str = Field(min_length=3, max_length=3)
    rate: Decimal = Field(gt=0)
    as_of: date


# --- Planning -----------------------------------------------------------------------------------

class BudgetIn(Input):
    name: str = Field(min_length=1, max_length=120)
    category_id: Optional[int] = None
    period: Literal[BUDGET_PERIODS] = "monthly"  # type: ignore[valid-type]
    amount: Money
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    include_subcategories: bool = True
    active: bool = True
    alert_thresholds: Optional[list[int]] = Field(default=None, max_length=6)  # e.g. [80, 100] creates alert rules


class GoalIn(Input):
    name: str = Field(min_length=1, max_length=120)
    goal_type: Literal[GOAL_TYPES] = "custom"  # type: ignore[valid-type]
    target: Money
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    target_date: Optional[date] = None
    start_date: Optional[date] = None
    linked_account_id: Optional[int] = None
    color: str = Field(default="", max_length=16)
    status: Literal["active", "completed", "archived"] = "active"
    initial_amount: Optional[Money] = None


class ContributionIn(Input):
    amount: Money  # negative = withdrawal
    date: date
    note: str = Field(default="", max_length=255)


class BillIn(Input):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(default="", max_length=120)
    amount: Money
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    frequency: Frequency = "monthly"
    next_due_date: date
    autopay: bool = False
    account_id: Optional[int] = None
    category_id: Optional[int] = None
    notes: str = Field(default="", max_length=2000)
    active: bool = True


class BillPayIn(Input):
    paid_on: Optional[date] = None
    amount: Optional[Money] = None
    account_id: Optional[int] = None
    create_transaction: bool = True


class SubscriptionIn(Input):
    name: str = Field(min_length=1, max_length=120)
    merchant: Optional[str] = Field(default=None, max_length=120)
    amount: Money
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    frequency: Frequency = "monthly"
    next_payment_date: Optional[date] = None
    account_id: Optional[int] = None
    category_id: Optional[int] = None
    active: bool = True
    started_on: Optional[date] = None
    notes: str = Field(default="", max_length=2000)
    detected: bool = False


# --- Alerts & integrations ----------------------------------------------------------------------

class AlertRuleIn(Input):
    name: str = Field(min_length=1, max_length=120)
    metric: str = Field(max_length=48)
    params: dict = Field(default_factory=dict)
    operator: str = Field(default=">=", max_length=8)
    threshold: Optional[Decimal] = None
    channels: Optional[list[Literal[CHANNELS]]] = None  # type: ignore[valid-type]
    cooldown_policy: Literal["once_per_threshold", "once_per_day", "cooldown", "every_event"] = "once_per_threshold"
    cooldown_minutes: int = Field(default=0, ge=0, le=60 * 24 * 90)
    enabled: bool = True


class ImportMappingIn(Input):
    account_id: int
    mapping: dict


class ImportCommitIn(Input):
    include_duplicate_rows: list[int] = Field(default_factory=list)
    type_overrides: dict[int, TxnType] = Field(default_factory=dict)


class BankConnectIn(Input):
    provider: str = Field(max_length=32)
    institution_id: str = Field(max_length=64)
    params: dict = Field(default_factory=dict)


class BankLinkIn(Input):
    account_external_ids: list[str] = Field(min_length=1, max_length=20)


class SmsIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    account_id: Optional[int] = None
    sender: Optional[str] = Field(default=None, max_length=64)


class SmsCommitIn(Input):
    text: str = Field(min_length=3, max_length=2000)
    account_id: int
    type: Optional[TxnType] = None
    category_id: Optional[int] = None
    date: Optional[date] = None


__all__ = [name for name in dir() if name.endswith("In")]
