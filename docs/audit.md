# v1 audit (September 2026)

This is what the repository contained before the rebuild, and what happened to each part.

## What v1 was

- **Backend:** FastAPI with raw `sqlite3`. Seven files, ~1,800 lines. Money was stored as `REAL` (float),
  with ad-hoc `ALTER TABLE` migrations at runtime. There was no authentication.
- **Frontend:** React 18 + Vite, a single 877-line `App.jsx` with all state in component state, Framer
  Motion, React Three Fiber, and an unused Tailwind setup.
- **No real data existed** (no SQLite file in the repo), so nothing needed migrating. v1 JSON backups can
  still be restored.

## Keep / improve / replace / remove

| Area | Verdict | Notes |
|---|---|---|
| FastAPI, React, Vite, Framer Motion, R3F | **Keep** | Modern and suitable, so the stack wasn't swapped |
| SMS parser (`parser.py`) | **Keep → improve** | Real and useful for India. Moved to `services/sms_parser.py`; refunds are now their own type; fixed "Electricity" being picked over the merchant BESCOM; its 7 cases are now pytest assertions |
| Statement parser | **Improve** | CSV/PDF logic reworked into a preview → map → validate → commit pipeline, plus XLSX and OFX/QFX, count-based dedupe, and undo |
| CSV export / JSON backup | **Improve** | Now per user, authenticated, portable (v2), and v1-compatible |
| Command palette, PWA shell | **Improve** | Palette searches the API; the service worker only registers in production |
| `database.py` / `crud.py` | **Replace** | SQLAlchemy models + Alembic; integer paise; constraints and indexes |
| Dashboard/analytics maths | **Replace** | Computed separately (and inconsistently) on client and server, e.g. "Accounts" total was opening balances only. Now one engine: `services/ledger.py` |
| `aa.py` "RBI Account Aggregator" | **Remove** | **Fake sync.** It accepted any 6-digit OTP, invented discovered accounts, and inserted 10 hard-coded transactions and fake balances (₹48,320.50 / ₹64,200) into the *real* database. "Live Setu" mode never called an API. Replaced by the provider interface in `services/banking.py` |
| `AccountAggregatorHub.jsx` | **Remove** | UI for the fake flow (pre-filled test phone `9876543210` and OTP `123456`) |
| `AutoSyncHub.jsx` | **Remove** | Dead code, never imported |
| `confetti.js`, `sound.js`, custom cursor | **Remove** | Decorative; `cursor: none` hurt accessibility |
| `axios`, `zustand`, `tailwindcss`, `canvas-confetti` | **Remove** | Unused or replaced by `fetch` / TanStack Query / plain CSS |
| `test_api.py` | **Remove** | A manual script against a running server; replaced by pytest |

## Security issues found in v1

1. No authentication or authorisation: anyone reaching port 8000 could read or delete everything.
2. `CORS: *` combined with `allow_credentials=True`.
3. `POST /sync/sms` was unauthenticated, so anyone on the LAN could inject transactions.
4. `POST /backup/restore` wiped all tables without confirmation or auth.
5. `POST /aa/config` accepted client secrets over the API and held them in memory.
6. f-string table names in SQL (limited to internal constants, but fragile).
7. Floats for money (`amount REAL`).

All of these are fixed; see [security.md](security.md).

## Dummy values, classified

| Where | What | Classification → action |
|---|---|---|
| `aa.py` | 10 sample narrations, fake balances, fake accounts | **Remove** (moved to an isolated *demo* sandbox provider, which is refused for real users) |
| `main.py /aa/fetch` | `opening_balance: 48320.50 / 64200 / 32150.75` | **Remove** |
| `AccountAggregatorHub.jsx` | FIP list duplicated in the UI, pre-filled OTP/phone | **Remove** |
| `AutoSyncHub.jsx` | 6 preset SMS with amounts | **Remove** (the same texts live on as **test fixtures**) |
| `crud.py` health score | Heuristic 50 ± 35 score and burn-rate fallback `total/len(rows)` | **Remove**: not a meaningful financial metric |
| `crud.py` | `payment_method or "UPI"` default in analytics | **Remove**: unknown stays unknown |
| `ui.jsx` | `healthScore \|\| 75` fallback | **Remove** |
| `App.jsx` | Account total = sum of opening balances | **Replace** with ledger balances |
| `App.jsx` | Profile card "H" and "Personal space" | **Replace** with the signed-in user |
| `ThreeDCore.jsx` | `Math.random()` particle positions | Decorative only → **replaced** with a deterministic distribution |
| `demo.py` / `DemoBankProvider` | Sample transactions | **Demo data**: isolated user, labelled everywhere |
