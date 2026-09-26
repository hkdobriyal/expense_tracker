"""Model → JSON shapes returned by the API.

Amounts are returned as integer minor units (``*_minor`` / plain ints in
analytics) together with their currency; the frontend formats them. Secrets
such as ``BankConnection.credentials_encrypted`` are never serialised.
"""

from __future__ import annotations

from .models import (
    Account, AlertEvent, AlertRule, Attachment, BankConnection, Bill, Budget, CategorizationRule, Category, ExchangeRate, Goal,
    GoalContribution, ImportJob, Merchant, Notification, NotificationDelivery, RecurringTransaction, Subscription, SyncLog, Tag,
    Transaction, User, UserSettings,
)


def _iso(value):
    return value.isoformat() if value is not None else None


def user(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "is_demo": u.is_demo, "created_at": _iso(u.created_at)}


def settings(s: UserSettings) -> dict:
    return {
        "base_currency": s.base_currency, "timezone": s.timezone, "locale": s.locale, "week_start": s.week_start,
        "default_account_id": s.default_account_id, "theme": s.theme, "reduce_motion": s.reduce_motion, "sound_enabled": s.sound_enabled,
        "onboarding_dismissed": s.onboarding_dismissed, "contact_email": s.contact_email, "contact_phone": s.contact_phone,
        "whatsapp_number": s.whatsapp_number,
        "channels": {c: getattr(s, f"channel_{c}") for c in ("in_app", "email", "sms", "whatsapp", "push")},
        "notification_matrix": s.notification_matrix,
        "sms_webhook_configured": bool(s.sms_webhook_token_hash), "sms_webhook_token_hint": s.sms_webhook_token_hint,
    }


def account(a: Account, balance: int, base_balance: int | None, reconciliation: dict | None = None) -> dict:
    available = None
    if a.type == "credit_card" and a.credit_limit_minor is not None:
        available = a.credit_limit_minor + balance  # balance is negative when money is owed
    elif a.type not in ("loan", "mortgage", "liability"):
        available = balance
    return {
        "id": a.id, "name": a.name, "type": a.type, "institution": a.institution, "currency": a.currency,
        "opening_balance_minor": a.opening_balance_minor, "opening_date": _iso(a.opening_date), "credit_limit_minor": a.credit_limit_minor,
        "account_number_mask": a.account_number_mask, "color": a.color, "include_in_net_worth": a.include_in_net_worth,
        "is_archived": a.is_archived, "is_liability": a.is_liability,
        "balance_minor": balance, "base_balance_minor": base_balance, "available_minor": available,
        "bank_connection_id": a.bank_connection_id, "connection_status": a.bank_connection.status if a.bank_connection else None,
        "last_synced_at": _iso(a.last_synced_at), "reconciliation": reconciliation,
    }


def category(c: Category) -> dict:
    return {"id": c.id, "name": c.name, "parent_id": c.parent_id, "kind": c.kind, "color": c.color, "icon": c.icon, "is_archived": c.is_archived}


def merchant(m: Merchant) -> dict:
    return {"id": m.id, "name": m.name, "default_category_id": m.default_category_id}


def tag(t: Tag) -> dict:
    return {"id": t.id, "name": t.name, "color": t.color}


def transaction(t: Transaction) -> dict:
    return {
        "id": t.id, "type": t.type, "date": t.date.isoformat(), "account_id": t.account_id,
        "account_name": t.account.name if t.account else None,
        "amount_minor": t.amount_minor, "currency": t.currency, "base_amount_minor": t.base_amount_minor,
        "fx_rate": str(t.fx_rate) if t.fx_rate is not None else None,
        "original_amount_minor": t.original_amount_minor, "original_currency": t.original_currency,
        "transfer_account_id": t.transfer_account_id, "transfer_account_name": t.transfer_account.name if t.transfer_account else None,
        "transfer_amount_minor": t.transfer_amount_minor,
        "description": t.description, "merchant_id": t.merchant_id, "merchant": t.merchant.name if t.merchant else None,
        "category_id": t.category_id, "category": t.category.name if t.category else None,
        "category_color": t.category.color if t.category else None,
        "notes": t.notes, "payment_method": t.payment_method, "is_recurring": t.is_recurring, "reviewed": t.reviewed,
        "source": t.source, "external_id": t.external_id, "raw_description": t.raw_description,
        "tags": [tag(x) for x in t.tags],
        "splits": [{"id": s.id, "category_id": s.category_id, "category": s.category.name if s.category else None, "amount_minor": s.amount_minor, "note": s.note} for s in t.splits],
        "attachments": [attachment(a) for a in t.attachments],
        "created_at": _iso(t.created_at), "updated_at": _iso(t.updated_at),
    }


