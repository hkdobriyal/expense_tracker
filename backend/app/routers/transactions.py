"""Transactions: CRUD, filtering, bulk actions, attachments and global search."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import serializers as ser
from ..config import get_settings
from ..db import get_db
from ..deps import CurrentUser, client_ip, get_current_user, get_owned
from ..models import Account, Attachment, Bill, Category, Merchant, Subscription, Tag, Transaction, TransactionSplit
from ..money import to_minor
from ..schemas import BulkIn, TransactionIn
from ..services import alerts, audit, ledger
from ..services.transactions import TransactionInput, build_transaction, duplicate_of, learn_merchant_category, resolve_tags
from .common import ctx_of

router = APIRouter(prefix="/api", tags=["transactions"])

ALLOWED_ATTACHMENTS = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG", "application/pdf": b"%PDF"}


def _input(body: TransactionIn) -> TransactionInput:
    return TransactionInput(
        type=body.type, account_id=body.account_id, date=body.date, amount=body.amount, description=body.description,
        merchant=body.merchant, category_id=body.category_id, notes=body.notes, payment_method=body.payment_method,
        tags=body.tags, transfer_account_id=body.transfer_account_id, transfer_amount=body.transfer_amount, fx_rate=body.fx_rate,
        original_amount=body.original_amount, original_currency=body.original_currency, is_recurring=body.is_recurring,
        reviewed=body.reviewed, splits=[s.model_dump() for s in body.splits] if body.splits else None,
    )


def _load(db: Session, current: CurrentUser, txn_id: int) -> Transaction:
    return get_owned(db, Transaction, txn_id, current, "Transaction")


@router.get("/transactions")
def list_transactions(
    q: str = "",
    start: Optional[date] = None,
    end: Optional[date] = None,
    type: Optional[list[str]] = Query(default=None),
    account_id: Optional[list[int]] = Query(default=None),
    category_id: Optional[list[int]] = Query(default=None),
    include_subcategories: bool = True,
    uncategorized: bool = False,
    merchant_id: Optional[int] = None,
    tag: Optional[str] = None,
    source: Optional[str] = None,
    reviewed: Optional[bool] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
    sort: Literal["date", "amount", "description", "created"] = "date",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conds = [Transaction.user_id == current.id]
    if q:
        like = f"%{q.strip()}%"
        conds.append(or_(Transaction.description.ilike(like), Transaction.notes.ilike(like), Transaction.raw_description.ilike(like), Transaction.merchant.has(Merchant.name.ilike(like))))
    if start:
        conds.append(Transaction.date >= start)
    if end:
        conds.append(Transaction.date <= end)
    if type:
        conds.append(Transaction.type.in_(type))
    if account_id:
        conds.append(or_(Transaction.account_id.in_(account_id), Transaction.transfer_account_id.in_(account_id)))
    if uncategorized:
        conds.append(Transaction.category_id.is_(None))
        conds.append(Transaction.type.in_(("expense", "income", "refund")))
        conds.append(~Transaction.splits.any())
    elif category_id:
        ids = set(category_id)
        if include_subcategories:
            cats = db.scalars(select(Category).where(Category.user_id == current.id)).all()
            for cid in category_id:
                ids |= ledger.descendant_ids(cats, cid)
        conds.append(or_(Transaction.category_id.in_(ids), Transaction.splits.any(TransactionSplit.category_id.in_(ids))))
    if merchant_id:
        conds.append(Transaction.merchant_id == merchant_id)
    if tag:
        conds.append(Transaction.tags.any(Tag.name == tag))
    if source:
        conds.append(Transaction.source == source)
    if reviewed is not None:
        conds.append(Transaction.reviewed.is_(reviewed))
    base = current.base_currency
    if min_amount is not None:
        conds.append(func.abs(Transaction.base_amount_minor) >= to_minor(min_amount, base))
    if max_amount is not None:
        conds.append(func.abs(Transaction.base_amount_minor) <= to_minor(max_amount, base))

    total = db.scalar(select(func.count()).select_from(Transaction).where(*conds)) or 0
    sort_col = {"date": Transaction.date, "amount": Transaction.base_amount_minor, "description": Transaction.description, "created": Transaction.created_at}[sort]
    ordering = [sort_col.desc() if order == "desc" else sort_col.asc(), Transaction.id.desc()]
    rows = db.scalars(
        select(Transaction).where(*conds).order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
        .options(selectinload(Transaction.tags), selectinload(Transaction.splits), selectinload(Transaction.attachments))
    ).all()
    # Summary of the whole filtered set (not just this page), computed in SQL.
    summary_rows = db.execute(select(Transaction.type, func.coalesce(func.sum(Transaction.base_amount_minor), 0)).where(*conds).group_by(Transaction.type)).all()
    by_type = {k: int(v) for k, v in summary_rows}
    return {
        "items": [ser.transaction(t) for t in rows],
        "total": total, "page": page, "page_size": page_size, "pages": (total + page_size - 1) // page_size,
        "summary": {
            "income": by_type.get("income", 0), "expenses": by_type.get("expense", 0) - by_type.get("refund", 0),
            "invested": by_type.get("investment", 0), "transfers": by_type.get("transfer", 0), "currency": base,
        },
    }


@router.post("/transactions", status_code=201)
def create_transaction(body: TransactionIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx = ctx_of(current)
    txn = build_transaction(db, current.id, current.base_currency, _input(body))
    learn_merchant_category(db, txn)
    fired = alerts.after_ledger_change(db, ctx, [txn])
    db.commit()
    return {**ser.transaction(txn), "alerts_triggered": [e.title for e in fired]}


@router.get("/transactions/{txn_id}")
def get_transaction(txn_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ser.transaction(_load(db, current, txn_id))


@router.put("/transactions/{txn_id}")
def update_transaction(txn_id: int, body: TransactionIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    txn = _load(db, current, txn_id)
    data = _input(body)
    data.source, data.external_id, data.raw_description = txn.source, txn.external_id, txn.raw_description
    build_transaction(db, current.id, current.base_currency, data, txn)
    learn_merchant_category(db, txn)
    alerts.after_ledger_change(db, ctx_of(current), [])
    db.commit()
    return ser.transaction(txn)


@router.patch("/transactions/{txn_id}")
def patch_transaction(txn_id: int, body: dict, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Quick edits from the list view: category, reviewed, notes, tags."""
    txn = _load(db, current, txn_id)
    allowed = {"category_id", "reviewed", "notes", "tags", "is_recurring"}
    unknown = set(body) - allowed
    if unknown:
        raise HTTPException(422, f"Unsupported fields: {', '.join(sorted(unknown))}")
    if "category_id" in body:
        if body["category_id"] is not None:
            get_owned(db, Category, int(body["category_id"]), current, "Category")
        if txn.splits:
            raise HTTPException(422, "Edit the splits to change categories of a split transaction")
        txn.category_id = body["category_id"]
        txn.category_source, txn.category_confidence = "user", None
        txn.reviewed = True
        db.flush()
        db.refresh(txn)
        learn_merchant_category(db, txn)
    if "reviewed" in body:
        txn.reviewed = bool(body["reviewed"])
    if "notes" in body:
        txn.notes = str(body["notes"] or "")[:5000]
    if "is_recurring" in body:
        txn.is_recurring = bool(body["is_recurring"])
    if "tags" in body:
        txn.tags = resolve_tags(db, current.id, [str(t) for t in body["tags"] or []])
    alerts.after_ledger_change(db, ctx_of(current), [])
    db.commit()
    return ser.transaction(txn)


