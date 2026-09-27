"""A tiny database-backed job queue.

Why not Celery/BullMQ? They need Redis. A jobs table works on SQLite and
PostgreSQL, survives restarts, and is easy to inspect while learning. On
PostgreSQL, ``FOR UPDATE SKIP LOCKED`` lets several workers run safely.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import Job

log = logging.getLogger("hisaab.jobs")

HANDLERS: dict[str, Callable[[Session, dict], None]] = {}


def handler(job_type: str):
    def register(fn: Callable[[Session, dict], None]):
        HANDLERS[job_type] = fn
        return fn

    return register


def enqueue(db: Session, job_type: str, payload: dict, run_at: datetime | None = None, max_attempts: int = 5) -> Job:
    job = Job(type=job_type, payload=payload, run_at=run_at or utcnow(), max_attempts=max_attempts)
    db.add(job)
    db.flush()
    if get_settings().jobs_inline:
        run(db, job, isolated=False)
    return job


def _claim(db: Session, limit: int) -> list[Job]:
    stmt = select(Job).where(Job.status == "queued", Job.run_at <= utcnow()).order_by(Job.run_at, Job.id).limit(limit)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    jobs = db.scalars(stmt).all()
    for job in jobs:
        job.status = "running"
    db.commit()
    return jobs


class Retry(Exception):
    """Raised by handlers that recorded their own failure state and want a retry later."""


def run(db: Session, job: Job, isolated: bool = True) -> None:
    """Run one job. ``isolated`` (worker mode) rolls back partial work on unexpected errors."""
    _ensure_handlers()
    fn = HANDLERS.get(job.type)
    attempts = job.attempts + 1
    error: str | None = None
    try:
        if fn is None:
            raise LookupError(f"No handler for job type {job.type}")
        fn(db, job.payload or {})
    except Retry as exc:
        error = str(exc)[:2000]
    except Exception as exc:  # noqa: BLE001 - every failure is recorded on the job
        if isolated:
            db.rollback()
        error = "".join(traceback.format_exception_only(type(exc), exc)).strip()[:2000]
    job.attempts = attempts
    if error is None:
        job.status = "done"
        job.finished_at = utcnow()
        job.last_error = None
        return
    log.warning("job %s (%s) failed: %s", job.id, job.type, error)
    job.last_error = error
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.finished_at = utcnow()
    else:
        job.status = "queued"
        job.run_at = utcnow() + timedelta(seconds=30 * 2 ** (job.attempts - 1))  # exponential backoff


def process_due(db: Session, limit: int = 20) -> int:
    jobs = _claim(db, limit)
    for job in jobs:
        run(db, job)
        db.commit()
    return len(jobs)


_loaded = False


def _ensure_handlers() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    from . import notifications, banking  # noqa: F401 - registers handlers

    @handler("deliver_notification")
    def _deliver(db: Session, payload: dict) -> None:
        notifications.deliver(db, int(payload["delivery_id"]))

    @handler("bank_sync")
    def _sync(db: Session, payload: dict) -> None:
        banking.sync_connection_by_id(db, int(payload["connection_id"]), trigger="scheduled")
