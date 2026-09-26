"""Audit trail for important actions. Never pass secrets in ``details``."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditLog

_FORBIDDEN_KEYS = {"password", "token", "secret", "client_secret", "otp", "credentials"}


def record(db: Session, user_id: int | None, action: str, entity: str = "", entity_id=None, details: dict | None = None, ip: str = "") -> None:
    safe = {k: v for k, v in (details or {}).items() if k.lower() not in _FORBIDDEN_KEYS}
    db.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=str(entity_id) if entity_id is not None else None, details=safe, ip_address=ip))
