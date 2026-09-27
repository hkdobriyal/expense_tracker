"""Single-use tokens for password reset and email verification."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import AuthToken, User
from ..security import hash_token, new_token
from .email import EmailResult, send_email

TTL = {"reset": timedelta(minutes=30), "verify": timedelta(days=3)}


def issue(db: Session, user: User, purpose: str) -> str:
    # Only the newest token of a kind stays valid.
    db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None)).values(used_at=utcnow()))
    raw = new_token()
    db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=hash_token(raw), expires_at=utcnow() + TTL[purpose]))
    db.flush()
    return raw


def consume(db: Session, raw: str, purpose: str) -> User | None:
    token = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(raw or ""), AuthToken.purpose == purpose))
    if token is None or token.used_at is not None or token.expires_at <= utcnow():
        return None
    token.used_at = utcnow()
    return db.get(User, token.user_id)


def send_reset_email(email: str, name: str, raw: str) -> EmailResult:
    s = get_settings()
    link = f"{s.app_url}/reset-password?token={raw}"
    return send_email(
        email, "Reset your password",
        f"Hi {name or 'there'},\n\nSomeone (hopefully you) asked to reset the password for your {s.app_name} account. "
        f"The link below works once and expires in 30 minutes.\n\nIf you didn't ask for this, ignore this email – your password stays the same.",
        link, "Choose a new password",
    )


def send_verification_email(email: str, name: str, raw: str) -> EmailResult:
    s = get_settings()
    link = f"{s.app_url}/verify-email?token={raw}"
    return send_email(
        email, "Confirm your email",
        f"Hi {name or 'there'},\n\nWelcome to {s.app_name}! Confirm this address so we can send you budget alerts, bill reminders and password resets.",
        link, "Confirm email",
    )
