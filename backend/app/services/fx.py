"""Exchange rates.

Rates are entered by the user (free, no external API). A future adapter can
fill the same table from a rate provider. When a rate is missing we say so
instead of silently adding different currencies together.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExchangeRate


def latest_rate(db: Session, user_id: int, from_currency: str, to_currency: str, on: date | None = None) -> Decimal | None:
    """Return the rate so that 1 ``from_currency`` = rate ``to_currency``, or None."""
    if from_currency == to_currency:
        return Decimal(1)

    def _query(base: str, quote: str):
        stmt = select(ExchangeRate).where(
            ExchangeRate.user_id == user_id, ExchangeRate.base_currency == base, ExchangeRate.quote_currency == quote
        )
        if on is not None:
            stmt = stmt.where(ExchangeRate.as_of <= on)
        return db.scalar(stmt.order_by(ExchangeRate.as_of.desc()).limit(1))

    direct = _query(from_currency, to_currency)
    if direct is not None:
        return Decimal(direct.rate)
    inverse = _query(to_currency, from_currency)
    if inverse is not None and Decimal(inverse.rate) != 0:
        return (Decimal(1) / Decimal(inverse.rate)).quantize(Decimal("0.0000000001"))
    if on is not None:
        # Fall back to the earliest known rate after the date rather than failing outright.
        return latest_rate(db, user_id, from_currency, to_currency, None)
    return None