def attachment(a: Attachment) -> dict:
    return {"id": a.id, "filename": a.filename, "content_type": a.content_type, "size_bytes": a.size_bytes, "created_at": _iso(a.created_at)}


def budget(b: Budget, status: dict) -> dict:
    return {
        "id": b.id, "name": b.name, "category_id": b.category_id, "category": b.category.name if b.category else "All spending",
        "category_color": b.category.color if b.category else None,
        "period": b.period, "amount_minor": b.amount_minor, "start_date": _iso(b.start_date), "end_date": _iso(b.end_date),
        "include_subcategories": b.include_subcategories, "active": b.active, **status,
    }


def goal(g: Goal, status: dict) -> dict:
    return {
        "id": g.id, "name": g.name, "goal_type": g.goal_type, "target_minor": g.target_minor, "currency": g.currency,
        "target_date": _iso(g.target_date), "start_date": _iso(g.start_date), "linked_account_id": g.linked_account_id,
        "color": g.color, "status": g.status, "completed_at": _iso(g.completed_at), **status,
    }


def contribution(c: GoalContribution) -> dict:
    return {"id": c.id, "goal_id": c.goal_id, "amount_minor": c.amount_minor, "date": c.date.isoformat(), "note": c.note}


def bill(b: Bill, status: str, monthly_equivalent: int) -> dict:
    return {
        "id": b.id, "name": b.name, "provider": b.provider, "amount_minor": b.amount_minor, "currency": b.currency,
        "frequency": b.frequency, "next_due_date": b.next_due_date.isoformat(), "autopay": b.autopay, "account_id": b.account_id,
        "category_id": b.category_id, "notes": b.notes, "active": b.active, "status": status, "monthly_equivalent_minor": monthly_equivalent,
        "history": [{"id": p.id, "due_date": p.due_date.isoformat(), "status": p.status, "amount_minor": p.amount_minor, "transaction_id": p.transaction_id, "recorded_at": _iso(p.recorded_at)} for p in sorted(b.payments, key=lambda p: p.recorded_at, reverse=True)[:12]],
    }


def subscription(s: Subscription, equivalents: dict) -> dict:
    return {
        "id": s.id, "name": s.name, "merchant_id": s.merchant_id, "merchant": s.merchant.name if s.merchant else None,
        "amount_minor": s.amount_minor, "currency": s.currency, "frequency": s.frequency, "next_payment_date": _iso(s.next_payment_date),
        "account_id": s.account_id, "category_id": s.category_id, "active": s.active, "started_on": _iso(s.started_on),
        "cancelled_on": _iso(s.cancelled_on), "previous_amount_minor": s.previous_amount_minor, "price_changed_at": _iso(s.price_changed_at),
        "detected": s.detected, "notes": s.notes, "monthly_equivalent_minor": equivalents["monthly_equivalent"], "annual_equivalent_minor": equivalents["annual_equivalent"],
    }


def recurring(r: RecurringTransaction) -> dict:
    return {
        "id": r.id, "name": r.name, "type": r.type, "account_id": r.account_id, "transfer_account_id": r.transfer_account_id,
        "amount_minor": r.amount_minor, "currency": r.currency, "category_id": r.category_id, "merchant_name": r.merchant_name,
        "payment_method": r.payment_method, "frequency": r.frequency, "next_date": r.next_date.isoformat(), "end_date": _iso(r.end_date),
        "auto_create": r.auto_create, "active": r.active, "last_generated_date": _iso(r.last_generated_date),
    }


