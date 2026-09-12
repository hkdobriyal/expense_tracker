# Ledgerly Personal Finance OS

A privacy-first, local-first personal finance workspace for Indian expenses and investments.

## What is implemented

- INR base currency with `en-IN` formatting
- Expenses, income, investments, transfers-ready transaction model
- Indian categories, UPI/cards/cash/net banking payment methods
- Merchants, notes, dates, recurring transaction flag
- Dashboard metrics, category analytics, search, filters, animated UI, and 3D visual
- Accounts, budgets, goals, bills, investments view, and dashboard summary APIs
- CSV transaction export and complete JSON backup
- SQLite persistence with automatic schema migration
- FastAPI OpenAPI documentation

## Local-first architecture decision

The supplied architecture proposes PostgreSQL, Valkey, workers, OCR, Ollama, and Docker. They are intentionally not mandatory in the current personal build:

- SQLite is the zero-setup local database. It keeps the app free and private on Windows.
- FastAPI and Pydantic provide the API and validation boundary.
- React, Vite, Framer Motion, and React Three Fiber provide the interactive UI.
- External bank sync, cloud AI, cloud analytics, and paid services are not used.
- The backend entities are separated enough to migrate to SQLAlchemy/PostgreSQL when multi-user or family deployment becomes necessary.

## Run

Backend:

```powershell
cd backend
.\myvenv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Backups

Use Settings in the UI, or download directly:

- `http://localhost:8000/transactions/export.csv`
- `http://localhost:8000/backup.json`

Keep backups outside the repository if the data is sensitive.

## Deliberate next phases

Authentication, PostgreSQL/SQLAlchemy migration, import preview and duplicate detection, receipt/document storage, portfolio holdings and valuations, offline IndexedDB sync, PWA packaging, and optional local Ollama/OCR adapters should be added only when their workflows are needed. They are not faked as complete features in this personal build.
