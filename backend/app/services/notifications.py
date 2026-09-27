"""Notification channels behind one provider interface.

    in_app    – stored in the notifications table (always free)
    email     – SMTP (Gmail/Outlook app password, any mail host, Mailpit locally); log fallback
    push      – Web Push to subscribed browsers (VAPID, free)
    sms       – mock adapter (logs only) until a real provider is chosen
    whatsapp  – mock adapter (logs only) until a real provider is chosen

Delivery statuses are explicit: "mocked" and "logged" never pretend a message
reached a phone or inbox.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import AlertEvent, Notification, NotificationDelivery, User, UserSettings
from ..security import mask

log = logging.getLogger("hisaab.notifications")


@dataclass
class Message:
    title: str
    body: str
    severity: str = "info"
    category: str = "system"
    link: str = ""


@dataclass
class DeliveryResult:
    status: str  # sent|failed|skipped|mocked|logged
    provider: str
    error: str | None = None


class NotificationProvider(Protocol):
    name: str

    def send(self, destination: str, message: Message) -> DeliveryResult: ...


class EmailProvider:
    name = "smtp"

    def send(self, destination: str, message: Message) -> DeliveryResult:
        from .email import send_email

        link = f"{get_settings().app_url}{message.link}" if message.link else None
        result = send_email(destination, message.title, message.body, link, "Open in app" if link else None)
        return DeliveryResult(result.status, result.provider, result.error)


class MockSMSProvider:
    name = "mock-sms"

    def send(self, destination: str, message: Message) -> DeliveryResult:
        log.info("SMS (mock) to=%s text=%s", mask(destination), message.title)
        return DeliveryResult("mocked", self.name, "Mock SMS provider – no message was sent")


class MockWhatsAppProvider:
    name = "mock-whatsapp"

    def send(self, destination: str, message: Message) -> DeliveryResult:
        log.info("WHATSAPP (mock) to=%s text=%s", mask(destination), message.title)
        return DeliveryResult("mocked", self.name, "Mock WhatsApp provider – no message was sent")


class WebPushProvider:
    """``destination`` is the user id; every browser the user subscribed receives the push."""

    name = "webpush"

    def __init__(self, db: Session):
        self.db = db

    def send(self, destination: str, message: Message) -> DeliveryResult:
        from .push import send_to_user

        delivered, errors = send_to_user(self.db, int(destination), message.title, message.body, message.link or "/")
        if delivered:
            return DeliveryResult("sent", self.name, "; ".join(errors) or None)
        return DeliveryResult("failed" if errors and "subscribed" not in errors[0] else "skipped", self.name, "; ".join(errors) or None)


def provider_for(channel: str, db: Session | None = None) -> NotificationProvider:
    if channel == "email":
        return EmailProvider()
    if channel == "sms":
        return MockSMSProvider()  # real adapters (e.g. MSG91, Twilio) plug in here – see docs/notifications.md
    if channel == "whatsapp":
        return MockWhatsAppProvider()
    return WebPushProvider(db)


def destination_for(channel: str, user: User, settings: UserSettings) -> str:
    if channel == "email":
        return settings.contact_email or user.email
    if channel == "sms":
        return settings.contact_phone
    if channel == "whatsapp":
        return settings.whatsapp_number or settings.contact_phone
    if channel == "push":
        return str(user.id)
    return ""


def channel_enabled(settings: UserSettings, channel: str) -> bool:
    return bool(getattr(settings, f"channel_{channel}", False))


def resolve_channels(settings: UserSettings, category: str, rule_channels: list[str] | None) -> list[str]:
    if rule_channels is not None:
        wanted = rule_channels
    else:
        matrix = settings.notification_matrix or {}
        wanted = [c for c, on in (matrix.get(category) or {"in_app": True}).items() if on]
    return [c for c in ("in_app", "email", "sms", "whatsapp", "push") if c in wanted and channel_enabled(settings, c)]


def dispatch(db: Session, user: User, settings: UserSettings, event: AlertEvent, channels: list[str]) -> list[NotificationDelivery]:
    """Create the in-app notification and queue external deliveries for an alert event."""
    from . import jobs  # local import to avoid a cycle

    deliveries = []
    notification = None
    if "in_app" in channels:
        notification = Notification(
            user_id=user.id, alert_event_id=event.id, category=event.category, severity=event.severity,
            title=event.title, message=event.message, link=event.context.get("link", "") if event.context else "",
        )
        db.add(notification)
        db.flush()
        deliveries.append(NotificationDelivery(user_id=user.id, alert_event_id=event.id, notification_id=notification.id, channel="in_app", provider="in_app", status="sent", sent_at=utcnow(), attempts=1))
    for channel in channels:
        if channel == "in_app":
            continue
        destination = destination_for(channel, user, settings)
        if not destination:
            deliveries.append(NotificationDelivery(user_id=user.id, alert_event_id=event.id, channel=channel, status="skipped", error=f"No {channel} destination configured in Settings"))
            continue
        deliveries.append(NotificationDelivery(user_id=user.id, alert_event_id=event.id, notification_id=notification.id if notification else None, channel=channel, destination="browser" if channel == "push" else mask(destination), status="queued"))
    for d in deliveries:
        db.add(d)
    db.flush()
    for d in deliveries:
        if d.status == "queued":
            jobs.enqueue(db, "deliver_notification", {"delivery_id": d.id})
    return deliveries


def deliver(db: Session, delivery_id: int) -> NotificationDelivery | None:
    delivery = db.get(NotificationDelivery, delivery_id)
    if delivery is None or delivery.status not in ("queued", "failed"):
        return delivery
    user = db.get(User, delivery.user_id)
    event = db.get(AlertEvent, delivery.alert_event_id) if delivery.alert_event_id else None
    if user is None or event is None:
        delivery.status = "skipped"
        delivery.error = "Alert no longer exists"
        return delivery
    settings = user.settings
    destination = destination_for(delivery.channel, user, settings)
    provider = provider_for(delivery.channel, db)
    result = provider.send(destination, Message(event.title, event.message, event.severity, event.category, (event.context or {}).get("link", "")))
    delivery.attempts += 1
    delivery.provider = result.provider
    delivery.status = result.status
    delivery.error = result.error
    if result.status in ("sent", "logged", "mocked"):
        delivery.sent_at = utcnow()
    if result.status == "failed":
        from .jobs import Retry

        raise Retry(result.error or "delivery failed")  # the job runner retries with backoff
    return delivery


def unread_count(db: Session, user_id: int) -> int:
    from sqlalchemy import func

    return int(db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))) or 0)
