"""Registration, login, logout and demo-mode sessions."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..config import get_settings
from ..db import get_db, utcnow
from ..deps import SESSION_COOKIE, CurrentUser, client_ip, get_current_user
from ..models import User, UserSession, UserSettings
from ..money import SUPPORTED_CURRENCIES
from ..schemas import ChangePasswordIn, LoginIn, RegisterIn
from ..security import hash_password, hash_token, new_token, rate_limiter, validate_password_strength, verify_password
from ..services import alerts, audit
from ..services.catalog import seed_default_categories

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _open_session(db: Session, request: Request, response: Response, user: User) -> UserSession:
    s = get_settings()
    token = new_token()
    session = UserSession(
        user_id=user.id, token_hash=hash_token(token), csrf_token=new_token(),
        expires_at=utcnow() + timedelta(days=s.session_days),
        user_agent=(request.headers.get("user-agent") or "")[:300], ip_address=client_ip(request),
    )
    db.add(session)
    user.last_login_at = utcnow()
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="lax",
        max_age=s.session_days * 86400, path="/",
    )
    return session


def _session_payload(user: User, session: UserSession) -> dict:
    return {"user": ser.user(user), "csrf_token": session.csrf_token, "settings": ser.settings(user.settings)}


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    """Tells the login screen whether to show 'create account' (first run) or 'sign in'."""
    real_users = db.scalar(select(func.count()).select_from(User).where(User.is_demo.is_(False))) or 0
    return {"has_account": real_users > 0, "registration_open": real_users == 0 or get_settings().allow_registration}


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    real_users = db.scalar(select(func.count()).select_from(User).where(User.is_demo.is_(False))) or 0
    if real_users > 0 and not get_settings().allow_registration:
        raise HTTPException(403, "Registration is closed. This is a single-user installation; set ALLOW_REGISTRATION=true to add users.")
    if not rate_limiter.hit(f"register:{client_ip(request)}", 5, 3600):
        raise HTTPException(429, "Too many attempts. Try again later.")
    if db.scalar(select(User).where(func.lower(User.email) == body.email)):
        raise HTTPException(409, "An account with this email already exists")
    problem = validate_password_strength(body.password)
    if problem:
        raise HTTPException(422, problem)
    currency = body.base_currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(422, "Unsupported base currency")
    user = User(email=body.email, password_hash=hash_password(body.password), display_name=body.display_name or body.email.split("@")[0])
    db.add(user)
    db.flush()
    user.settings = UserSettings(user_id=user.id, base_currency=currency, timezone=body.timezone, contact_email=body.email)
    seed_default_categories(db, user.id)
    alerts.create_default_rules(db, user.id)
    session = _open_session(db, request, response, user)
    audit.record(db, user.id, "user.registered", "user", user.id, ip=client_ip(request))
    db.commit()
    return _session_payload(user, session)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    ip = client_ip(request)
    if not rate_limiter.hit(f"login:{ip}", 10, 300) or not rate_limiter.hit(f"login:{email}", 5, 300):
        raise HTTPException(429, "Too many sign-in attempts. Wait a few minutes and try again.")
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_demo.is_(False)))
    if user is None or not verify_password(body.password, user.password_hash):
        audit.record(db, user.id if user else None, "auth.login_failed", "user", user.id if user else None, {"email": email}, ip)
        db.commit()
        raise HTTPException(401, "Incorrect email or password")
    session = _open_session(db, request, response, user)
    audit.record(db, user.id, "auth.login", "user", user.id, ip=ip)
    db.commit()
    return _session_payload(user, session)


@router.post("/logout")
def logout(response: Response, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.get(UserSession, current.session.id)
    if session is not None:
        db.delete(session)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/session")
def current_session(request: Request, db: Session = Depends(get_db)):
    """Like /me, but answers 200 when signed out so the SPA can bootstrap without an error."""
    from ..deps import _load_session

    session = _load_session(request, db)
    if session is None:
        return {"authenticated": False}
    return {"authenticated": True, **_session_payload(session.user, session)}


@router.get("/me")
def me(current: CurrentUser = Depends(get_current_user)):
    return _session_payload(current.user, current.session)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(User, current.user.id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    problem = validate_password_strength(body.new_password)
    if problem:
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.new_password)
    # Sign out every other session.
    for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.id != current.session.id)).all():
        db.delete(s)
    audit.record(db, user.id, "auth.password_changed", "user", user.id, ip=client_ip(request))
    db.commit()
    return {"ok": True}


@router.get("/sessions")
def sessions(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(UserSession).where(UserSession.user_id == current.id, UserSession.expires_at > utcnow()).order_by(UserSession.last_seen_at.desc())).all()
    return [{"id": s.id, "current": s.id == current.session.id, "user_agent": s.user_agent, "ip_address": s.ip_address, "created_at": s.created_at.isoformat(), "last_seen_at": s.last_seen_at.isoformat()} for s in rows]


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(UserSession, session_id)
    if s is None or s.user_id != current.id:
        raise HTTPException(404, "Session not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.post("/demo")
def start_demo(request: Request, response: Response, db: Session = Depends(get_db)):
    """Reset and open the isolated demo workspace (sample data, sandbox bank)."""
    from ..services.demo import reset_demo_user

    if not rate_limiter.hit(f"demo:{client_ip(request)}", 10, 3600):
        raise HTTPException(429, "Too many demo resets. Try again later.")
    user = reset_demo_user(db)
    session = _open_session(db, request, response, user)
    db.commit()
    return _session_payload(user, session)
