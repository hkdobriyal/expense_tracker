# Ledgerly – personal finance, local-first

A personal finance and expense tracker you run on your own machine: accounts, transactions, budgets, goals,
bills, subscriptions, analytics, cash flow, net worth, statement import, bank-sync architecture, and a rule-based
alert engine with in-app and email notifications. Built for India (INR, UPI, Indian bank statements and SMS),
with multi-currency support. Every number on screen is calculated from your data. There are no hard-coded or
random values.

It is also a learning project: the code is small enough to read end to end, and `docs/` explains the decisions.

## Stack (all free & open source)

| Layer | Choice | Why |
|---|---|---|
| API | **FastAPI** + Pydantic | Kept from v1; typed, fast, auto-generated docs at `/api/docs` |
| Database | **SQLite** by default, **PostgreSQL** via `DATABASE_URL` | Zero setup today; portable types so Postgres is a config change |
| ORM / migrations | **SQLAlchemy 2** + **Alembic** | Real migrations, constraints, indexes, transactions |
| Background jobs | DB-backed queue + `python -m app.worker` | No Redis needed; survives restarts; easy to inspect |
| Frontend | **React 18** + **Vite** | Kept from v1 |
| Data fetching | **TanStack Query** | Every write refreshes all derived numbers |
| Charts / icons / motion / 3D | **Recharts**, **Lucide**, **Framer Motion**, **React Three Fiber** | 3D only in the dashboard hero and login |
| Tests | **pytest** (58 API tests), **Playwright** (E2E in your local Edge) | |

## Quick start (Windows)

Prerequisites: Python 3.11+ and Node 20+.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

This creates `backend\.venv`, installs dependencies, and opens three windows: the API (:8000), the worker, and
the web app at **http://localhost:5173**. The first account you create becomes the owner. Registration then
closes, because this is a single-user installation. To look around without entering data, click
**Try the demo workspace**.

Manual start:

```powershell
cd backend;  python -m venv .venv;  .\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000     # terminal 1
.\.venv\Scripts\python -m app.worker                                   # terminal 2
cd ..\frontend;  npm install;  npm run dev                             # terminal 3
```

**Where is my data?** By default it's in `%LOCALAPPDATA%\Ledgerly`: the SQLite database, uploaded receipts,
and generated keys. This is deliberately outside the OneDrive-synced source folder. You can override it with
`DATA_DIR`.

## Configuration

Copy `backend/.env.example` to `backend/.env`. Every value is optional locally. See
[docs/local-development.md](docs/local-development.md).

## Tests

```powershell
cd backend;  .\.venv\Scripts\python -m pytest            # 58 API tests, ~20 s
cd frontend; npx playwright test                         # needs the stack running on a throwaway DATA_DIR
```

## What works, and what needs something from you

| Feature | Status |
|---|---|
| Accounts, transactions (expense/income/transfer/refund/adjustment/investment), splits, tags, receipts | ✅ |
| Search, filters, pagination, bulk actions, review queue, command palette (Ctrl K), quick add (N) | ✅ |
| Categories, smart rules (contains/equals/starts/ends/regex, amount, account), merchant learning | ✅ |
| Budgets (weekly/monthly/yearly/custom), goals, bills, subscriptions (+ detection), recurring | ✅ |
| Dashboard, analytics, cash flow, net worth history, deterministic insights | ✅ |
| Statement import: CSV, XLSX, OFX/QFX, text PDFs, with preview, mapping, dedupe and undo | ✅ |
| Bank SMS parsing: paste, or forward via an authenticated webhook | ✅ |
| Alert engine: 19 metrics, cooldowns, per-rule channels, history with delivery status | ✅ |
| In-app notifications | ✅ |
| Email | ✅ via any SMTP server (Mailpit locally); without SMTP, emails are logged, not sent |
| Reports: CSV / Excel / print-to-PDF; JSON backup & restore (reads v1 backups too) | ✅ |
| Demo mode (isolated workspace + sandbox bank through the real sync pipeline) | ✅ |
| **Live bank sync (India)** | ⛔ Needs an RBI Account Aggregator FIU licence. See [docs/bank-integration.md](docs/bank-integration.md) |
| SMS / WhatsApp delivery | 🟡 Mock adapters. Real providers cost money; see [docs/costs.md](docs/costs.md) |
| Push notifications, OCR, AI assistant | 🟡 Not built yet. Architecture leaves room ([docs/architecture.md](docs/architecture.md#roadmap)) |

## Documentation

- [docs/audit.md](docs/audit.md): what the v1 app contained and what was kept, improved, replaced or removed
- [docs/architecture.md](docs/architecture.md): layers, the financial engine, decisions and trade-offs
- [docs/database.md](docs/database.md): schema, money representation, migrations, SQLite vs PostgreSQL
- [docs/alerts.md](docs/alerts.md) · [docs/notifications.md](docs/notifications.md)
- [docs/bank-integration.md](docs/bank-integration.md): provider interface, sync pipeline, India options
- [docs/security.md](docs/security.md) · [docs/costs.md](docs/costs.md)
- [docs/local-development.md](docs/local-development.md) · [docs/deployment.md](docs/deployment.md)
