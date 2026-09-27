"""Outgoing email over plain SMTP (works with Gmail/Outlook app passwords, any mail host, or Mailpit).

When SMTP is not configured (or still has the placeholder values from
.env.example) messages are written to the server log instead and reported as
"logged" – never as "sent".
"""

from __future__ import annotations

import html
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from ..config import get_settings
from ..security import mask

log = logging.getLogger("hisaab.email")


@dataclass
class EmailResult:
    status: str  # sent|failed|logged
    provider: str
    error: str | None = None


def _html(title: str, body: str, action_url: str | None, action_label: str | None, footer: str) -> str:
    s = get_settings()
    paragraphs = "".join(f"<p style='margin:0 0 14px;line-height:1.55'>{html.escape(p)}</p>" for p in body.split("\n\n") if p.strip())
    button = (
        f"<p style='margin:22px 0'><a href='{html.escape(action_url)}' style='background:#2bb7d9;color:#04202c;padding:12px 20px;"
        f"border-radius:10px;text-decoration:none;font-weight:700;display:inline-block'>{html.escape(action_label or 'Open')}</a></p>"
        f"<p style='font-size:12px;color:#6b7a8c;word-break:break-all'>{html.escape(action_url)}</p>"
        if action_url else ""
    )
    return f"""<!doctype html><html><body style="margin:0;background:#eef3f8;font-family:Segoe UI,Arial,sans-serif;color:#0e1b2c">
<div style="max-width:560px;margin:0 auto;padding:28px 16px">
  <div style="font-weight:800;font-size:20px;margin-bottom:14px">&#8377; {html.escape(s.app_name)}</div>
  <div style="background:#fff;border-radius:16px;padding:26px;border:1px solid #dde5ef">
    <h1 style="font-size:20px;margin:0 0 14px">{html.escape(title)}</h1>
    {paragraphs}{button}
  </div>
  <p style="font-size:12px;color:#6b7a8c;margin-top:16px">{html.escape(footer)}</p>
</div></body></html>"""


def send_email(to: str, subject: str, body: str, action_url: str | None = None, action_label: str | None = None,
               footer: str | None = None) -> EmailResult:
    s = get_settings()
    footer = footer or f"Sent by {s.app_name}, your personal finance app. You can change notification settings in Settings → Notifications."
    if not s.email_configured:
        link = f" | link: {action_url}" if action_url else ""
        log.warning("EMAIL NOT SENT (SMTP not configured) to=%s subject=%r%s", mask(to), subject, link)
        return EmailResult("logged", "console", "SMTP is not configured – see backend/.env; the email was written to the server log")

    msg = EmailMessage()
    msg["Subject"] = f"{subject} · {s.app_name}"
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="hisaab.local")
    text = body + (f"\n\n{action_label or 'Open'}: {action_url}" if action_url else "") + f"\n\n— {footer}"
    msg.set_content(text)
    msg.add_alternative(_html(subject, body, action_url, action_label, footer), subtype="html")
    try:
        context = ssl.create_default_context()
        if s.smtp_ssl:
            server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20, context=context)
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
        with server:
            server.ehlo()
            if s.smtp_starttls and not s.smtp_ssl:
                server.starttls(context=context)
                server.ehlo()
            if s.smtp_user:
                server.login(s.smtp_user, s.smtp_password)
            server.send_message(msg)
        return EmailResult("sent", "smtp")
    except smtplib.SMTPAuthenticationError:
        return EmailResult("failed", "smtp", "SMTP login failed – check SMTP_USER / SMTP_PASSWORD (Gmail needs an App Password, not your normal password)")
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        return EmailResult("failed", "smtp", f"{type(exc).__name__}: {exc}"[:500])
