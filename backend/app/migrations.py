"""Run Alembic migrations programmatically (used at API/worker start-up when AUTO_MIGRATE=true)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import BACKEND_DIR, get_settings


def alembic_config(database_url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(BACKEND_DIR) / "alembic"))
    cfg.set_main_option("sqlalchemy.url", (database_url or get_settings().database_url).replace("%", "%%"))
    return cfg


def upgrade_database(database_url: str | None = None) -> None:
    command.upgrade(alembic_config(database_url), "head")
