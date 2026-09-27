"""Browser push notifications via the Web Push standard (free, no account needed).

The server signs each push with its own VAPID key pair, generated once into
DATA_DIR. Browsers' push services (Chrome/Edge → Google, Firefox → Mozilla)
deliver them at no cost. Push works on http://localhost; any other host needs HTTPS.
"""

from __future__ import annotations

import base64
import json
import logging
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import PushSubscription

log = logging.getLogger("hisaab.push")
_lock = threading.Lock()


def _vapid():
    from py_vapid import Vapid

    path = get_settings().vapid_private_key_path
    with _lock:
        if not path.exists():
            v = Vapid()
            v.generate_keys()
            try:
                v.save_key(str(path))  # PEM, private
            except FileExistsError:
                pass
        return Vapid.from_file(str(path))


def public_key() -> str:
    from cryptography.hazmat.primitives import serialization

    raw = _vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def subscribe(db: Session, user_id: int, endpoint: str, p256dh: str, auth: str, user_agent: str = "") -> PushSubscription:
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=endpoint, user_id=user_id, p256dh=p256dh, auth=auth)
        db.add(sub)
    sub.user_id, sub.p256dh, sub.auth, sub.user_agent = user_id, p256dh, auth, user_agent[:300]
    db.flush()
    return sub


def subscription_count(db: Session, user_id: int) -> int:
    return len(db.scalars(select(PushSubscription.id).where(PushSubscription.user_id == user_id)).all())


def send_to_user(db: Session, user_id: int, title: str, body: str, url: str = "/", tag: str = "") -> tuple[int, list[str]]:
    """Send to every browser the user subscribed. Returns (delivered, errors)."""
    from pywebpush import WebPushException, webpush

    subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)).all()
    if not subs:
        return 0, ["No browser is subscribed – enable push in Settings → Notifications"]
    s = get_settings()
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag or title, "app": s.app_name})
    key_path = str(s.vapid_private_key_path)
    _vapid()  # make sure the key exists
    delivered, errors = 0, []
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=payload, vapid_private_key=key_path, vapid_claims={"sub": s.vapid_subject}, timeout=15, ttl=86400,
            )
            sub.last_used_at = utcnow()
            delivered += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):  # the browser unsubscribed or the subscription expired
                db.delete(sub)
                errors.append("A browser subscription had expired and was removed")
            else:
                errors.append(f"Push failed ({status or 'network'}): {str(exc)[:200]}")
        except Exception as exc:  # noqa: BLE001 - network errors etc.
            errors.append(f"Push failed: {type(exc).__name__}: {exc}"[:300])
    return delivered, errors
