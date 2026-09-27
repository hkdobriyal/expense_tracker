"""AI features: on-device ML categoriser, optional local LLM, entity extraction and the assistant."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, get_current_user
from ..models import Category, Transaction
from ..money import format_decimal, to_minor
from ..security import rate_limiter
from ..services import alerts, assistant, extraction, llm, ml
from ..services.categorization import get_or_create_merchant
from .common import ctx_of

router = APIRouter(prefix="/api/ai", tags=["ai"])


class SuggestIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    merchant: Optional[str] = Field(default=None, max_length=120)
    amount: Optional[Decimal] = None
    type: str = "expense"


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    use_llm: bool = True


class CategorizeIn(BaseModel):
    scope: str = Field(default="uncategorized", pattern="^(uncategorized|unreviewed|ids)$")
    ids: list[int] = Field(default_factory=list, max_length=500)
    use_llm: bool = True
    limit: int = Field(default=300, ge=1, le=1000)


def _category_paths(db: Session, user_id: int) -> tuple[dict[int, str], dict[str, int]]:
    cats = db.scalars(select(Category).where(Category.user_id == user_id, Category.is_archived.is_(False))).all()
    by_id = {c.id: c for c in cats}
    names = {c.id: (f"{by_id[c.parent_id].name}/{c.name}" if c.parent_id in by_id else c.name) for c in cats}
    return names, {v.lower(): k for k, v in names.items()}


@router.get("/status")
def status(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"ml": ml.status(db, current.id), "llm": llm.status(force=True), "ocr": {"engine": "RapidOCR (ONNX, local)"},
            "extraction": {"engine": "rule-based entity extraction for Indian bank narrations"}}


@router.post("/train")
def train(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if not rate_limiter.hit(f"train:{current.id}", 6, 600):
        raise HTTPException(429, "Training was requested too often")
    try:
        meta = ml.train(db, current.id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return meta


@router.post("/suggest")
def suggest(body: SuggestIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Live suggestion while typing a transaction (no LLM call – must be instant)."""
    entities = extraction.extract(body.description)
    amount_minor = to_minor(body.amount, current.base_currency) if body.amount else None
    names, _ = _category_paths(db, current.id)
    merchant = body.merchant or entities.get("merchant")
    preds = ml.predict(db, current.id, body.description, merchant, body.description, body.type, amount_minor)
    return {
        "entities": entities, "summary": extraction.summary(entities), "merchant": merchant,
        "payment_method": extraction.payment_method(entities),
        "suggestions": [{"category_id": c, "category": names.get(c, ""), "confidence": p} for c, p in preds if p >= ml.SUGGEST],
    }


@router.post("/extract")
def extract_text(body: SuggestIn, current: CurrentUser = Depends(get_current_user)):
    e = extraction.extract(body.description)
    return {"entities": e, "summary": extraction.summary(e)}


@router.post("/categorize")
def categorize(body: CategorizeIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Categorise many transactions: ML first; the local LLM (if running) handles what ML isn't sure about."""
    stmt = select(Transaction).where(Transaction.user_id == current.id, Transaction.type.in_(("expense", "income", "refund")), ~Transaction.splits.any())
    if body.scope == "uncategorized":
        stmt = stmt.where(Transaction.category_id.is_(None))
    elif body.scope == "unreviewed":
        stmt = stmt.where(Transaction.reviewed.is_(False), Transaction.category_source != "user")
    else:
        stmt = stmt.where(Transaction.id.in_(body.ids))
    txns = db.scalars(stmt.order_by(Transaction.date.desc()).limit(body.limit)).all()
    names, lookup = _category_paths(db, current.id)
    by_ml = by_llm = 0
    leftovers: list[Transaction] = []
    for t in txns:
        preds = ml.predict(db, current.id, t.description, t.merchant.name if t.merchant else None, t.raw_description,
                           "income" if t.type == "income" else "expense", t.amount_minor)
        if preds and preds[0][1] >= ml.AUTO_APPLY:
            if t.category_id != preds[0][0]:
                t.category_id = preds[0][0]
                by_ml += 1
            t.category_source, t.category_confidence = "ml", preds[0][1]
        else:
            leftovers.append(t)
    llm_state = llm.status()
    llm_error = None
    if body.use_llm and leftovers and llm_state["available"]:
        kinds = {c.id: c.kind for c in db.scalars(select(Category).where(Category.user_id == current.id)).all()}
        for i in range(0, len(leftovers), 20):
            chunk = leftovers[i:i + 20]
            try:
                results = llm.categorize(
                    [{"id": t.id, "text": (t.raw_description or t.description)[:200], "amount": format_decimal(t.amount_minor, t.currency), "type": t.type} for t in chunk],
                    sorted(names.values()),
                )
            except llm.LLMUnavailable as exc:
                llm_error = str(exc)
                break
            by_id = {t.id: t for t in chunk}
            for r in results:
                t = by_id.get(r["id"])
                cat_id = lookup.get(r["category"].lower())
                if t is None or cat_id is None:
                    continue
                wanted_kind = "income" if t.type == "income" else "expense"
                if kinds.get(cat_id) != wanted_kind:
                    continue
                t.category_id = cat_id
                t.category_source, t.category_confidence = "llm", r["confidence"]
                if r["merchant"] and t.merchant_id is None:
                    m = get_or_create_merchant(db, current.id, r["merchant"])
                    t.merchant_id = m.id if m else None
                by_llm += 1
    alerts.after_ledger_change(db, ctx_of(current), [])
    db.commit()
    return {
        "examined": len(txns), "categorized_by_ml": by_ml, "categorized_by_llm": by_llm,
        "still_uncertain": max(len(leftovers) - by_llm, 0),
        "llm": "used" if by_llm else (llm_error or llm_state.get("reason") or ("not needed" if not leftovers else "not used")),
    }


@router.post("/ask")
def ask(body: AskIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if not rate_limiter.hit(f"ask:{current.id}", 30, 60):
        raise HTTPException(429, "Slow down a little")
    return assistant.ask(db, ctx_of(current), body.question, body.use_llm)
