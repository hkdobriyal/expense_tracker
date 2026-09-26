"""Settings, accounts, categories, tags, merchants, categorisation rules and exchange rates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..db import get_db
from ..deps import CurrentUser, client_ip, get_current_user, get_owned
from ..models import (
    ACCOUNT_TYPES, LIABILITY_ACCOUNT_TYPES, Account, CategorizationRule, Category, ExchangeRate, Merchant, Tag, Transaction, User,
    UserSettings, transaction_tags,
)
from ..money import SUPPORTED_CURRENCIES, MoneyError, normalize_currency, to_minor
from ..schemas import AccountIn, CategoryIn, ExchangeRateIn, RuleIn, SettingsIn, TagIn
from ..security import hash_token, new_token
from ..services import audit, banking, ledger
from ..services.categorization import apply_rules, rule_matches, validate_regex
from ..services.transactions import resolve_tags

router = APIRouter(prefix="/api", tags=["ledger"])


# --- Settings -----------------------------------------------------------------------------------

@router.get("/settings")
def get_settings_(current: CurrentUser = Depends(get_current_user)):
    return {"user": ser.user(current.user), "settings": ser.settings(current.settings)}


@router.patch("/settings")
def update_settings(body: SettingsIn, request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(UserSettings, current.id)
    data = body.model_dump(exclude_unset=True)
    if "base_currency" in data and data["base_currency"]:
        code = normalize_currency(data["base_currency"])
        if code not in SUPPORTED_CURRENCIES:
            raise HTTPException(422, "Unsupported currency")
        has_txns = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.user_id == current.id))
        if has_txns and code != s.base_currency:
            raise HTTPException(409, "The base currency cannot change after transactions exist (stored conversions would become inconsistent).")
        s.base_currency = code
    if "default_account_id" in data and data["default_account_id"] is not None:
        get_owned(db, Account, data["default_account_id"], current, "Account")
    for key in ("timezone", "locale", "week_start", "default_account_id", "theme", "reduce_motion", "sound_enabled",
                "onboarding_dismissed", "contact_email", "contact_phone", "whatsapp_number"):
        if key in data:
            setattr(s, key, data[key])
    if data.get("display_name") is not None:
        db.get(User, current.id).display_name = data["display_name"]
    for channel, enabled in (data.get("channels") or {}).items():
        if channel in ("in_app", "email", "sms", "whatsapp", "push"):
            setattr(s, f"channel_{channel}", bool(enabled))
    if data.get("notification_matrix") is not None:
        matrix = dict(s.notification_matrix or {})
        for category, channels in data["notification_matrix"].items():
            matrix[category] = {c: bool(v) for c, v in channels.items() if c in ("in_app", "email", "sms", "whatsapp", "push")}
        s.notification_matrix = matrix
    audit.record(db, current.id, "settings.changed", "settings", current.id, {"fields": sorted(data)}, client_ip(request))
    db.commit()
    return {"user": ser.user(db.get(User, current.id)), "settings": ser.settings(s)}


@router.post("/settings/sms-webhook-token")
def rotate_sms_token(request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create (or rotate) the token an SMS-forwarder app uses to post bank SMS. Shown once."""
    token = f"lsms_{new_token()}"
    s = db.get(UserSettings, current.id)
    s.sms_webhook_token_hash = hash_token(token)
    s.sms_webhook_token_hint = token[-4:]
    audit.record(db, current.id, "integration.sms_token_rotated", "settings", current.id, ip=client_ip(request))
    db.commit()
    return {"token": token, "hint": token[-4:]}


