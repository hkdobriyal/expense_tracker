"""Database engine, session factory and shared column types.

The schema is written against SQLAlchemy's portable types so the same models
run on SQLite (zero-setup local default) and PostgreSQL (set DATABASE_URL).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """Stores timezone-aware datetimes as naive UTC and returns them as aware UTC.

    SQLite has no timezone support, so normalising at the boundary keeps
    comparisons correct on both SQLite and PostgreSQL.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


_engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def init_engine(database_url: str) -> Engine:
    """(Re)initialise the global engine. Tests call this with a temporary database."""
    global _engine
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
            # Let SQLAlchemy (not the sqlite3 module) decide when transactions start.
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.close()

        @event.listens_for(engine, "begin")
        def _sqlite_begin(conn):  # pragma: no cover - driver hook
            # The API and the worker are separate processes. A transaction that starts as a
            # read and later writes fails instantly with "database is locked" if the other
            # process wrote in between (SQLite can't upgrade a stale snapshot). Taking the
            # write lock up front makes writers queue (busy_timeout) instead of failing.
            conn.exec_driver_sql("BEGIN IMMEDIATE")

    _engine = engine
    SessionLocal.configure(bind=engine)
    return engine


def get_engine() -> Engine:
    if _engine is None:
        from .config import get_settings

        init_engine(get_settings().database_url)
    assert _engine is not None
    return _engine


def get_db() -> Iterator[Session]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
