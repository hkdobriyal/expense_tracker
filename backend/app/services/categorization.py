"""Merchant normalisation and the categorisation rules engine.

Order of precedence when a transaction arrives without a category:
1. User rules (lowest ``priority`` first; first match wins)
2. The merchant's default category (learned when the user recategorises)
3. Built-in keyword hints (``catalog.KEYWORD_HINTS``)
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CategorizationRule, Category, Merchant, Tag, Transaction
from .catalog import KEYWORD_HINTS

_NON_WORD = re.compile(r"[^a-z0-9&]+")


def normalize_merchant(name: str) -> str:
    return _NON_WORD.sub(" ", name.lower()).strip()[:120]


def get_or_create_merchant(db: Session, user_id: int, name: str | None) -> Merchant | None:
    if not name or not name.strip():
        return None
    normalized = normalize_merchant(name)
    if not normalized:
        return None
    merchant = db.scalar(select(Merchant).where(Merchant.user_id == user_id, Merchant.normalized_name == normalized))
    if merchant is None:
        merchant = Merchant(user_id=user_id, name=name.strip()[:120], normalized_name=normalized)
        db.add(merchant)
        db.flush()
    return merchant


def _field_values(rule: CategorizationRule, txn: Transaction, merchant_name: str) -> list[str]:
    fields = {
        "description": [txn.description or "", txn.raw_description or ""],
        "merchant": [merchant_name],
        "notes": [txn.notes or ""],
    }
    if rule.field == "any":
        return fields["description"] + fields["merchant"] + fields["notes"]
    return fields.get(rule.field, [])


def rule_matches(rule: CategorizationRule, txn: Transaction, merchant_name: str = "") -> bool:
    if not rule.enabled:
        return False
    if rule.account_id and rule.account_id != txn.account_id:
        return False
    if rule.transaction_type and rule.transaction_type != txn.type:
        return False
    amount = abs(txn.amount_minor)
    if rule.amount_min_minor is not None and amount < rule.amount_min_minor:
        return False
    if rule.amount_max_minor is not None and amount > rule.amount_max_minor:
        return False

    pattern = rule.pattern if rule.case_sensitive else rule.pattern.lower()
    for raw in _field_values(rule, txn, merchant_name):
        value = raw if rule.case_sensitive else raw.lower()
        if not value:
            continue
        if rule.match_type == "equals" and value.strip() == pattern.strip():
            return True
        if rule.match_type == "contains" and pattern in value:
            return True
        if rule.match_type == "starts_with" and value.startswith(pattern):
            return True
        if rule.match_type == "ends_with" and value.endswith(pattern):
            return True
        if rule.match_type == "regex":
            try:
                if re.search(rule.pattern, raw, 0 if rule.case_sensitive else re.IGNORECASE):
                    return True
            except re.error:
                return False
    return False


def validate_regex(pattern: str) -> str | None:
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"Invalid regular expression: {exc}"
    if len(pattern) > 255:
        return "Pattern is too long"
    return None


def apply_rules(db: Session, user_id: int, txn: Transaction, rules: list[CategorizationRule] | None = None) -> CategorizationRule | None:
    """Apply the first matching rule to ``txn`` (in place). Returns the rule that matched."""
    if rules is None:
        rules = db.scalars(
            select(CategorizationRule).where(CategorizationRule.user_id == user_id, CategorizationRule.enabled.is_(True)).order_by(CategorizationRule.priority, CategorizationRule.id)
        ).all()
    merchant_name = txn.merchant.name if txn.merchant is not None else ""
    for rule in rules:
        if not rule_matches(rule, txn, merchant_name):
            continue
        if rule.set_category_id:
            txn.category_id = rule.set_category_id
        if rule.set_merchant_name:
            merchant = get_or_create_merchant(db, user_id, rule.set_merchant_name)
            txn.merchant_id = merchant.id if merchant else txn.merchant_id
        if rule.add_tag_ids:
            existing = {t.id for t in txn.tags}
            for tag in db.scalars(select(Tag).where(Tag.user_id == user_id, Tag.id.in_(rule.add_tag_ids))).all():
                if tag.id not in existing:
                    txn.tags.append(tag)
        if rule.mark_reviewed:
            txn.reviewed = True
        rule.apply_count += 1
        return rule
    return None


def _category_by_path(categories: list[Category], path: str) -> Category | None:
    parent_name, _, child_name = path.partition("/")
    parents = [c for c in categories if c.parent_id is None and c.name.lower() == parent_name.lower()]
    if not parents:
        return None
    if not child_name:
        return parents[0]
    for c in categories:
        if c.parent_id == parents[0].id and c.name.lower() == child_name.lower():
            return c
    return parents[0]


def suggest_category(db: Session, user_id: int, text: str, merchant: Merchant | None, txn_type: str) -> int | None:
    if merchant is not None and merchant.default_category_id:
        return merchant.default_category_id
    haystack = f" {text.lower()} {(merchant.name.lower() if merchant else '')} "
    categories = db.scalars(select(Category).where(Category.user_id == user_id, Category.is_archived.is_(False))).all()
    wanted_kind = "income" if txn_type in ("income",) else "expense"
    for keyword, path in KEYWORD_HINTS:
        if keyword in haystack:
            cat = _category_by_path(categories, path)
            if cat is not None and cat.kind == wanted_kind:
                return cat.id
    return None


def auto_categorize(db: Session, user_id: int, txn: Transaction) -> None:
    """Fill the category of a transaction that arrived without one.

    Order: user rules → the merchant's learned default → ML model (if confident)
    → built-in keyword hints. The winner is recorded in ``category_source``.
    """
    from . import ml

    matched = apply_rules(db, user_id, txn)
    if matched is not None and matched.set_category_id:
        txn.category_source, txn.category_confidence = "rule", 1.0
    if txn.category_id is None and txn.type in ("expense", "income", "refund"):
        if txn.merchant is not None and txn.merchant.default_category_id:
            txn.category_id = txn.merchant.default_category_id
            txn.category_source, txn.category_confidence = "merchant", 0.95
        else:
            predictions = ml.predict(db, user_id, txn.description, txn.merchant.name if txn.merchant else None,
                                     txn.raw_description, "income" if txn.type == "income" else "expense", txn.amount_minor)
            best = predictions[0] if predictions else None
            if best and best[1] >= ml.AUTO_APPLY:
                txn.category_id = best[0]
                txn.category_source, txn.category_confidence = "ml", best[1]
            else:
                hint = suggest_category(db, user_id, f"{txn.description} {txn.raw_description}", None, txn.type)
                if hint:
                    txn.category_id = hint
                    txn.category_source, txn.category_confidence = "keyword", 0.6
            if txn.category_id is None and predictions and predictions[0][1] >= ml.SUGGEST:
                txn.extracted = {**(txn.extracted or {}), "suggestions": [{"category_id": c, "confidence": p} for c, p in predictions]}
    if (matched is None or not matched.mark_reviewed) and txn.source in ("import", "bank", "sms"):
        # Machine-created transactions are flagged for review unless a user rule vouched for them.
        txn.reviewed = bool(matched is not None and matched.mark_reviewed)