@router.delete("/settings/sms-webhook-token")
def revoke_sms_token(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(UserSettings, current.id)
    s.sms_webhook_token_hash = None
    s.sms_webhook_token_hint = None
    db.commit()
    return {"ok": True}


# --- Accounts -----------------------------------------------------------------------------------

def _account_out(db: Session, current: CurrentUser, accounts: list[Account]) -> list[dict]:
    converted = {b.account_id: b for b in ledger.balances_in_base(db, current.id, current.base_currency, None, accounts)}
    return [ser.account(a, converted[a.id].balance_minor, converted[a.id].base_minor, banking.reconciliation(db, a)) for a in accounts]


def _apply_account(db: Session, acc: Account, body: AccountIn) -> None:
    try:
        currency = normalize_currency(body.currency)
        opening = to_minor(body.opening_balance, currency)
        limit = to_minor(body.credit_limit, currency) if body.credit_limit is not None else None
    except MoneyError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.type not in ACCOUNT_TYPES:
        raise HTTPException(422, "Unknown account type")
    acc.name = body.name
    acc.type = body.type
    acc.institution = body.institution
    acc.currency = currency
    # Liabilities are entered as "amount owed" and stored as a negative balance.
    acc.opening_balance_minor = -abs(opening) if body.type in LIABILITY_ACCOUNT_TYPES else opening
    acc.opening_date = body.opening_date
    acc.credit_limit_minor = limit
    acc.account_number_mask = body.account_number_mask
    acc.color = body.color
    acc.include_in_net_worth = body.include_in_net_worth
    acc.is_archived = body.is_archived


@router.get("/accounts")
def list_accounts(include_archived: bool = False, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Account).where(Account.user_id == current.id)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    return _account_out(db, current, db.scalars(stmt.order_by(Account.type, Account.name)).all())


@router.post("/accounts", status_code=201)
def create_account(body: AccountIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = Account(user_id=current.id)
    _apply_account(db, acc, body)
    db.add(acc)
    db.flush()
    s = db.get(UserSettings, current.id)
    if s.default_account_id is None and acc.type in ("current", "savings", "cash", "wallet"):
        s.default_account_id = acc.id
    db.commit()
    return _account_out(db, current, [acc])[0]


@router.get("/accounts/{account_id}")
def get_account(account_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return _account_out(db, current, [get_owned(db, Account, account_id, current, "Account")])[0]


@router.put("/accounts/{account_id}")
def update_account(account_id: int, body: AccountIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = get_owned(db, Account, account_id, current, "Account")
    if body.currency.upper() != acc.currency:
        has_txns = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.account_id == acc.id))
        if has_txns:
            raise HTTPException(409, "An account's currency cannot change once it has transactions")
    _apply_account(db, acc, body)
    db.commit()
    return _account_out(db, current, [acc])[0]


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, request: Request, confirm: bool = False, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = get_owned(db, Account, account_id, current, "Account")
    count = db.scalar(select(func.count()).select_from(Transaction).where((Transaction.account_id == acc.id) | (Transaction.transfer_account_id == acc.id))) or 0
    if count and not confirm:
        raise HTTPException(409, f"This account has {count} transaction(s). Archive it instead, or delete with confirm=true to remove them too.")
    audit.record(db, current.id, "account.deleted", "account", acc.id, {"name": acc.name, "transactions_deleted": count}, client_ip(request))
    db.delete(acc)
    db.commit()
    return {"deleted": True, "transactions_deleted": count}


# --- Categories, tags, merchants ----------------------------------------------------------------

@router.get("/categories")
def list_categories(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    cats = db.scalars(select(Category).where(Category.user_id == current.id).order_by(Category.kind, Category.name)).all()
    return [ser.category(c) for c in cats]


def _check_parent(db: Session, current: CurrentUser, parent_id: int | None, kind: str, self_id: int | None = None) -> None:
    if parent_id is None:
        return
    parent = get_owned(db, Category, parent_id, current, "Parent category")
    if parent.parent_id is not None:
        raise HTTPException(422, "Categories support two levels: choose a top-level parent")
    if parent.kind != kind:
        raise HTTPException(422, "A subcategory must have the same kind as its parent")
    if self_id is not None and parent.id == self_id:
        raise HTTPException(422, "A category cannot be its own parent")


def _unique_name(db: Session, current: CurrentUser, name: str, parent_id: int | None, self_id: int | None = None) -> None:
    stmt = select(Category).where(Category.user_id == current.id, func.lower(Category.name) == name.lower())
    stmt = stmt.where(Category.parent_id.is_(None) if parent_id is None else Category.parent_id == parent_id)
    existing = db.scalar(stmt)
    if existing is not None and existing.id != self_id:
        raise HTTPException(409, "A category with this name already exists here")


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_parent(db, current, body.parent_id, body.kind)
    _unique_name(db, current, body.name, body.parent_id)
    parent = db.get(Category, body.parent_id) if body.parent_id else None
    cat = Category(user_id=current.id, name=body.name, parent_id=body.parent_id, kind=body.kind, color=body.color or (parent.color if parent else ""), icon=body.icon or (parent.icon if parent else ""), is_archived=body.is_archived)
    db.add(cat)
    db.commit()
    return ser.category(cat)


@router.put("/categories/{category_id}")
def update_category(category_id: int, body: CategoryIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    cat = get_owned(db, Category, category_id, current, "Category")
    if body.parent_id is not None and db.scalar(select(func.count()).select_from(Category).where(Category.parent_id == cat.id)):
        raise HTTPException(422, "A category with subcategories cannot become a subcategory")
    _check_parent(db, current, body.parent_id, body.kind, cat.id)
    _unique_name(db, current, body.name, body.parent_id, cat.id)
    cat.name, cat.parent_id, cat.kind, cat.color, cat.icon, cat.is_archived = body.name, body.parent_id, body.kind, body.color, body.icon, body.is_archived
    db.commit()
    return ser.category(cat)


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, reassign_to: int | None = None, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    cat = get_owned(db, Category, category_id, current, "Category")
    ids = ledger.descendant_ids(db.scalars(select(Category).where(Category.user_id == current.id)).all(), cat.id)
    target = None
    if reassign_to is not None:
        target = get_owned(db, Category, reassign_to, current, "Target category")
        if target.id in ids:
            raise HTTPException(422, "Cannot move transactions into the category being deleted")
    moved = 0
    for txn in db.scalars(select(Transaction).where(Transaction.user_id == current.id, Transaction.category_id.in_(ids))).all():
        txn.category_id = target.id if target else None
        moved += 1
    db.delete(cat)
    db.commit()
    return {"deleted": True, "transactions_updated": moved}


@router.get("/tags")
def list_tags(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Tag, func.count(transaction_tags.c.transaction_id)).outerjoin(transaction_tags, transaction_tags.c.tag_id == Tag.id)
        .where(Tag.user_id == current.id).group_by(Tag.id).order_by(Tag.name)
    ).all()
    return [{**ser.tag(t), "count": int(c)} for t, c in rows]


@router.post("/tags", status_code=201)
def create_tag(body: TagIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    tag = resolve_tags(db, current.id, [body.name])[0]
    tag.color = body.color or tag.color
    db.commit()
    return ser.tag(tag)


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_owned(db, Tag, tag_id, current, "Tag"))
    db.commit()
    return {"deleted": True}


@router.get("/merchants")
def list_merchants(q: str = "", current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = (
        select(Merchant, func.count(Transaction.id), func.coalesce(func.sum(Transaction.base_amount_minor), 0), func.max(Transaction.date))
        .outerjoin(Transaction, (Transaction.merchant_id == Merchant.id) & (Transaction.type == "expense"))
        .where(Merchant.user_id == current.id).group_by(Merchant.id)
    )
    if q:
        stmt = stmt.where(Merchant.name.ilike(f"%{q}%"))
    rows = db.execute(stmt.order_by(func.coalesce(func.sum(Transaction.base_amount_minor), 0).desc()).limit(500)).all()
    return [{**ser.merchant(m), "transaction_count": int(c), "total_spent": int(t), "last_seen": d.isoformat() if d else None} for m, c, t, d in rows]


@router.patch("/merchants/{merchant_id}")
def update_merchant(merchant_id: int, body: dict, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_owned(db, Merchant, merchant_id, current, "Merchant")
    if "name" in body and str(body["name"]).strip():
        m.name = str(body["name"]).strip()[:120]
    if "default_category_id" in body:
        cid = body["default_category_id"]
        if cid is not None:
            get_owned(db, Category, int(cid), current, "Category")
        m.default_category_id = cid
    db.commit()
    return ser.merchant(m)


# --- Categorisation rules -----------------------------------------------------------------------

def _apply_rule_body(db: Session, current: CurrentUser, rule: CategorizationRule, body: RuleIn) -> None:
    if body.match_type == "regex":
        problem = validate_regex(body.pattern)
        if problem:
            raise HTTPException(422, problem)
    if body.set_category_id is not None:
        get_owned(db, Category, body.set_category_id, current, "Category")
    if body.account_id is not None:
        get_owned(db, Account, body.account_id, current, "Account")
    if not (body.set_category_id or body.set_merchant_name or body.add_tags or body.mark_reviewed):
        raise HTTPException(422, "A rule must set a category, merchant or tag, or mark as reviewed")
    for key in ("name", "priority", "field", "match_type", "pattern", "case_sensitive", "account_id", "transaction_type", "set_category_id", "set_merchant_name", "mark_reviewed", "enabled"):
        setattr(rule, key, getattr(body, key))
    base = current.base_currency
    rule.amount_min_minor = to_minor(body.amount_min, base) if body.amount_min is not None else None
    rule.amount_max_minor = to_minor(body.amount_max, base) if body.amount_max is not None else None
    rule.add_tag_ids = [t.id for t in resolve_tags(db, current.id, body.add_tags)]


@router.get("/rules")
def list_rules(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rules = db.scalars(select(CategorizationRule).where(CategorizationRule.user_id == current.id).order_by(CategorizationRule.priority, CategorizationRule.id)).all()
    return [ser.rule(r) for r in rules]


@router.post("/rules", status_code=201)
def create_rule(body: RuleIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = CategorizationRule(user_id=current.id, pattern=body.pattern)
    _apply_rule_body(db, current, rule, body)
    db.add(rule)
    db.commit()
    return ser.rule(rule)


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = get_owned(db, CategorizationRule, rule_id, current, "Rule")
    _apply_rule_body(db, current, rule, body)
    db.commit()
    return ser.rule(rule)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_owned(db, CategorizationRule, rule_id, current, "Rule"))
    db.commit()
    return {"deleted": True}


@router.post("/rules/{rule_id}/preview")
def preview_rule(rule_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Which existing transactions would this rule match? (Nothing is changed.)"""
    rule = get_owned(db, CategorizationRule, rule_id, current, "Rule")
    matches = []
    for txn in db.scalars(select(Transaction).where(Transaction.user_id == current.id).order_by(Transaction.date.desc()).limit(5000)).all():
        if rule_matches(rule, txn, txn.merchant.name if txn.merchant else ""):
            matches.append(txn)
    return {"count": len(matches), "sample": [ser.transaction(t) for t in matches[:20]]}


@router.post("/rules/{rule_id}/apply")
def apply_rule_to_existing(rule_id: int, only_uncategorized: bool = True, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = get_owned(db, CategorizationRule, rule_id, current, "Rule")
    stmt = select(Transaction).where(Transaction.user_id == current.id)
    if only_uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    changed = 0
    for txn in db.scalars(stmt).all():
        if not txn.splits and apply_rules(db, current.id, txn, [rule]) is not None:
            changed += 1
    db.commit()
    return {"updated": changed}


# --- Exchange rates -----------------------------------------------------------------------------

@router.get("/exchange-rates")
def list_rates(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ExchangeRate).where(ExchangeRate.user_id == current.id).order_by(ExchangeRate.as_of.desc())).all()
    return [ser.exchange_rate(r) for r in rows]


@router.post("/exchange-rates", status_code=201)
def upsert_rate(body: ExchangeRateIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    base, quote = normalize_currency(body.base_currency), normalize_currency(body.quote_currency)
    if base == quote:
        raise HTTPException(422, "Choose two different currencies")
    rate = db.scalar(select(ExchangeRate).where(ExchangeRate.user_id == current.id, ExchangeRate.base_currency == base, ExchangeRate.quote_currency == quote, ExchangeRate.as_of == body.as_of))
    if rate is None:
        rate = ExchangeRate(user_id=current.id, base_currency=base, quote_currency=quote, as_of=body.as_of, rate=body.rate)
        db.add(rate)
    rate.rate = body.rate
    db.commit()
    return ser.exchange_rate(rate)


@router.delete("/exchange-rates/{rate_id}")
def delete_rate(rate_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_owned(db, ExchangeRate, rate_id, current, "Exchange rate"))
    db.commit()
    return {"deleted": True}