@router.delete("/transactions/{txn_id}")
def delete_transaction(txn_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    txn = _load(db, current, txn_id)
    for att in txn.attachments:
        _remove_file(att)
    db.delete(txn)
    db.flush()
    alerts.after_ledger_change(db, ctx_of(current), [])
    db.commit()
    return {"deleted": True}


@router.post("/transactions/{txn_id}/duplicate", status_code=201)
def duplicate_transaction(txn_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    copy = duplicate_of(_load(db, current, txn_id))
    db.add(copy)
    db.flush()
    alerts.after_ledger_change(db, ctx_of(current), [copy])
    db.commit()
    return ser.transaction(copy)


@router.post("/transactions/bulk")
def bulk(body: BulkIn, request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    txns = db.scalars(select(Transaction).where(Transaction.user_id == current.id, Transaction.id.in_(body.ids))).all()
    if len(txns) != len(set(body.ids)):
        raise HTTPException(404, "Some transactions were not found")
    if body.action == "delete":
        for t in txns:
            for att in t.attachments:
                _remove_file(att)
            db.delete(t)
        audit.record(db, current.id, "transactions.bulk_deleted", "transaction", None, {"count": len(txns)}, client_ip(request))
    elif body.action == "categorize":
        if body.category_id is not None:
            get_owned(db, Category, body.category_id, current, "Category")
        for t in txns:
            if not t.splits:
                t.category_id = body.category_id
                t.category_source, t.category_confidence = "user", None
                t.reviewed = True
    elif body.action in ("mark_reviewed", "mark_unreviewed"):
        for t in txns:
            t.reviewed = body.action == "mark_reviewed"
    elif body.action in ("add_tag", "remove_tag"):
        if not body.tag:
            raise HTTPException(422, "Provide a tag")
        tag = resolve_tags(db, current.id, [body.tag])[0]
        for t in txns:
            if body.action == "add_tag" and tag not in t.tags:
                t.tags.append(tag)
            if body.action == "remove_tag" and tag in t.tags:
                t.tags.remove(tag)
    db.flush()
    alerts.after_ledger_change(db, ctx_of(current), [])
    db.commit()
    return {"updated": len(txns), "action": body.action}


# --- Attachments --------------------------------------------------------------------------------

def _remove_file(att: Attachment) -> None:
    path = get_settings().uploads_dir / att.storage_key
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


@router.post("/transactions/{txn_id}/attachments", status_code=201)
async def upload_attachment(txn_id: int, file: UploadFile = File(...), current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    txn = _load(db, current, txn_id)
    limit = get_settings().max_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"Files are limited to {get_settings().max_upload_mb} MB")
    content_type = next((ct for ct, magic in ALLOWED_ATTACHMENTS.items() if content.startswith(magic)), None)
    if content_type is None:
        raise HTTPException(415, "Receipts must be JPG, PNG or PDF files")
    key = f"{current.id}/{uuid.uuid4().hex}"
    path = get_settings().uploads_dir / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    safe_name = Path(file.filename or "receipt").name[:200]
    att = Attachment(user_id=current.id, transaction_id=txn.id, filename=safe_name, content_type=content_type, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), storage_key=key)
    db.add(att)
    db.commit()
    return ser.attachment(att)


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    att = get_owned(db, Attachment, attachment_id, current, "Attachment")
    path = get_settings().uploads_dir / att.storage_key
    if not path.exists():
        raise HTTPException(404, "File is missing from storage")
    return FileResponse(path, media_type=att.content_type, filename=att.filename, headers={"X-Content-Type-Options": "nosniff"})


@router.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    att = get_owned(db, Attachment, attachment_id, current, "Attachment")
    _remove_file(att)
    db.delete(att)
    db.commit()
    return {"deleted": True}


# --- Global search ------------------------------------------------------------------------------

@router.get("/search")
def search(q: str = Query(min_length=1, max_length=100), current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    like = f"%{q.strip()}%"
    uid = current.id
    txns = db.scalars(select(Transaction).where(Transaction.user_id == uid, or_(Transaction.description.ilike(like), Transaction.notes.ilike(like), Transaction.raw_description.ilike(like))).order_by(Transaction.date.desc()).limit(8)).all()
    return {
        "transactions": [{"id": t.id, "description": t.description, "date": t.date.isoformat(), "amount_minor": t.amount_minor, "currency": t.currency, "type": t.type} for t in txns],
        "merchants": [ser.merchant(m) for m in db.scalars(select(Merchant).where(Merchant.user_id == uid, Merchant.name.ilike(like)).limit(5))],
        "accounts": [{"id": a.id, "name": a.name, "type": a.type} for a in db.scalars(select(Account).where(Account.user_id == uid, or_(Account.name.ilike(like), Account.institution.ilike(like))).limit(5))],
        "categories": [ser.category(c) for c in db.scalars(select(Category).where(Category.user_id == uid, Category.name.ilike(like)).limit(5))],
        "bills": [{"id": b.id, "name": b.name, "next_due_date": b.next_due_date.isoformat()} for b in db.scalars(select(Bill).where(Bill.user_id == uid, Bill.name.ilike(like)).limit(5))],
        "subscriptions": [{"id": s.id, "name": s.name} for s in db.scalars(select(Subscription).where(Subscription.user_id == uid, Subscription.name.ilike(like)).limit(5))],
        "tags": [ser.tag(t) for t in db.scalars(select(Tag).where(Tag.user_id == uid, Tag.name.ilike(like)).limit(5))],
    }

