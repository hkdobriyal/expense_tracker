"""Password hashing, session tokens, secret encryption and rate limiting.

* Passwords: scrypt from the standard library (memory-hard, no native deps).
* Sessions: random 256-bit tokens in an HttpOnly cookie; only a SHA-256 hash
  is stored, so a leaked database cannot be replayed as a login.
* CSRF: double-submit token. The per-session token is readable by the SPA and
  must be echoed in ``X-CSRF-Token`` for every state-changing request.
* Secrets at rest (bank tokens): Fernet (AES-128-CBC + HMAC).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict, deque

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**15, 8, 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), maxmem=_SCRYPT_MAXMEM, dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> str | None:
    if len(password) < 10:
        return "Password must be at least 10 characters long."
    if password.lower() == password or password.upper() == password or not any(ch.isdigit() for ch in password):
        return "Use upper- and lower-case letters and at least one number."
    return None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # Keyed hash so tokens cannot be brute-forced offline without the server secret.
    return hmac.new(get_settings().secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


# --- Encryption for provider credentials --------------------------------------------------------

def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str | None) -> dict:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError):
        return {}


def mask(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if "@" in value:
        name, _, domain = value.partition("@")
        return f"{name[:2]}***@{domain}"
    return f"{'*' * max(len(value) - keep, 0)}{value[-keep:]}"


# --- Rate limiting ------------------------------------------------------------------------------

class RateLimiter:
    """In-memory sliding-window limiter. Good enough for a single-process personal app;
    swap for Redis/Valkey if the API is ever run with multiple workers."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()
