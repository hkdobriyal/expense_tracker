"""Bank connections & sync, statement imports, and bank-SMS ingestion."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..config import get_settings
from ..db import get_db
from ..deps import CurrentUser, client_ip, get_current_user, get_owned
from ..models import Account, BankConnection, ImportJob, SyncLog, UserSettings
from ..schemas import BankConnectIn, BankLinkIn, ImportCommitIn, ImportMappingIn, SmsCommitIn, SmsIn
from ..security import hash_token, rate_limiter
from ..services import alerts, audit, banking, imports
from ..services.context import UserContext
from ..services.importers import ImportParseError
from ..services.sms_parser import parse_bank_sms
from ..services.transactions import TransactionInput, build_transaction, find_duplicate, fingerprint, signed_for_fingerprint
from ..money import to_minor
from .common import ctx_of

router = APIRouter(prefix="/api", tags=["integrations"])


# --- Bank connections ---------------------------------------------------------------------------

def _conn_out(db: Session, conn: BankConnection) -> dict:
    accounts = db.scalars(select(Account).where(Account.bank_connection_id == conn.id)).all()
    return ser.bank_connection(conn, accounts)


@router.get("/banks/providers")
def providers(current: CurrentUser = Depends(get_current_user)):
    return banking.provider_catalog(current.user)


@router.get("/banks/connections")
def connections(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(BankConnection).where(BankConnection.user_id == current.id).order_by(BankConnection.created_at.desc())).all()
    return [_conn_out(db, c) for c in rows]


@router.post("/banks/connections", status_code=201)
def connect(body: BankConnectIn, request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        conn, step = banking.start_connection(db, ctx_of(current), current.user, body.provider, body.institution_id, body.params)
    except banking.ProviderError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.record(db, current.id, "bank.connection_started", "bank_connection", conn.id, {"provider": conn.provider}, client_ip(request))
    db.commit()
    return {
        "connection": _conn_out(db, conn), "status": step.status, "message": step.message, "next_action": step.next_action,
        "redirect_url": step.redirect_url,
        "accounts": [{"external_id": a.external_id, "name": a.name, "type": a.type, "currency": a.currency, "mask": a.mask} for a in step.accounts],
    }


@router.post("/banks/connections/{conn_id}/accounts")
def link_accounts(conn_id: int, body: BankLinkIn, request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = get_owned(db, BankConnection, conn_id, current, "Connection")
    ctx = ctx_of(current)
    try:
        banking.link_accounts(db, ctx, conn, body.account_external_ids)
    except banking.ProviderError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.record(db, current.id, "bank.connected", "bank_connection", conn.id, {"accounts": len(body.account_external_ids)}, client_ip(request))
    log = banking.sync_connection(db, ctx, current.user, conn, "manual")
    db.commit()
    return {"connection": _conn_out(db, conn), "sync": ser.sync_log(log)}


@router.post("/banks/connections/{conn_id}/sync")
def sync_now(conn_id: int, request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = get_owned(db, BankConnection, conn_id, current, "Connection")
    if not rate_limiter.hit(f"sync:{conn.id}", 6, 60):
        raise HTTPException(429, "Sync was requested too often. Wait a minute.")
    log = banking.sync_connection(db, ctx_of(current), current.user, conn, "manual")
    audit.record(db, current.id, "bank.synced", "bank_connection", conn.id, {"status": log.status, "imported": log.imported_count}, client_ip(request))
    db.commit()
    return {"connection": _conn_out(db, conn), "sync": ser.sync_log(log)}


@router.patch("/banks/connections/{conn_id}")
def update_connection(conn_id: int, body: dict, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = get_owned(db, BankConnection, conn_id, current, "Connection")
    if "auto_sync" in body:
        conn.auto_sync = bool(body["auto_sync"])
    db.commit()
    return _conn_out(db, conn)


@router.delete("/banks/connections/{conn_id}")
def disconnect(conn_id: int, request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = get_owned(db, BankConnection, conn_id, current, "Connection")
    banking.disconnect(db, conn)
    audit.record(db, current.id, "bank.disconnected", "bank_connection", conn.id, {"provider": conn.provider}, client_ip(request))
    db.commit()
    return _conn_out(db, conn)


@router.get("/banks/sync-logs")
def sync_logs(connection_id: Optional[int] = None, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(SyncLog).where(SyncLog.user_id == current.id)
    if connection_id:
        stmt = stmt.where(SyncLog.connection_id == connection_id)
    return [ser.sync_log(s) for s in db.scalars(stmt.order_by(SyncLog.started_at.desc()).limit(50)).all()]


# --- Statement imports --------------------------------------------------------------------------

@router.post("/imports", status_code=201)
async def upload_statement(
    file: UploadFile = File(...), password: Optional[str] = Form(None), account_id: Optional[int] = Form(None),
    current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    limit = get_settings().max_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"Statements are limited to {get_settings().max_upload_mb} MB")
    if not content:
        raise HTTPException(422, "The file is empty")
    if account_id is not None:
        get_owned(db, Account, account_id, current, "Account")
    try:
        job = imports.create_job(db, ctx_of(current), file.filename or "statement", content, password or None, account_id)
    except ImportParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return ser.import_job(job)


@router.get("/imports")
def list_imports(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = db.scalars(select(ImportJob).where(ImportJob.user_id == current.id).order_by(ImportJob.created_at.desc()).limit(50)).all()
    return [{"id": j.id, "filename": j.filename, "file_format": j.file_format, "status": j.status, "bank_detected": j.bank_detected, "imported": j.imported_count, "duplicates": j.duplicate_count, "errors": j.error_count, "created_at": j.created_at.isoformat(), "completed_at": j.completed_at.isoformat() if j.completed_at else None} for j in jobs]


@router.get("/imports/{job_id}")
def get_import(job_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ser.import_job(get_owned(db, ImportJob, job_id, current, "Import"))


@router.post("/imports/{job_id}/validate")
def validate_import(job_id: int, body: ImportMappingIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    job = get_owned(db, ImportJob, job_id, current, "Import")
    if job.status not in ("preview", "validated"):
        raise HTTPException(409, "This import has already been completed")
    imports.validate(db, ctx_of(current), job, body.mapping, body.account_id)
    db.commit()
    return ser.import_job(job)


@router.post("/imports/{job_id}/commit")
def commit_import(job_id: int, body: ImportCommitIn, request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    job = get_owned(db, ImportJob, job_id, current, "Import")
    result = imports.commit(db, ctx_of(current), job, set(body.include_duplicate_rows), body.type_overrides)
    audit.record(db, current.id, "import.completed", "import_job", job.id, {**result, "format": job.file_format}, client_ip(request))
    db.commit()
    return {**result, "job": ser.import_job(job)}


@router.post("/imports/{job_id}/undo")
def undo_import(job_id: int, request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    job = get_owned(db, ImportJob, job_id, current, "Import")
    removed = imports.undo(db, ctx_of(current), job)
    audit.record(db, current.id, "import.undone", "import_job", job.id, {"removed": removed}, client_ip(request))
    db.commit()
    return {"removed": removed}


# --- SMS ingestion ------------------------------------------------------------------------------

def _sms_to_input(parsed: dict, account_id: int, on: date, txn_type: str | None, category_id: int | None, raw: str) -> TransactionInput:
    return TransactionInput(
        type=txn_type or parsed["kind"], account_id=account_id, date=on, amount=parsed["amount"],
        description=parsed["title"], merchant=parsed.get("merchant"), category_id=category_id,
        notes=parsed.get("notes") or "", payment_method=parsed.get("payment_method") or "", source="sms",
        raw_description=raw[:2000], external_id=f"sms:{parsed['ref_id']}" if parsed.get("ref_id") else None,
    )


@router.post("/sms/parse")
def sms_parse(body: SmsIn, current: CurrentUser = Depends(get_current_user)):
    parsed = parse_bank_sms(body.text)
    if not parsed:
        raise HTTPException(422, "No transaction found. The text needs an amount (e.g. 'INR 450') and debit/credit wording.")
    return {"type": parsed["kind"], "amount": str(parsed["amount"]), "description": parsed["title"], "merchant": parsed.get("merchant"),
            "payment_method": parsed.get("payment_method"), "institution": parsed.get("institution"), "account_ref": parsed.get("account_ref"), "ref_id": parsed.get("ref_id")}


@router.post("/sms/commit", status_code=201)
def sms_commit(body: SmsCommitIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    parsed = parse_bank_sms(body.text)
    if not parsed:
        raise HTTPException(422, "No transaction found in this text")
    ctx = ctx_of(current)
    data = _sms_to_input(parsed, body.account_id, body.date or ctx.today, body.type, body.category_id, body.text)
    dup = find_duplicate(db, current.id, "", data.external_id)
    if dup is not None:
        raise HTTPException(409, f"Already recorded as transaction #{dup.id}")
    txn = build_transaction(db, current.id, current.base_currency, data)
    txn.reviewed = True
    alerts.after_ledger_change(db, ctx, [txn])
    db.commit()
    return ser.transaction(txn)


@router.post("/sms/webhook", status_code=201)
def sms_webhook(body: SmsIn, request: Request, db: Session = Depends(get_db)):
    """For SMS-forwarder apps. Authenticated with the token from Settings → Integrations
    (``Authorization: Bearer lsms_…``). Transactions land in the default account for review."""
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token.startswith("lsms_") or not rate_limiter.hit(f"smshook:{client_ip(request)}", 60, 60):
        raise HTTPException(401, "Invalid token")
    settings = db.scalar(select(UserSettings).where(UserSettings.sms_webhook_token_hash == hash_token(token)))
    if settings is None:
        raise HTTPException(401, "Invalid token")
    parsed = parse_bank_sms(body.text)
    if not parsed:
        raise HTTPException(422, "Text could not be parsed as a transaction")
    user = settings.user
    ctx = UserContext.for_user(db, user)
    account_id = body.account_id or settings.default_account_id
    account = db.get(Account, account_id) if account_id else None
    if account is None or account.user_id != user.id:
        raise HTTPException(422, "Set a default account in Settings before using the SMS webhook")
    data = _sms_to_input(parsed, account.id, ctx.today, None, None, body.text)
    fp = fingerprint(account.id, ctx.today, signed_for_fingerprint(data.type, to_minor(data.amount, account.currency)), data.raw_description)
    if find_duplicate(db, user.id, fp, data.external_id) is not None:
        return {"created": False, "reason": "duplicate"}
    txn = build_transaction(db, user.id, ctx.base_currency, data)
    txn.reviewed = False
    alerts.after_ledger_change(db, ctx, [txn])
    db.commit()
    return {"created": True, "transaction_id": txn.id}
