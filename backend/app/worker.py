"""Background worker: ``python -m app.worker``

Runs independently of the browser and the API process:

* every loop (~15 s): process queued jobs (email/SMS deliveries, bank syncs)
* every 10 min:        evaluate state alerts, create due recurring transactions
* hourly:              enqueue auto-sync for bank connections not synced in 6 h
* daily:               store a net-worth snapshot per user

It writes a heartbeat so Settings → System can show whether it is running.
"""

from __future__ import annotations

import logging
import signal
import time
from datetime import timedelta

from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal, get_engine, utcnow
from .migrations import upgrade_database
from .models import BankConnection, SystemState, User
from .services import alerts, jobs, networth, recurring
from .services.context import UserContext

log = logging.getLogger("ledgerly.worker")

LOOP_SECONDS = 15
ALERT_EVERY = timedelta(minutes=10)
SYNC_CHECK_EVERY = timedelta(hours=1)
AUTO_SYNC_AFTER = timedelta(hours=6)

_running = True


def _stop(*_):
    global _running
    _running = False


def heartbeat(db, info: dict) -> None:
    state = db.get(SystemState, "worker_heartbeat")
    if state is None:
        state = SystemState(key="worker_heartbeat")
        db.add(state)
    state.value = info
    state.updated_at = utcnow()
    db.commit()


def run_periodic(db, now, last: dict) -> None:
    users = db.scalars(select(User)).all()
    if now - last.get("alerts", now - ALERT_EVERY * 2) >= ALERT_EVERY:
        for user in users:
            try:
                ctx = UserContext.for_user(db, user)
                created = recurring.generate_due(db, user.id, ctx.base_currency, ctx.today)
                if created:
                    alerts.after_ledger_change(db, ctx, created)
                else:
                    alerts.evaluate_state_rules(db, ctx)
                db.commit()
            except Exception:  # noqa: BLE001 - one user's failure must not stop the others
                db.rollback()
                log.exception("periodic alert/recurring run failed for user %s", user.id)
        last["alerts"] = now
    if now - last.get("sync", now - SYNC_CHECK_EVERY * 2) >= SYNC_CHECK_EVERY:
        cutoff = now - AUTO_SYNC_AFTER
        for conn in db.scalars(select(BankConnection).where(BankConnection.auto_sync.is_(True), BankConnection.status == "active")).all():
            if conn.last_synced_at is None or conn.last_synced_at < cutoff:
                jobs.enqueue(db, "bank_sync", {"connection_id": conn.id}, max_attempts=2)
        db.commit()
        last["sync"] = now
    today_key = now.date().isoformat()
    if last.get("snapshot") != today_key:
        for user in users:
            try:
                ctx = UserContext.for_user(db, user)
                networth.take_snapshot(db, user.id, ctx.base_currency, ctx.today)
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("net worth snapshot failed for user %s", user.id)
        last["snapshot"] = today_key


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    get_engine()
    if settings.auto_migrate:
        upgrade_database()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    log.info("worker started (database: %s)", "sqlite" if settings.is_sqlite else "postgresql")
    last: dict = {}
    processed_total = 0
    while _running:
        db = SessionLocal()
        try:
            processed = jobs.process_due(db)
            processed_total += processed
            run_periodic(db, utcnow(), last)
            heartbeat(db, {"processed_total": processed_total, "last_batch": processed})
        except Exception:  # noqa: BLE001 - keep the worker alive; errors are logged
            db.rollback()
            log.exception("worker loop failed")
        finally:
            db.close()
        for _ in range(LOOP_SECONDS):
            if not _running:
                break
            time.sleep(1)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
