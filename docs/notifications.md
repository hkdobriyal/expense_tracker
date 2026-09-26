# Notifications

`backend/app/services/notifications.py`. Every channel implements one interface:

```python
class NotificationProvider(Protocol):
    name: str
    def send(self, destination: str, message: Message) -> DeliveryResult: ...
```

| Channel | Provider now | Delivery status recorded |
|---|---|---|
| In-app | stored in `notifications` | `sent` |
| Email | `SMTPEmailProvider` when `SMTP_HOST` is set, otherwise `ConsoleEmailProvider` | `sent` / `failed`, or `logged` (not sent) |
| SMS | `MockSMSProvider` | `mocked` (nothing sent) |
| WhatsApp | `MockWhatsAppProvider` | `mocked` (nothing sent) |
| Push | not implemented | `skipped` |

Statuses are deliberately honest: the UI shows "logged (SMTP not set)" or "mock", never a fake "sent".

## Which channels are used

1. The rule's own channel list, or, when it says "use my defaults", the per-category matrix in
   Settings → Notifications.
2. Filtered by the **master switch** for each channel.
3. Skipped with a reason if there's no destination (for example, no phone number).

In-app notifications are created immediately. Other channels become `deliver_notification` jobs that the
worker sends, retrying with exponential backoff (30 s, 60 s, 120 s…, up to 5 attempts). Settings → Alerts →
**Send test notification** exercises every enabled channel.

## Email locally, for free: Mailpit

1. Download the single binary from the Mailpit GitHub releases (or `podman run -p 8025:8025 -p 1025:1025 axllent/mailpit`).
2. Set `SMTP_HOST=localhost` and `SMTP_PORT=1025` in `backend/.env`, then restart the API and worker.
3. Open http://localhost:8025 to see every email Ledgerly sends.

For real email, point the SMTP variables at any provider (your mail host, or a Gmail/Outlook app password).

## Adding a real SMS or WhatsApp provider

Implement `send()` in a new class (for example `Msg91SMSProvider`) and return it from `provider_for("sms")`
when `SMS_PROVIDER=msg91`. Keep API keys in `.env`. Check the costs and rules first; see [costs.md](costs.md).
