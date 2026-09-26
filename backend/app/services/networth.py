"""Net worth = assets − liabilities, current and historical (month-end) values."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, NetWorthSnapshot
from . import ledger
from .periods import add_months, month_bounds


def net_worth(db: Session, user_id: int, base_currency: str, as_of: date | None = None) -> dict:
    accounts = db.scalars(select(Account).where(Account.user_id == user_id, Account.include_in_net_worth.is_(True))).all()
    if as_of is not None:
        accounts = [a for a in accounts if a.opening_date is None or a.opening_date <= as_of]
    balances = ledger.balances_in_base(db, user_id, base_currency, as_of, accounts)
    by_id = {a.id: a for a in accounts}
    assets = liabilities = 0
    breakdown: dict[str, int] = {}
    missing: set[str] = set()
    for b in balances:
        if b.base_minor is None:
            missing.add(b.currency)
            continue
        acc = by_id[b.account_id]
        if acc.is_liability:
            liabilities += -b.base_minor  # owed amounts are negative balances
        else:
            assets += b.base_minor
        breakdown[acc.type] = breakdown.get(acc.type, 0) + b.base_minor
    return {
        "as_of": (as_of or date.today()).isoformat(),
        "currency": base_currency,
        "assets": assets,
        "liabilities": liabilities,
        "net_worth": assets - liabilities,
        "by_type": breakdown,
        "missing_rates": sorted(missing),
    }


def history(db: Session, user_id: int, base_currency: str, today: date, months: int = 12) -> list[dict]:
    """Month-end net worth computed from the ledger (no need to wait for snapshots)."""
    points = []
    for offset in range(months - 1, -1, -1):
        month_end = month_bounds(add_months(today, -offset))[1]
        point_date = min(month_end, today)
        nw = net_worth(db, user_id, base_currency, point_date)
        points.append({"date": point_date.isoformat(), "assets": nw["assets"], "liabilities": nw["liabilities"], "net_worth": nw["net_worth"]})
    return points


def take_snapshot(db: Session, user_id: int, base_currency: str, today: date) -> NetWorthSnapshot:
    nw = net_worth(db, user_id, base_currency, today)
    snap = db.scalar(select(NetWorthSnapshot).where(NetWorthSnapshot.user_id == user_id, NetWorthSnapshot.date == today))
    if snap is None:
        snap = NetWorthSnapshot(user_id=user_id, date=today, currency=base_currency, assets_minor=0, liabilities_minor=0, net_worth_minor=0)
        db.add(snap)
    snap.assets_minor = nw["assets"]
    snap.liabilities_minor = nw["liabilities"]
    snap.net_worth_minor = nw["net_worth"]
    snap.breakdown = {"by_type": nw["by_type"], "missing_rates": nw["missing_rates"]}
    return snap
