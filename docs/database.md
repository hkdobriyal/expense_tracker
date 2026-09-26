# Database

## Money

- All amounts are `BIGINT` minor units (`amount_minor`, `opening_balance_minor`…). ₹1,234.50 is `123450`.
- `money.to_minor()` **rejects** extra precision (`"10.005"` in INR) instead of rounding silently.
- A transaction stores its amount in the **account's currency** plus `base_amount_minor` (converted to the
  user's base currency) and the `fx_rate` used. If you paid in a foreign currency on an INR card,
  `original_amount_minor` / `original_currency` record what was charged.
- Amounts are positive; the `type` gives the direction. Adjustments carry their own sign. This is enforced by
  a `CHECK` constraint.

## Main tables

| Group | Tables |
|---|---|
| Identity | `users`, `user_sessions`, `user_settings`, `audit_logs` |
| Ledger | `accounts`, `transactions`, `transaction_splits`, `transaction_tags`, `tags`, `categories` (2 levels), `merchants`, `attachments`, `categorization_rules`, `recurring_transactions`, `exchange_rates` |
| Planning | `budgets`, `goals`, `goal_contributions`, `bills`, `bill_payments`, `subscriptions` |
| Banking & import | `bank_connections` (credentials Fernet-encrypted), `sync_logs`, `import_jobs` |
| Alerts | `alert_rules`, `alert_events` (unique `user_id + dedupe_key`), `notifications`, `notification_deliveries` |
| System | `jobs`, `system_state` (worker heartbeat), `net_worth_snapshots` |

Every user-owned table has `user_id`. Routers fetch rows through `deps.get_owned()`, which returns **404**
for other users' rows, so a row's existence is never revealed. Transactions are indexed on
`(user_id, date)`, `(user_id, account_id, date)`, `(user_id, category_id)`, `(user_id, fingerprint)` and
`(user_id, external_id)`.

## Duplicate detection

`fingerprint = sha256(account | date | direction-signed amount | normalised raw description)`.
Statement imports use **count-based** matching: two identical ₹340 Swiggy orders on the same day in a file
only count as duplicates if two such rows already exist. Bank and OFX data also match on `external_id`
(FITID / provider id). Bank sync links a matching manual or imported row by setting its `external_id`
instead of creating a duplicate.

## Migrations

Alembic, in `backend/alembic/versions`. The API and worker run `alembic upgrade head` at start-up when
`AUTO_MIGRATE=true`. When you change a model:

```powershell
cd backend
.\.venv\Scripts\python -m alembic revision --autogenerate -m "describe the change"
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m alembic check      # verifies models and migrations match
```

`render_as_batch=True` lets `ALTER TABLE` migrations work on SQLite.

## SQLite → PostgreSQL

1. `pip install "psycopg[binary]"`
2. `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/ledgerly`
3. Start the API (migrations create the schema), then restore a JSON backup from the SQLite install
   (Settings → Data).

The job queue switches to `FOR UPDATE SKIP LOCKED` automatically on PostgreSQL. **Note:** the test suite runs
on SQLite. The schema uses only portable types, but PostgreSQL has not been exercised on this machine
(there's no Docker/Podman). Run the tests against Postgres once you have it.

## Backups

- **Portable:** Settings → Data → Download backup (JSON v2, references by name, safe across SQLite and Postgres).
- **Byte-for-byte:** stop the API and worker, then copy `%LOCALAPPDATA%\Ledgerly\ledgerly.sqlite3`, plus
  `encryption.key` (without it, stored bank credentials can't be decrypted).
