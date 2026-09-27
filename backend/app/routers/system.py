"""Health, backup/restore, audit log and account deletion."""

from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db, utcnow
from ..deps import SESSION_COOKIE, CurrentUser, client_ip, get_current_user
from ..models import AuditLog, Job, SystemState, User
from ..security import verify_password
from ..services import audit, backup
from .common import ctx_of

router = APIRouter(prefix="/api", tags=["system"])


def worker_status(db: Session) -> dict:
    beat = db.get(SystemState, "worker_heartbeat")
    if beat is None:
        return {"running": False, "last_heartbeat": None}
    age = (utcnow() - beat.updated_at).total_seconds()
    return {"running": age < 180, "last_heartbeat": beat.updated_at.isoformat(), "seconds_ago": int(age)}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001
        database = "unavailable"
    s = get_settings()
    queued = db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued")) if database == "ok" else None
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": {"status": database, "engine": "sqlite" if s.is_sqlite else "postgresql"},
        "worker": worker_status(db) if database == "ok" else None,
        "jobs_queued": queued,
        "email": "smtp" if s.email_configured else "console (not sending)",
        "sms": f"{s.sms_provider} (no messages sent)" if s.sms_provider == "mock" else s.sms_provider,
        "whatsapp": f"{s.whatsapp_provider} (no messages sent)" if s.whatsapp_provider == "mock" else s.whatsapp_provider,
    }


@router.get("/backup")
def export_backup(request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    data = backup.export(db, ctx_of(current))
    audit.record(db, current.id, "data.exported", "backup", None, {"transactions": len(data["transactions"])}, client_ip(request))
    db.commit()
    filename = f"hisaab-backup-{utcnow():%Y%m%d-%H%M}.json"
    return Response(json.dumps(data, indent=2, ensure_ascii=False), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/backup/restore")
async def restore_backup(request: Request, file: UploadFile = File(...), confirm: bool = False, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if not confirm:
        raise HTTPException(400, "Restoring replaces all data in this workspace. Repeat with confirm=true.")
    content = await file.read(50 * 1024 * 1024 + 1)
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "Backup files are limited to 50 MB")
    try:
        payload = json.loads(content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, "That file is not valid JSON") from exc
    try:
        result = backup.restore(db, ctx_of(current), payload)
    except (backup.RestoreError, ValueError, KeyError) as exc:
        db.rollback()
        raise HTTPException(422, f"Could not restore: {exc}") from exc
    audit.record(db, current.id, "data.restored", "backup", None, result, client_ip(request))
    db.commit()
    return result


@router.get("/audit-log")
def audit_log(limit: int = 100, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == current.id).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()
    return [{"id": r.id, "action": r.action, "entity": r.entity, "entity_id": r.entity_id, "details": r.details, "ip_address": r.ip_address, "created_at": r.created_at.isoformat()} for r in rows]


@router.get("/jobs")
def recent_jobs(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    since = utcnow() - timedelta(days=3)
    rows = db.scalars(select(Job).where(Job.created_at >= since).order_by(Job.created_at.desc()).limit(50)).all()
    return {"worker": worker_status(db), "jobs": [{"id": j.id, "type": j.type, "status": j.status, "attempts": j.attempts, "last_error": j.last_error, "created_at": j.created_at.isoformat()} for j in rows]}


@router.post("/me/delete")
def delete_me(body: dict, request: Request, response: Response, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Permanently delete the signed-in user and all of their data."""
    user = db.get(User, current.id)
    if not current.user.is_demo and not verify_password(str(body.get("password") or ""), user.password_hash):
        raise HTTPException(400, "Password is incorrect")
    audit.record(db, None, "account.deleted", "user", user.id, {"email_domain": user.email.split("@")[-1]}, client_ip(request))
    db.delete(user)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"deleted": True}
