"""Registration, login, password reset, email verification, logout and demo-mode sessions."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..config import get_settings
from ..db import get_db, utcnow
from ..deps import SESSION_COOKIE, CurrentUser, client_ip, get_current_user
from ..models import User, UserSession, UserSettings
from ..money import SUPPORTED_CURRENCIES
from ..schemas import ChangePasswordIn, EmailIn, LoginIn, RegisterIn, ResetPasswordIn, TokenIn
from ..security import hash_password, hash_token, new_token, rate_limiter, validate_password_strength, verify_password
from ..services import account_tokens, alerts, audit
from ..services.catalog import seed_default_categories

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _open_session(db: Session, request: Request, response: Response, user: User, remember: bool = True) -> UserSession:
    s = get_settings()
    token = new_token()
    lifetime = timedelta(days=s.session_days) if remember else timedelta(hours=12)
    session = UserSession(
        user_id=user.id, token_hash=hash_token(token), csrf_token=new_token(),
        expires_at=utcnow() + lifetime,
        user_agent=(request.headers.get("user-agent") or "")[:300], ip_address=client_ip(request),
    )
    db.add(session)
    user.last_login_at = utcnow()
    # "Remember me" off -> a browser-session cookie that disappears when the browser closes.
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="lax",
        max_age=int(lifetime.total_seconds()) if remember else None, path="/",
    )
    return session


def _session_payload(user: User, session: UserSession) -> dict:
    return {"user": ser.user(user), "csrf_token": session.csrf_token, "settings": ser.settings(user.settings)}


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    """Tells the login screen whether to show 'create account' (first run) or 'sign in'."""
    real_users = db.scalar(select(func.count()).select_from(User).where(User.is_demo.is_(False))) or 0
    s = get_settings()
    return {
        "has_account": real_users > 0, "registration_open": real_users == 0 or s.allow_registration,
        "app_name": s.app_name, "email_configured": s.email_configured,
    }


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, background: BackgroundTasks, db: Session = Depends(get_db)):
    real_users = db.scalar(select(func.count()).select_from(User).where(User.is_demo.is_(False))) or 0
    if real_users > 0 and not get_settings().allow_registration:
        raise HTTPException(403, "Registration is closed on this installation (ALLOW_REGISTRATION=false).")
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
    raw = account_tokens.issue(db, user, "verify")
    audit.record(db, user.id, "user.registered", "user", user.id, ip=client_ip(request))
    db.commit()
    background.add_task(account_tokens.send_verification_email, user.email, user.display_name, raw)
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
    session = _open_session(db, request, response, user, remember=body.remember)
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


@router.post("/forgot-password")
def forgot_password(body: EmailIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Always answers the same way so the endpoint can't be used to discover registered emails."""
    email = body.email.strip().lower()
    if not rate_limiter.hit(f"forgot:{client_ip(request)}", 5, 900) or not rate_limiter.hit(f"forgot:{email}", 3, 900):
        raise HTTPException(429, "Too many reset requests. Try again in 15 minutes.")
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_demo.is_(False)))
    if user is not None:
        raw = account_tokens.issue(db, user, "reset")
        audit.record(db, user.id, "auth.reset_requested", "user", user.id, ip=client_ip(request))
        db.commit()
        background.add_task(account_tokens.send_reset_email, user.email, user.display_name, raw)
    return {"ok": True, "message": "If an account exists for that email, a reset link is on its way.",
            "email_configured": get_settings().email_configured}


@router.post("/reset-password")
def reset_password(body: ResetPasswordIn, request: Request, db: Session = Depends(get_db)):
    if not rate_limiter.hit(f"reset:{client_ip(request)}", 10, 900):
        raise HTTPException(429, "Too many attempts. Try again later.")
    problem = validate_password_strength(body.password)
    if problem:
        raise HTTPException(422, problem)
    user = account_tokens.consume(db, body.token, "reset")
    if user is None:
        raise HTTPException(400, "This reset link is invalid or has expired. Request a new one.")
    user.password_hash = hash_password(body.password)
    user.email_verified_at = user.email_verified_at or utcnow()  # they proved access to the inbox
    for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all():
        db.delete(s)  # sign out everywhere
    audit.record(db, user.id, "auth.password_reset", "user", user.id, ip=client_ip(request))
    db.commit()
    return {"ok": True}


@router.post("/verify-email")
def verify_email(body: TokenIn, db: Session = Depends(get_db)):
    user = account_tokens.consume(db, body.token, "verify")
    if user is None:
        raise HTTPException(400, "This confirmation link is invalid or has expired.")
    user.email_verified_at = utcnow()
    audit.record(db, user.id, "auth.email_verified", "user", user.id)
    db.commit()
    return {"ok": True, "email": user.email}


@router.post("/resend-verification")
def resend_verification(background: BackgroundTasks, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(User, current.id)
    if user.email_verified_at:
        return {"ok": True, "already_verified": True}
    if not rate_limiter.hit(f"verify:{user.id}", 3, 900):
        raise HTTPException(429, "Please wait before requesting another email.")
    raw = account_tokens.issue(db, user, "verify")
    db.commit()
    background.add_task(account_tokens.send_verification_email, user.email, user.display_name, raw)
    return {"ok": True, "email_configured": get_settings().email_configured}


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
