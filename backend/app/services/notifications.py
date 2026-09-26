"""Notification channels behind one provider interface.

    in_app    – stored in the notifications table (always free)
    email     – SMTP (Mailpit locally, any SMTP server in production); console fallback
    sms       – mock adapter (logs only) until a real provider is chosen
    whatsapp  – mock adapter (logs only) until a real provider is chosen
    push      – not implemented yet; deliveries are recorded as skipped

Delivery statuses are explicit: "mocked" and "logged" never pretend a message
reached a phone or inbox.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import AlertEvent, Notification, NotificationDelivery, User, UserSettings
from ..security import mask

log = logging.getLogger("ledgerly.notifications")


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


class SMTPEmailProvider:
    name = "smtp"

    def send(self, destination: str, message: Message) -> DeliveryResult:
        s = get_settings()
        email = EmailMessage()
        email["Subject"] = f"[Ledgerly] {message.title}"
        email["From"] = s.smtp_from
        email["To"] = destination
        link = f"\n\nOpen Ledgerly: {s.app_url}{message.link}" if message.link else ""
        email.set_content(f"{message.body}{link}\n\n— Ledgerly alerts. Manage alerts in Settings → Alerts.")
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
                if s.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(email)
            return DeliveryResult("sent", self.name)
        except (OSError, smtplib.SMTPException) as exc:
            return DeliveryResult("failed", self.name, f"{type(exc).__name__}: {exc}"[:500])


class ConsoleEmailProvider:
    """Used when SMTP_HOST is not configured: the email is written to the log, not sent."""

    name = "console"

    def send(self, destination: str, message: Message) -> DeliveryResult:
        log.info("EMAIL (not sent, SMTP not configured) to=%s subject=%s", mask(destination), message.title)
        return DeliveryResult("logged", self.name, "SMTP is not configured; email written to the server log only")


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


class UnavailablePushProvider:
    name = "none"

    def send(self, destination: str, message: Message) -> DeliveryResult:
        return DeliveryResult("skipped", self.name, "Push notifications are not implemented yet")


def provider_for(channel: str) -> NotificationProvider:
    s = get_settings()
    if channel == "email":
        return SMTPEmailProvider() if s.email_configured else ConsoleEmailProvider()
    if channel == "sms":
        return MockSMSProvider()  # real adapters (e.g. Twilio, MSG91) plug in here – see docs/notifications.md
    if channel == "whatsapp":
        return MockWhatsAppProvider()
    return UnavailablePushProvider()


def destination_for(channel: str, user: User, settings: UserSettings) -> str:
    if channel == "email":
        return settings.contact_email or user.email
    if channel == "sms":
        return settings.contact_phone
    if channel == "whatsapp":
        return settings.whatsapp_number or settings.contact_phone
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
        if not destination and channel != "push":
            deliveries.append(NotificationDelivery(user_id=user.id, alert_event_id=event.id, channel=channel, status="skipped", error=f"No {channel} destination configured in Settings"))
            continue
        deliveries.append(NotificationDelivery(user_id=user.id, alert_event_id=event.id, notification_id=notification.id if notification else None, channel=channel, destination=mask(destination), status="queued"))
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
    provider = provider_for(delivery.channel)
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
