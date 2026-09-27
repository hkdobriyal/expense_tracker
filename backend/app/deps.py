"""FastAPI dependencies: current user, CSRF enforcement, ownership helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TypeVar

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, utcnow
from .models import User, UserSession, UserSettings
from .security import hash_token

SESSION_COOKIE = "hisaab_session"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

T = TypeVar("T")


@dataclass
class CurrentUser:
    user: User
    session: UserSession
    settings: UserSettings

    @property
    def id(self) -> int:
        return self.user.id

    @property
    def base_currency(self) -> str:
        return self.settings.base_currency


def _load_session(request: Request, db: Session) -> UserSession | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if session is None or session.expires_at <= utcnow():
        return None
    return session


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    session = _load_session(request, db)
    if session is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    if request.method not in SAFE_METHODS:
        header = request.headers.get(CSRF_HEADER, "")
        if not header or header != session.csrf_token:
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token")
    now = utcnow()
    if now - session.last_seen_at > timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    user = session.user
    settings = user.settings
    if settings is None:
        settings = UserSettings(user_id=user.id)
        db.add(settings)
        db.commit()
    request.state.user_id = user.id
    return CurrentUser(user=user, session=session, settings=settings)


def get_owned(db: Session, model: type[T], record_id: int, user: CurrentUser, label: str | None = None) -> T:
    """Fetch a row by id, returning 404 (not 403) when it belongs to someone else."""
    obj = db.get(model, record_id)
    if obj is None or getattr(obj, "user_id", None) != user.id:
        raise HTTPException(status_code=404, detail=f"{label or model.__name__} not found")
    return obj


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""
