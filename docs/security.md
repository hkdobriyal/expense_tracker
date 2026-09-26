# Security

| Control | Implementation |
|---|---|
| Passwords | scrypt (N=2¹⁵, r=8), random salt, constant-time compare; ≥10 chars with mixed case and a digit |
| Sessions | 256-bit random token in an **HttpOnly, SameSite=Lax** cookie (`Secure` when `APP_URL` is https). Only an HMAC of the token is stored, so a stolen DB can't be replayed. Sessions are listable and revocable; changing the password signs out other sessions |
| CSRF | Per-session token returned at login; every non-GET request must send `X-CSRF-Token` |
| Authorisation | Every query filters on `user_id`; `get_owned()` returns 404 for foreign rows (tested in `test_users_cannot_see_each_others_data`) |
| Registration | Only the first user can register unless `ALLOW_REGISTRATION=true` |
| Rate limits | Login (5 per email / 10 per IP per 5 min), registration, demo resets, Sync Now, SMS webhook |
| Input validation | Pydantic with `extra="forbid"`; money parsed as Decimal and rejected (not rounded) when invalid; regex rules compiled before saving |
| Uploads | Size limit; type decided by **magic bytes** (JPG/PNG/PDF only), not the filename; random storage names outside the web root; downloads are authenticated with `nosniff` |
| Secrets | Keys generated into `DATA_DIR` with exclusive create, never in git; bank credentials Fernet-encrypted and never serialised; PDF statement passwords are used once and not stored |
| SMS webhook | Separate bearer token (stored hashed; shown once; revocable) |
| Headers / CORS | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store` on API responses; CORS limited to `APP_URL` |
| Logging | Audit log for logins, failed logins, settings, bank connect/sync/disconnect, imports, bulk deletes, restores and account deletion; keys like `password` and `token` are stripped; request bodies are never logged |
| Destructive actions | Restore needs `confirm=true`; deleting an account with transactions needs explicit confirmation (archive is offered); account deletion needs the password |

## Known limits

- Rate limiting is in-memory, i.e. per process. Use Redis/Valkey if you ever run several API workers.
- There's no 2FA yet. For access beyond localhost, put the app behind HTTPS (see deployment.md).
- The SQLite file isn't encrypted at rest; rely on Windows account and disk encryption (BitLocker).
