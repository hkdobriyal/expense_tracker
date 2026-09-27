"""On-device machine-learning categoriser (scikit-learn, BSD licence – free, offline).

Model: TF-IDF over character n-grams (robust to "SWIGGY8", "swiggy.stores")
+ word n-grams + extracted-entity tokens (mode, UPI handle, amount bucket),
fed to a class-balanced logistic regression. One small model per user,
stored in DATA_DIR/models.

Training data = the user's own labelled transactions (manual categories,
rules, reviewed suggestions) + synthetic seed examples from the built-in
keyword list, so predictions work from day one and adapt to *your* merchants.
"""

from __future__ import annotations

import logging
import math
import re
import threading
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import Category, SystemState, Transaction
from .catalog import KEYWORD_HINTS
from .extraction import extract

log = logging.getLogger("hisaab.ml")

AUTO_APPLY = 0.55      # confidence needed to set a category automatically
SUGGEST = 0.30         # below this we don't even suggest
_cache: dict[int, tuple[float, object, dict]] = {}
_lock = threading.Lock()


def features(description: str, merchant: str | None = None, raw: str = "", txn_type: str = "expense", amount_minor: int | None = None) -> str:
    text = f"{merchant or ''} {description or ''} {raw or ''}"
    e = extract(raw or description or "")
    tokens = [f"type_{txn_type}"]
    if e.get("mode"):
        tokens.append(f"mode_{e['mode'].lower().replace(' ', '_')}")
    if e.get("vpa"):
        local, _, handle = e["vpa"].partition("@")
        tokens += [f"vpah_{handle}", re.sub(r"\d+", "", local)]
    if e.get("merchant"):
        tokens.append(e["merchant"])
    if e.get("counterparty"):
        tokens.append(f"cp_{e['counterparty']}")
    if amount_minor:
        tokens.append(f"amt_b{min(int(math.log10(max(abs(amount_minor), 100))) , 8)}")
    clean = re.sub(r"\d{5,}", " ", text.lower())
    return " ".join(tokens) + " " + re.sub(r"[^a-z0-9@ ]+", " ", clean)


def _path_to_id(categories: list[Category]) -> dict[str, int]:
    by_id = {c.id: c for c in categories}
    out = {}
    for c in categories:
        parent = by_id.get(c.parent_id) if c.parent_id else None
        out[(f"{parent.name}/{c.name}" if parent else c.name).lower()] = c.id
    return out


def training_data(db: Session, user_id: int) -> tuple[list[str], list[int], int]:
    categories = db.scalars(select(Category).where(Category.user_id == user_id, Category.is_archived.is_(False))).all()
    valid = {c.id for c in categories}
    rows = db.execute(
        select(Transaction.description, Transaction.raw_description, Transaction.type, Transaction.amount_minor, Transaction.category_id, Transaction.merchant_id)
        .where(Transaction.user_id == user_id, Transaction.category_id.is_not(None), Transaction.type.in_(("expense", "income", "refund")),
               (Transaction.reviewed.is_(True)) | (Transaction.category_source.in_(("user", "rule", "merchant"))))
    ).all()
    texts, labels = [], []
    for r in rows:
        if r.category_id in valid:
            texts.append(features(r.description, None, r.raw_description, r.type, r.amount_minor))
            labels.append(r.category_id)
    user_samples = len(texts)
    paths = _path_to_id(categories)
    for keyword, path in KEYWORD_HINTS:
        cat_id = paths.get(path.lower()) or paths.get(path.split("/")[0].lower())
        if cat_id:
            kind = next((c.kind for c in categories if c.id == cat_id), "expense")
            t = "income" if kind == "income" else "expense"
            for template in (f"UPI/DR/{keyword}/payment", f"{keyword}", f"POS {keyword} bangalore"):
                texts.append(features(template, keyword, template, t))
                labels.append(cat_id)
    return texts, labels, user_samples


