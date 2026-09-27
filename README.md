# Hisaab – personal finance by Hemant Kumar

*Hisaab* (हिसाब) means "the accounts". It's a private, local-first personal finance app: accounts,
transactions, budgets, goals, bills, subscriptions, analytics, cash flow and net worth. On top of that it
imports statements in any common format, categorises transactions with on-device ML, has an optional local
AI assistant, and sends alerts in-app, by email and as browser push notifications. Built for India (INR, UPI,
Indian bank statements and SMS), with multi-currency support. Every number on screen is calculated from your
data; there are no hard-coded or random values.

It's also a learning project: the code is small enough to read end to end, and `docs/` explains every decision.

## Quick start (Windows)

Prerequisites: Python 3.11+ and Node 20+. No admin rights needed.

```powershell
# 1. Backend dependencies (once)
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Frontend dependencies (once)
cd ..\frontend
npm install
```

Run it in three terminals. Activating the venv isn't needed, so no PowerShell scripts run:

```powershell
cd backend;  .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000   # API
cd backend;  .\.venv\Scripts\python.exe -m app.worker                                  # background worker
cd frontend; npm run dev                                                                # web app
```

Open **http://localhost:5173**, then click **Get started** to create your account, or **Explore the demo**
to look around with sample data. (`scripts\dev.ps1` does all of this in one go if your machine allows
PowerShell scripts.)

Your data lives in `%LOCALAPPDATA%\Hisaab` (or `…\Ledgerly` if you used the earlier version), outside the
OneDrive folder. Override it with `DATA_DIR`.

## Configuration: `backend/.env`

`backend/.env` (already created on this machine; `backend/.env.example` is the template in git) has **dummy SMTP values**. Replace them to get real emails:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop     # a Gmail *App Password* (Google Account → Security → App passwords)
SMTP_FROM=Hisaab <you@gmail.com>
```

While the placeholders are still there, email counts as "not configured". Emails, including password-reset
links, are then written to the API console window instead, and are never reported as sent. After editing,
restart the API and worker, then use **Settings → Notifications → Send test email**.

**Push notifications** need no configuration: **Settings → Notifications → Enable push notifications**,
then **Send test push**. Push works on `http://localhost`; any other address needs HTTPS.

**Optional local AI**: install Ollama and run `ollama pull qwen2.5:3b`. Everything else works without it.
See [docs/ai.md](docs/ai.md).

## Features

| Area | What you get |
|---|---|
| Accounts | Sign up, sign in with remember-me, show/hide password, strength meter, forgot/reset password by email, email verification, session management, audit log |
| Money | Accounts, transactions (expense/income/transfer/refund/adjustment/investment), splits, tags, receipts, search & filters, bulk actions, review queue, command palette (Ctrl K), quick add (N) |
| Import | CSV, TSV, TXT, XLS, XLSX, OFX/QFX, JSON, DOCX, PDF (incl. password-protected and scanned), photos; preview, column mapping, duplicate detection, undo; bank SMS paste or webhook |
| AI / ML | Narration entity extraction (UPI id, reference, payee, mode…), on-device ML categoriser that learns from you, live suggestions while typing, OCR, optional local LLM for tricky items, "Ask your money" assistant |
| Planning | Budgets (weekly/monthly/yearly/custom) with pace, goals, bills, subscriptions (+ auto-detection), recurring transactions |
| Insights | Dashboard, analytics, cash flow, net worth history, deterministic insights, reports (CSV / Excel / print-to-PDF) |
| Alerts | 19 metrics, cooldown policies, per-rule channels, history with per-channel delivery status; in-app (live), email, browser push |
| Look & feel | Animated landing page with 3D and scroll effects, 3D tilt cards, dark/light themes, reduced-motion support, mobile layout, installable PWA |

## Honest limits

| Item | Status |
|---|---|
| Live bank sync (India) | ⛔ Needs an RBI Account Aggregator FIU licence. Use statement import or SMS ([docs/bank-integration.md](docs/bank-integration.md)) |
| SMS / WhatsApp delivery | 🟡 Mock adapters: real providers cost money ([docs/costs.md](docs/costs.md)) |
| Local LLM | 🟡 Optional; needs Ollama installed (may need IT approval on a work laptop) |
| PostgreSQL | 🟡 Supported by config; tests run on SQLite |

## Tests

```powershell
cd backend;  .\.venv\Scripts\python.exe -m pytest -q     # 86 API tests
cd frontend; npx playwright test                         # 5 end-to-end tests, run against the dev stack with an empty DATA_DIR
```

## Documentation

[audit](docs/audit.md) · [architecture](docs/architecture.md) · [database](docs/database.md) ·
[AI & ML](docs/ai.md) · [alerts](docs/alerts.md) · [notifications](docs/notifications.md) ·
[bank integration](docs/bank-integration.md) · [security](docs/security.md) · [costs](docs/costs.md) ·
[local development](docs/local-development.md) · [deployment](docs/deployment.md)
