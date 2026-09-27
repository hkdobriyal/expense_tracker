"""Web Push subscriptions, test email/push, and a live event stream (Server-Sent Events)."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..config import get_settings
from ..db import SessionLocal, get_db
from ..deps import CurrentUser, get_current_user
from ..models import Notification, PushSubscription, UserSettings
from ..security import rate_limiter
from ..services import push
from ..services.email import send_email

router = APIRouter(prefix="/api", tags=["realtime"])


class PushKeys(BaseModel):
    p256dh: str = Field(max_length=255)
    auth: str = Field(max_length=255)


class PushSubscribeIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: PushKeys


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)


@router.get("/push/public-key")
def push_public_key():
    return {"public_key": push.public_key()}


@router.post("/push/subscribe", status_code=201)
def push_subscribe(body: PushSubscribeIn, request: Request, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    if not body.endpoint.startswith("https://"):
        raise HTTPException(422, "Push endpoints must be https URLs from the browser's push service")
    push.subscribe(db, current.id, body.endpoint, body.keys.p256dh, body.keys.auth, request.headers.get("user-agent", ""))
    settings = db.get(UserSettings, current.id)
    settings.channel_push = True
    db.commit()
    return {"ok": True, "devices": push.subscription_count(db, current.id)}


@router.delete("/push/subscribe")
def push_unsubscribe(body: PushUnsubscribeIn, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == current.id))
    if sub is not None:
        db.delete(sub)
    db.flush()
    if push.subscription_count(db, current.id) == 0:
        db.get(UserSettings, current.id).channel_push = False
    db.commit()
    return {"ok": True}


@router.get("/push/devices")
def push_devices(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == current.id)).all()
    return [{"id": s.id, "user_agent": s.user_agent, "created_at": s.created_at.isoformat(), "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None} for s in subs]


@router.post("/push/test")
def push_test(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    if not rate_limiter.hit(f"pushtest:{current.id}", 10, 300):
        raise HTTPException(429, "Too many test pushes")
    delivered, errors = push.send_to_user(db, current.id, f"{get_settings().app_name} test", "Push notifications are working on this device.", "/settings")
    db.commit()
    if not delivered:
        raise HTTPException(422, errors[0] if errors else "No push was delivered")
    return {"delivered": delivered, "warnings": errors}


@router.post("/notifications/test-email")
def test_email(current: CurrentUser = Depends(get_current_user)):
    if not rate_limiter.hit(f"emailtest:{current.id}", 5, 300):
        raise HTTPException(429, "Too many test emails – wait a few minutes")
    to = current.settings.contact_email or current.user.email
    result = send_email(to, "Test email", f"This test was sent from {get_settings().app_name}. If you can read it, email alerts will reach you too.")
    return {"status": result.status, "provider": result.provider, "error": result.error, "to": to}


# --- Live events ---------------------------------------------------------------------------------

def _snapshot(user_id: int) -> tuple[int, int, dict | None]:
    db = SessionLocal()
    try:
        latest = db.scalar(select(Notification).where(Notification.user_id == user_id).order_by(Notification.id.desc()).limit(1))
        unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))) or 0
        payload = {"id": latest.id, "title": latest.title, "message": latest.message, "severity": latest.severity, "link": latest.link} if latest else None
        return (latest.id if latest else 0), int(unread), payload
    finally:
        db.close()


@router.get("/events/stream")
async def event_stream(request: Request, once: bool = False, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    """Pushes `notification` events (new alert) and `unread` counts as they change."""
    user_id = current.id
    db.close()  # a long-lived stream must not keep the request's DB transaction (and SQLite lock) open

    async def events():
        last_id, last_unread, _ = await run_in_threadpool(_snapshot, user_id)
        yield f"event: unread\ndata: {json.dumps({'unread': last_unread})}\n\n"
        if once:
            return
        ticks = 0
        while not await request.is_disconnected():
            await asyncio.sleep(3)
            ticks += 1
            latest_id, unread, payload = await run_in_threadpool(_snapshot, user_id)
            if latest_id > last_id and payload:
                yield f"event: notification\ndata: {json.dumps(payload)}\n\n"
            if latest_id != last_id or unread != last_unread:
                yield f"event: unread\ndata: {json.dumps({'unread': unread})}\n\n"
            last_id, last_unread = latest_id, unread
            if ticks % 5 == 0:
                yield ": keep-alive\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
