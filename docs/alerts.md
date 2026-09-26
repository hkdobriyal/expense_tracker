# Alert & automation engine

`backend/app/services/alerts.py`. A rule is: **WHEN** `metric(params) operator threshold` **THEN** notify `channels`.

## Metrics

| Kind | Metric | Params | Unit |
|---|---|---|---|
| state | `budget_usage` | budget (or any) | % |
| state | `category_spending` | category, period day/week/month | ₹ |
| state | `total_spending` | period | ₹ |
| state | `savings_rate` | – (this month) | % |
| state | `account_balance` | account (or any cash/bank) | ₹ |
| state | `bill_due_within` | – | days (0 = due today) |
| state | `bill_overdue` | – | days overdue |
| state | `subscription_renewal` | – | days |
| state | `goal_progress` | goal (or any) | % milestone |
| state | `goal_behind_schedule` | goal | percentage points behind a linear plan |
| state | `expected_income_missing` | income category, day of month | – |
| event | `large_transaction` | – | ₹ |
| event | `unusual_transaction` | – | × median of the category over 90 days (≥5 samples) |
| event | `new_merchant`, `duplicate_transaction`, `refund_received`, `salary_detected` | – | – |
| event | `subscription_price_changed`, `sync_failed` | – | emitted by the subscription and sync services |

## When rules run

- **After every ledger change** (create/edit/delete/import/sync/bill paid), in the same request, so in-app
  notifications appear immediately.
- **Every 10 minutes in the worker**, for date-driven conditions (a bill becoming due) with no browser open.
- `POST /api/alerts/evaluate` runs them on demand. `POST /api/alerts/rules/{id}/test` is a dry run that sends nothing.

## Cooldowns

| Policy | Behaviour |
|---|---|
| `once_per_threshold` (default for state) | Once per period (e.g. once per budget month). Period-less metrics like balance fire once per *episode*: the balance must recover above the threshold before it can fire again |
| `once_per_day` | At most once per calendar day while the condition holds |
| `cooldown` | At most once every *N* minutes |
| `every_event` (default for events) | Every matching transaction |

Each firing writes an `AlertEvent` with a unique `dedupe_key`, e.g. `r12:budget:3:2026-09-01`. That makes
evaluation idempotent, even when the API and worker evaluate concurrently.

## Worked example (from the brief, covered by `tests/test_alerts.py`)

Food budget ₹500, existing spend ₹390 (78%, no alert). Add ₹20 → ₹410 → **82%** ≥ 80%, so the rule fires:
an in-app notification *"You have used 82% of your Food budget (₹410 of ₹500)."*, plus an email delivery
queued if email is enabled. A further ₹30 the same month doesn't re-alert. The next month it can fire again.

## Defaults

A new user gets: bill due within 3 days, bill overdue, subscription renewing within 3 days, and bank sync
failed. Creating a budget can add threshold rules (e.g. 80% and 100%) in one step.