def rule(r: CategorizationRule) -> dict:
    return {
        "id": r.id, "name": r.name, "priority": r.priority, "field": r.field, "match_type": r.match_type, "pattern": r.pattern,
        "case_sensitive": r.case_sensitive, "amount_min_minor": r.amount_min_minor, "amount_max_minor": r.amount_max_minor,
        "account_id": r.account_id, "transaction_type": r.transaction_type, "set_category_id": r.set_category_id,
        "set_merchant_name": r.set_merchant_name, "add_tag_ids": r.add_tag_ids, "mark_reviewed": r.mark_reviewed,
        "enabled": r.enabled, "apply_count": r.apply_count,
    }


def alert_rule(r: AlertRule) -> dict:
    return {
        "id": r.id, "name": r.name, "metric": r.metric, "params": r.params, "operator": r.operator,
        "threshold": str(r.threshold) if r.threshold is not None else None, "channels": r.channels,
        "cooldown_policy": r.cooldown_policy, "cooldown_minutes": r.cooldown_minutes, "enabled": r.enabled,
        "last_triggered_at": _iso(r.last_triggered_at), "last_evaluated_at": _iso(r.last_evaluated_at),
    }


def delivery(d: NotificationDelivery) -> dict:
    return {"id": d.id, "channel": d.channel, "provider": d.provider, "status": d.status, "destination": d.destination, "error": d.error, "attempts": d.attempts, "sent_at": _iso(d.sent_at)}


def alert_event(e: AlertEvent) -> dict:
    return {
        "id": e.id, "rule_id": e.rule_id, "metric": e.metric, "category": e.category, "title": e.title, "message": e.message,
        "severity": e.severity, "value": e.value, "threshold": e.threshold, "triggered_at": _iso(e.triggered_at),
        "link": (e.context or {}).get("link", ""), "deliveries": [delivery(d) for d in e.deliveries],
    }


def notification(n: Notification) -> dict:
    return {"id": n.id, "category": n.category, "severity": n.severity, "title": n.title, "message": n.message, "link": n.link, "read": n.read_at is not None, "created_at": _iso(n.created_at)}


def bank_connection(c: BankConnection, accounts: list[Account]) -> dict:
    return {
        "id": c.id, "provider": c.provider, "institution_id": c.institution_id, "institution_name": c.institution_name, "status": c.status,
        "auto_sync": c.auto_sync, "last_synced_at": _iso(c.last_synced_at), "last_error": c.last_error,
        "consent_expires_at": _iso(c.consent_expires_at), "created_at": _iso(c.created_at),
        "accounts": [{"id": a.id, "name": a.name, "type": a.type, "account_number_mask": a.account_number_mask, "last_synced_at": _iso(a.last_synced_at)} for a in accounts],
    }


def sync_log(s: SyncLog) -> dict:
    return {
        "id": s.id, "connection_id": s.connection_id, "trigger": s.trigger, "status": s.status, "fetched": s.fetched_count,
        "imported": s.imported_count, "updated": s.updated_count, "duplicates": s.duplicate_count, "errors": s.error_count,
        "message": s.message, "started_at": _iso(s.started_at), "finished_at": _iso(s.finished_at),
    }


def import_job(j: ImportJob, preview_rows: int = 25) -> dict:
    rows = j.normalized or []
    return {
        "id": j.id, "filename": j.filename, "file_format": j.file_format, "status": j.status, "account_id": j.account_id,
        "bank_detected": j.bank_detected, "headers": j.headers, "mapping": j.mapping,
        "sample_rows": (j.raw_rows or [])[:preview_rows], "total_rows": len(j.raw_rows or rows),
        "rows": [{k: v for k, v in r.items() if k != "raw"} for r in rows],
        "counts": {
            "ok": sum(1 for r in rows if r.get("status") == "ok"), "duplicates": sum(1 for r in rows if r.get("status") == "duplicate"),
            "errors": sum(1 for r in rows if r.get("status") == "error"), "imported": j.imported_count, "skipped": j.skipped_count,
        },
        "error": j.error, "created_at": _iso(j.created_at), "completed_at": _iso(j.completed_at),
    }


def exchange_rate(r: ExchangeRate) -> dict:
    return {"id": r.id, "base_currency": r.base_currency, "quote_currency": r.quote_currency, "rate": str(r.rate), "as_of": r.as_of.isoformat(), "source": r.source}
