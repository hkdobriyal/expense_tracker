# Bank integration

## The honest situation in India

v1 presented an "RBI Account Aggregator" flow that was simulated end to end: any OTP worked, and fixed
sample transactions were written into the real ledger. That has been removed.

Real AA data access happens through a licensed AA, such as Setu or Finvu, and the party *requesting* data
must be a **Financial Information User (FIU)**: an entity regulated by RBI, SEBI, IRDAI or PFRDA. An
individual building a personal app generally can't onboard as an FIU. So for personal use today, the working
routes are:

1. **Statement import:** CSV / XLSX / OFX / PDF from net banking (Import page). The most reliable option.
2. **Bank SMS:** paste them, or forward automatically via the token-protected webhook (Settings → Integrations).

## What I need from you to build a live provider

| Item | Why | Where to get it |
|---|---|---|
| Which AA/aggregator, and confirmation that you (or an entity you control) can act as FIU | Without FIU status the API won't issue consents | Setu / Finvu / Onemoney onboarding teams |
| Sandbox credentials (`client_id`, `client_secret`, product instance id) | To call the sandbox | Their developer console after onboarding |
| API documentation for consent + FI data fetch | So the adapter matches the real contract instead of guessing | Provider docs portal |
| One sample FI data response (anonymised) | To write the normaliser and its tests | Sandbox |

`SetuAAProvider` is registered and shows as unavailable, with the reason, until those exist.

## Provider interface (`services/banking.py`)

```python
class BankProvider(Protocol):
    key: str; label: str; description: str; is_sandbox: bool
    def availability(self, user) -> tuple[bool, str]
    def institutions(self) -> list[dict]
    def start(self, conn, params) -> ConnectStep            # consent / redirect / account selection
    def list_accounts(self, conn) -> list[ProviderAccount]
    def fetch_transactions(self, conn, account_external_id, since, until) -> list[ProviderTransaction]
    def disconnect(self, conn) -> None
```

Tokens and consent ids go in `bank_connections.credentials_encrypted` (Fernet) and are never serialised to
the browser.

## Sync pipeline (`sync_connection`)

1. Check the provider is available for this user (the sandbox refuses non-demo users).
2. For each linked account, fetch from the last sync minus 7 days (or 90 days on the first sync).
3. Normalise each item into a `TransactionInput` through the same write path as manual entry.
4. Match on `external_id`: unchanged → **duplicate**; changed amount/date/text → **updated** (your category, tags
   and notes are kept).
5. Otherwise match on fingerprint against manual or imported rows → link them and count as a **duplicate**.
6. Insert the rest, **categorise** them (rules → merchant default → keyword hints), and flag them for review.
7. Store the bank-reported balance to show reconciliation against the computed balance.
8. Run alerts (`after_ledger_change`); balances and analytics are derived live from the ledger.
9. Write a `SyncLog` (fetched, imported, updated, duplicates, errors, message).
10. On failure, mark the connection `error`/`expired` and emit `sync_failed` to your alert rules.

The worker auto-syncs active connections not synced in 6 hours.

## Sandbox (Demo mode)

`DemoBankProvider` generates deterministic sample data, with the same ids on every run, which exercises dedupe.
It only works inside the isolated demo workspace (login screen → *Try the demo workspace*).
