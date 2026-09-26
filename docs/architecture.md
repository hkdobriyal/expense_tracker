# Architecture

```
Browser (React SPA) ──/api──► FastAPI routers ──► services (financial engine) ──► SQLAlchemy ──► SQLite / PostgreSQL
                                   ▲                         │
                                   │                         └─► jobs table ◄── worker (python -m app.worker)
                          session cookie + CSRF                                   ├─ email/SMS deliveries
                                                                                  ├─ scheduled alert evaluation
                                                                                  ├─ recurring transactions
                                                                                  ├─ bank auto-sync
                                                                                  └─ daily net-worth snapshot
```

A **modular monolith**: one API process plus one worker process sharing one database. Nothing here needs
microservices, Kubernetes or a message broker. Each module has a clear boundary, so any of them can be split
out later.

## Backend layout (`backend/app`)

| Path | Responsibility |
|---|---|
| `config.py` | Settings from env / `.env`; generates and persists keys in `DATA_DIR` |
| `db.py`, `models.py` | Engine, `UTCDateTime`, the 31 tables |
| `money.py` | Minor-unit conversion, INR formatting, FX conversion. **No floats.** |
| `security.py`, `deps.py` | scrypt passwords, session tokens, CSRF, Fernet, rate limiting, `get_owned()` |
| `routers/*` | HTTP layer only: validation, ownership, calling services, serialising |
| `services/ledger.py` | **The financial engine**: balances, totals, series, breakdowns, cash flow |
| `services/transactions.py` | The single write path: validation, FX, fingerprints, splits, rules |
| `services/budgets / goals / bills / subscriptions / recurring / networth / insights / reports` | Planning and insight logic built on the ledger |
| `services/alerts.py`, `notifications.py`, `jobs.py` | Rule engine, channel providers, job queue |
| `services/importers.py`, `imports.py`, `sms_parser.py` | Statement parsing and the import workflow |
| `services/banking.py`, `demo.py` | Bank provider interface, sync pipeline, sandbox + demo workspace |
| `worker.py` | Background loop |

## One source of truth

Every derived number comes from `services/ledger.py`. That includes the dashboard, budget progress, alert
values, reports and insights. For example, `spent_in_categories()` powers budgets, category alerts and the
budget report, so they cannot disagree. On the frontend, every successful write invalidates all queries
(`useLedgerMutation`), so each screen refetches the numbers it shows.

### Definitions (base currency)

| Term | Definition |
|---|---|
| income | sum of `income` transactions |
| expenses | `expense` − `refund` (refunds reduce the category they belong to) |
| invested | `investment` transactions (SIPs, stocks, FDs funded from an account) |
| savings | income − expenses (investing counts as saving) |
| net cash flow | income − expenses − invested (actual change in cash) |
| savings rate | savings ÷ income |
| transfers | excluded from all of the above (credit-card payments, moving money to savings) |
| account balance | opening balance + signed transactions (+ incoming transfers), in the account's currency |
| net worth | Σ asset balances − Σ amounts owed on liabilities, each converted with the latest known rate |

## Key decisions

| Decision | Alternatives | Why | Trade-off |
|---|---|---|---|
| Integer minor units (paise) | `NUMERIC` columns, floats | Exact on SQLite *and* Postgres; trivially correct sums | Must divide only for display; per-currency exponent table |
| Store `base_amount_minor` at write time | Convert at read time | Aggregations are plain `SUM`s; history doesn't shift when rates change | Changing base currency is blocked once data exists |
| SQLite default, Postgres-ready | Postgres only | Zero setup on a work laptop without Docker | Single writer; `SKIP LOCKED` only on Postgres |
| DB-backed job queue | Celery / BullMQ + Redis | No extra service; inspectable; retries with backoff | Polling (15 s); fine for personal volumes |
| Cookie session + CSRF token | JWT in localStorage | HttpOnly cookie can't be read by injected JS; server-side revocation | Needs the CSRF header on writes |
| Demo = separate user | Flag on rows | Isolation reuses the same `user_id` filtering; no risk of mixing | Entering demo signs you out |
| Keep React + JS, add TanStack Query/Router | Rewrite in Next.js/TypeScript | Existing stack was fine; the brief says don't swap without reason | No static types yet (see roadmap) |
| Plain CSS design tokens | Tailwind / shadcn | v1 already used hand-written CSS; one small system, dark + light | More CSS to maintain by hand |

## Alerts in one paragraph

State metrics (budget usage, balances, days to a bill) are re-evaluated after every ledger change and every
10 minutes by the worker. Event metrics (large or unusual transaction, new merchant, refund, salary) run once
per new transaction. Cooldown policies and a unique `dedupe_key` per firing make evaluation idempotent. See
[alerts.md](alerts.md).

## Roadmap

- **TypeScript** for the frontend (Vite supports it incrementally, file by file).
- **Push notifications** (Web Push with VAPID keys is free and self-hostable) behind the existing provider interface.
- **Receipt OCR** with Tesseract (open source), run locally on attachments.
- **Optional AI assistant**: a tool-calling assistant over the ledger services, preferring a local model through
  Ollama. The core app never depends on it.
- **Live bank sync** once an Account Aggregator route is available (see bank-integration.md).
- Automatic FX rates through a free rate source, into the existing `exchange_rates` table.
