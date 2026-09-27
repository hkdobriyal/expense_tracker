"""Statement import workflow: upload → preview → map columns → validate → commit."""

from __future__ import annotations

from collections import Counter
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Account, ImportJob, Transaction
from ..money import to_minor
from . import alerts
from .context import UserContext
from .importers import ParsedFile, normalize_rows, parse_file, suggest_mapping
from .transactions import TransactionError, TransactionInput, build_transaction, fingerprint

PREVIEW_ROWS = 25


def create_job(db: Session, ctx: UserContext, filename: str, content: bytes, password: str | None, account_id: int | None) -> ImportJob:
    parsed: ParsedFile = parse_file(filename, content, password)
    job = ImportJob(
        user_id=ctx.user_id, filename=filename[:255], file_format=parsed.file_format, status="preview",
        bank_detected=parsed.bank_detected, headers=parsed.headers, raw_rows=parsed.rows,
        mapping=parsed.preset_mapping or suggest_mapping(parsed.headers), account_id=account_id,
        parse_info={"method": parsed.method, "notes": parsed.notes or []},
    )
    db.add(job)
    db.flush()
    if account_id:
        validate(db, ctx, job, job.mapping, account_id)
    return job


def _existing_fingerprints(db: Session, user_id: int, account_id: int, start: date, end: date) -> tuple[Counter, set[str]]:
    rows = db.execute(
        select(Transaction.fingerprint, Transaction.external_id).where(
            Transaction.user_id == user_id, Transaction.account_id == account_id, Transaction.date >= start, Transaction.date <= end
        )
    ).all()
    counts = Counter(r.fingerprint for r in rows)
    external = {r.external_id for r in rows if r.external_id}
    return counts, external


def validate(db: Session, ctx: UserContext, job: ImportJob, mapping: dict, account_id: int) -> ImportJob:
    account = db.get(Account, account_id)
    if account is None or account.user_id != ctx.user_id:
        raise TransactionError("Account not found")
    job.account_id = account.id
    job.mapping = mapping
    rows = normalize_rows(job.headers, job.raw_rows, mapping)
    ok_rows = [r for r in rows if r["status"] == "ok"]
    if ok_rows:
        dates = [date.fromisoformat(r["date"]) for r in ok_rows]
        existing, external = _existing_fingerprints(db, ctx.user_id, account.id, min(dates), max(dates))
        for r in ok_rows:
            try:
                minor = to_minor(r["amount"], account.currency)
            except ValueError as exc:
                r.update(status="error", error=str(exc))
                continue
            signed = minor if r["direction"] == "in" else -minor
            fp = fingerprint(account.id, date.fromisoformat(r["date"]), signed, r["description"])
            r["fingerprint"] = fp
            if r.get("external_id") and r["external_id"] in external:
                r["status"] = "duplicate"
            elif existing[fp] > 0:
                existing[fp] -= 1  # consume: two identical rows in a file only match two existing rows
                r["status"] = "duplicate"
    job.normalized = rows
    job.duplicate_count = sum(1 for r in rows if r["status"] == "duplicate")
    job.error_count = sum(1 for r in rows if r["status"] == "error")
    job.status = "validated"
    return job


def commit(db: Session, ctx: UserContext, job: ImportJob, include_rows: set[int] | None = None, type_overrides: dict[int, str] | None = None) -> dict:
    if job.status != "validated" or not job.account_id:
        raise TransactionError("Validate the column mapping before importing")
    include_rows = include_rows or set()
    type_overrides = type_overrides or {}
    created: list[Transaction] = []
    skipped = 0
    errors = 0
    for r in job.normalized:
        if r["status"] == "error":
            errors += 1
            continue
        if r["status"] == "duplicate" and r["row"] not in include_rows:
            skipped += 1
            continue
        txn_type = type_overrides.get(r["row"], r["type"])
        try:
            with db.begin_nested():
                txn = build_transaction(db, ctx.user_id, ctx.base_currency, TransactionInput(
                    type=txn_type, account_id=job.account_id, date=date.fromisoformat(r["date"]), amount=r["amount"],
                    description=r["merchant"] or r["description"], merchant=r.get("merchant"), notes=r.get("notes") or "",
                    payment_method=r.get("payment_method") or "", source="import", external_id=r.get("external_id"),
                    raw_description=r["description"], import_job_id=job.id,
                ))
            created.append(txn)
            r["status"] = "imported"
            r["transaction_id"] = txn.id
        except (TransactionError, ValueError) as exc:
            r["status"] = "error"
            r["error"] = str(exc)
            errors += 1
    # JSON columns need reassignment for SQLAlchemy to notice in-place changes.
    job.normalized = list(job.normalized)
    job.imported_count = len(created)
    job.duplicate_count = skipped
    job.error_count = errors
    job.skipped_count = skipped
    job.status = "completed"
    job.completed_at = utcnow()
    job.raw_rows = []  # the parsed rows remain in `normalized`; drop the raw copy
    alerts.after_ledger_change(db, ctx, created)
    return {"imported": len(created), "duplicates_skipped": skipped, "errors": errors, "total_rows": len(job.normalized)}


def undo(db: Session, ctx: UserContext, job: ImportJob) -> int:
    count = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.user_id == ctx.user_id, Transaction.import_job_id == job.id)) or 0
    for txn in db.scalars(select(Transaction).where(Transaction.user_id == ctx.user_id, Transaction.import_job_id == job.id)).all():
        db.delete(txn)
    job.status = "cancelled"
    return int(count)