def train(db: Session, user_id: int, release_lock: bool = False) -> dict:
    """Fit and save the user's model. release_lock (worker) ends the DB transaction before
    the CPU-heavy fit so the API isn't blocked while training."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline
    import joblib

    texts, labels, user_samples = training_data(db, user_id)
    if release_lock:
        db.rollback()
    classes = Counter(labels)
    if len(classes) < 2:
        raise ValueError("Need examples from at least two categories to train")
    pipeline = Pipeline([
        ("features", FeatureUnion([
            ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1, sublinear_tf=True, max_features=60000)),
            ("words", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, token_pattern=r"[a-z0-9_@]{2,}", sublinear_tf=True)),
        ])),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", C=4.0)),
    ])
    accuracy = None
    if user_samples >= 40:
        # Hold out the newest 20% of the user's own examples to estimate accuracy honestly.
        cut = int(user_samples * 0.8)
        holdout_x, holdout_y = texts[cut:user_samples], labels[cut:user_samples]
        train_x, train_y = texts[:cut] + texts[user_samples:], labels[:cut] + labels[user_samples:]
        if len(set(train_y)) >= 2:
            pipeline.fit(train_x, train_y)
            accuracy = round(float(sum(p == y for p, y in zip(pipeline.predict(holdout_x), holdout_y)) / len(holdout_y)), 3)
    pipeline.fit(texts, labels)
    meta = {
        "trained_at": utcnow().isoformat(), "user_samples": user_samples, "total_samples": len(texts), "classes": len(classes),
        "holdout_accuracy": accuracy, "model": "tfidf(char 2-5 + word 1-2) → logistic regression",
    }
    path = get_settings().models_dir / f"categorizer_user{user_id}.joblib"
    joblib.dump({"pipeline": pipeline, "meta": meta}, path)
    state = db.get(SystemState, f"ml:{user_id}") or SystemState(key=f"ml:{user_id}")
    state.value = meta
    state.updated_at = utcnow()
    db.merge(state)
    with _lock:
        _cache.pop(user_id, None)
    log.info("trained categoriser for user %s: %s", user_id, meta)
    return meta


def _load(db: Session, user_id: int):
    import joblib

    path = get_settings().models_dir / f"categorizer_user{user_id}.joblib"
    if not path.exists():
        try:
            train(db, user_id)
        except ValueError:
            return None, None
    mtime = path.stat().st_mtime
    with _lock:
        cached = _cache.get(user_id)
        if cached and cached[0] == mtime:
            return cached[1], cached[2]
    bundle = joblib.load(path)  # our own file in DATA_DIR, never user-supplied
    with _lock:
        _cache[user_id] = (mtime, bundle["pipeline"], bundle["meta"])
    return bundle["pipeline"], bundle["meta"]


def predict(db: Session, user_id: int, description: str, merchant: str | None = None, raw: str = "", txn_type: str = "expense",
            amount_minor: int | None = None, top: int = 3) -> list[tuple[int, float]]:
    """Return [(category_id, probability)] best first, restricted to categories of the right kind."""
    if not get_settings().ml_enabled:
        return []
    try:
        model, _ = _load(db, user_id)
    except Exception:  # noqa: BLE001 - a broken model file must never break a transaction save
        log.exception("could not load categoriser")
        return []
    if model is None:
        return []
    kind = "income" if txn_type == "income" else "expense"
    allowed = {c.id for c in db.scalars(select(Category).where(Category.user_id == user_id, Category.kind == kind, Category.is_archived.is_(False))).all()}
    probs = model.predict_proba([features(description, merchant, raw, txn_type, amount_minor)])[0]
    ranked = sorted(((int(c), float(p)) for c, p in zip(model.classes_, probs) if int(c) in allowed), key=lambda x: -x[1])
    total = sum(p for _, p in ranked) or 1.0
    return [(c, round(p / total, 3)) for c, p in ranked[:top]]  # renormalise over allowed categories


def status(db: Session, user_id: int) -> dict:
    state = db.get(SystemState, f"ml:{user_id}")
    labelled = len(training_data(db, user_id)[0]) if state is None else (state.value or {}).get("total_samples")
    return {"enabled": get_settings().ml_enabled, "trained": state is not None, **(state.value if state else {}), "examples": labelled}


def needs_retrain(db: Session, user_id: int) -> bool:
    state = db.get(SystemState, f"ml:{user_id}")
    if state is None:
        return True
    _, _, user_samples = training_data(db, user_id)
    return user_samples - int((state.value or {}).get("user_samples", 0)) >= 10 or (datetime.now(timezone.utc) - state.updated_at).days >= 7
