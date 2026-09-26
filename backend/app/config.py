"""Application configuration.

All configuration comes from environment variables (optionally loaded from
``backend/.env``). Nothing secret is hard-coded: when SECRET_KEY or
ENCRYPTION_KEY are not provided, a random key is generated once and persisted
inside the data directory so sessions and encrypted bank credentials survive
restarts.
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_data_dir() -> Path:
    # Personal finance data lives outside the (OneDrive-synced) source tree by default.
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "Ledgerly"


def _persistent_secret(data_dir: Path, filename: str, factory) -> str:
    """Read a generated secret, creating it atomically on first use.

    The API and the worker may start at the same moment; exclusive creation
    ("x" mode) guarantees both end up using the same key.
    """
    path = data_dir / filename
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(factory())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except FileExistsError:
        pass
    for _ in range(50):  # another process may still be writing it
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
        time.sleep(0.05)
    raise RuntimeError(f"Secret file {path} is empty")


@dataclass(frozen=True)
class Settings:
    env: str
    data_dir: Path
    database_url: str
    app_url: str
    cors_origins: tuple[str, ...]
    secret_key: str
    encryption_key: str
    allow_registration: bool
    session_days: int
    cookie_secure: bool
    auto_migrate: bool
    jobs_inline: bool
    max_upload_mb: int
    default_currency: str
    default_timezone: str

    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_starttls: bool

    sms_provider: str
    whatsapp_provider: str

    setu_client_id: str
    setu_client_secret: str
    setu_product_instance_id: str
    setu_env: str

    @property
    def uploads_dir(self) -> Path:
        path = self.data_dir / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host)


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("DATA_DIR") or _default_data_dir())
    data_dir.mkdir(parents=True, exist_ok=True)

    database_url = os.environ.get("DATABASE_URL") or f"sqlite:///{(data_dir / 'ledgerly.sqlite3').as_posix()}"
    app_url = os.environ.get("APP_URL", "http://localhost:5173").rstrip("/")
    cors = tuple(o.strip() for o in os.environ.get("CORS_ORIGINS", app_url).split(",") if o.strip())

    secret_key = os.environ.get("SECRET_KEY") or _persistent_secret(data_dir, "secret.key", lambda: secrets.token_urlsafe(48))

    def _fernet_key() -> str:
        from cryptography.fernet import Fernet

        return Fernet.generate_key().decode()

    encryption_key = os.environ.get("ENCRYPTION_KEY") or _persistent_secret(data_dir, "encryption.key", _fernet_key)

    return Settings(
        env=os.environ.get("APP_ENV", "development"),
        data_dir=data_dir,
        database_url=database_url,
        app_url=app_url,
        cors_origins=cors,
        secret_key=secret_key,
        encryption_key=encryption_key,
        allow_registration=_bool("ALLOW_REGISTRATION", False),
        session_days=int(os.environ.get("SESSION_DAYS", "14")),
        cookie_secure=_bool("COOKIE_SECURE", app_url.startswith("https://")),
        auto_migrate=_bool("AUTO_MIGRATE", True),
        jobs_inline=_bool("JOBS_INLINE", False),
        max_upload_mb=int(os.environ.get("MAX_UPLOAD_MB", "10")),
        default_currency=os.environ.get("DEFAULT_CURRENCY", "INR").upper(),
        default_timezone=os.environ.get("DEFAULT_TIMEZONE", "Asia/Kolkata"),
        smtp_host=os.environ.get("SMTP_HOST", ""),
        smtp_port=int(os.environ.get("SMTP_PORT", "1025")),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        smtp_from=os.environ.get("SMTP_FROM", "Ledgerly <ledgerly@localhost>"),
        smtp_starttls=_bool("SMTP_STARTTLS", False),
        sms_provider=os.environ.get("SMS_PROVIDER", "mock").lower(),
        whatsapp_provider=os.environ.get("WHATSAPP_PROVIDER", "mock").lower(),
        setu_client_id=os.environ.get("SETU_CLIENT_ID", ""),
        setu_client_secret=os.environ.get("SETU_CLIENT_SECRET", ""),
        setu_product_instance_id=os.environ.get("SETU_PRODUCT_INSTANCE_ID", ""),
        setu_env=os.environ.get("SETU_ENV", "sandbox"),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
