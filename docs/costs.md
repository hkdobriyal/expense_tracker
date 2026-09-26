# Costs

Current setup: **₹0.** Nothing is purchased or signed up for. Prices below change often, so treat them as
"may cost money" signals and check the provider's current pricing before relying on them.

| Service | Purpose | Open source | Free option in use | Possible cost later | Free alternative |
|---|---|---|---|---|---|
| Database | Storage | SQLite, PostgreSQL: yes | SQLite file | Managed Postgres hosting beyond free tiers | Self-hosted Postgres (Podman/native) |
| Job queue | Background work | Own code | DB table + worker | – | – |
| Email | Alert emails | Mailpit: yes | Console log / Mailpit locally | Transactional email services beyond free tiers | Your existing mailbox via SMTP app password |
| SMS | Alert texts | – | **Mock adapter** | Per message. India also requires TRAI DLT registration of sender ID and templates | Email or in-app instead |
| WhatsApp | Alert messages | – | **Mock adapter** | Business Platform charges per template message (varies by country and category) | In-app / email |
| Push | Browser push | Web Push standard | Not built | Free when self-hosted (VAPID) | – |
| Bank data (India) | Live sync | – | Statement import + SMS | AA/FIU onboarding and per-fetch fees; requires a regulated entity | Import / SMS (free) |
| FX rates | Multi-currency | – | Manual entry | Paid tiers of rate APIs | Free public reference rates (future adapter) |
| OCR | Receipts | Tesseract: yes | Not built | Cloud OCR APIs per page | Tesseract locally |
| AI assistant | Q&A over data | Ollama/models: yes | Not built | Cloud LLM APIs per token | Ollama + an open model locally |
| Containers | Local infra | Podman: yes | Not required | **Docker Desktop requires a paid subscription at companies with >250 employees or large revenue**, which matters on a work laptop | Podman Desktop, or no containers (default) |
| Hosting | Access from other devices | – | Your own PC | VPS / PaaS beyond free tiers | Keep it local, or use Tailscale-style private access |
| Domain | Public URL | – | None | Yearly registration | Not needed for personal use |

Nothing in the core app depends on a paid service.
