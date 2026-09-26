# Local development

## Everything free, no containers

| Piece | Local setup |
|---|---|
| Database | SQLite in `%LOCALAPPDATA%\Ledgerly` (or `DATA_DIR`) |
| Worker | `python -m app.worker` |
| Email | Console log by default; Mailpit for a real inbox (see notifications.md) |
| SMS / WhatsApp | Mock adapters |
| Bank | Sandbox provider in Demo mode |

`scripts\dev.ps1` starts the API, worker and Vite. `scripts\dev.ps1 -DataDir C:\temp\ledgerly-test` uses a
throwaway database, which is useful for E2E tests or experiments.

## With PostgreSQL + Mailpit (Podman or Docker)

```powershell
podman compose up --build      # or: docker compose up --build
```

This gives PostgreSQL :5432, Mailpit :8025, API :8000, worker, and web :5173. (Not verified on this machine:
neither Docker nor Podman is installed.)

## Useful URLs

- App: http://localhost:5173
- API docs (OpenAPI): http://localhost:8000/api/docs
- Health: http://localhost:8000/api/health (database, worker heartbeat, email mode)

## Tests

```powershell
cd backend; .\.venv\Scripts\python -m pytest -q
```

Each test gets a fresh SQLite file and uses `JOBS_INLINE=true`, so deliveries run synchronously.

End to end (Playwright drives your installed Edge; `E2E_BROWSER_CHANNEL=chrome` for Chrome):

```powershell
scripts\dev.ps1 -DataDir C:\temp\ledgerly-e2e     # must be an EMPTY data dir: the test registers the owner
cd frontend; npx playwright test
```

## Adding a feature: the usual path

1. Model change → `alembic revision --autogenerate` → review → `upgrade head` → `alembic check`.
2. Business logic in `services/` (use `ledger.py` for any totals; never re-sum in a router).
3. Endpoint in `routers/`; ownership via `get_owned()`.
4. Test in `backend/tests/`.
5. UI page/component; writes go through `useLedgerMutation` so every number refreshes.
