# Deployment

The recommended setup is **your own computer**: it's private and free. If you later want phone access,
choose one of these:

1. **Private network (simplest, still free):** run the stack on your PC and reach it over a private mesh VPN.
   No public exposure.
2. **Small server / VPS:** `docker compose up -d` (or Podman) with PostgreSQL, behind a reverse proxy with
   HTTPS (Caddy is free and handles certificates).

## Production checklist

- `APP_URL=https://your-host` (turns on `Secure` cookies; CORS follows it).
- Set `SECRET_KEY` and `ENCRYPTION_KEY` explicitly and back them up. Losing `ENCRYPTION_KEY` makes stored
  bank credentials unreadable.
- `DATABASE_URL` → PostgreSQL; schedule `pg_dump` backups.
- Build the frontend: `npm run build`, then serve `frontend/dist` from the reverse proxy and proxy `/api` to
  uvicorn (`--workers 1` while rate limiting is in-memory).
- Run `python -m app.worker` as a service (systemd, NSSM on Windows, or the compose `worker` service).
- Configure SMTP for email alerts.
- Keep `ALLOW_REGISTRATION=false`.

Nothing is tied to a particular vendor: any host that runs Python, Node (build only) and PostgreSQL works.
