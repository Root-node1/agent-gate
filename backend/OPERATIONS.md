# Backend operations

## Environment files

- Local: `config.settings.dev`, values from `backend/.env`.
- Tests: `config.settings.test`; SQLite unless `TEST_DATABASE_URL` is set. `manage.py test` selects it automatically.
- Production: `config.settings.prod`; requires `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` and a PostgreSQL 17 `DATABASE_URL`.

## Audit data reset

The chain starts with the first event written after the chain code is deployed. Existing demo rows are unchained, so reset the demo databases before using the demo. The data contains no live credentials and the old keys are revoked. Do not ship a migration that disables the audit triggers to rewrite rows.

### Local SQLite

```bash
cd backend
export DATABASE_URL=          # ignore a Neon URL in .env for this reset
rm db.sqlite3
python manage.py migrate
python manage.py seed_demo
python manage.py verify_audit
```

### Neon

Take an off-server copy first. The demo data is disposable, but the dump is the fallback if a demo recording needs the old events:

```bash
pg_dump "$DATABASE_URL" --format=custom --file=agentgate-before-reset.dump
```

Then, as the database owner, drop and recreate the schema (the append-only triggers intentionally block TRUNCATE and DELETE):

```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

Run migrations from the Contabo host or a trusted workstation using the **direct** Neon URL:

```bash
export DATABASE_URL='postgresql://...direct.../neondb?sslmode=require'
python manage.py migrate
python manage.py createcachetable
python manage.py seed_demo
python manage.py verify_audit
```

If the reset happens after real audit events exist, stop and take a normal backup instead. Resetting destroys the chain.

## Audit chain check

```bash
python manage.py verify_audit
```

The command walks each organization's events in id order, recomputes every hash from the stored canonical payload, and exits non-zero at the first mismatch.

Keep a periodic off-server `pg_dump` of the audit tables. The chain is tamper-evident, not tamper-proof, unless the head hash is anchored outside Neon.

## Production deploy checklist

1. Set `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and the direct Neon `DATABASE_URL`.
2. Run `python manage.py migrate` and `python manage.py createcachetable`.
3. Run `python manage.py collectstatic --noinput`; Caddy serves `backend/staticfiles` and proxies `/healthz` and `/readyz` over plain HTTP to gunicorn.
4. Keep `/admin/` off the public route or behind an IP allowlist.
5. Configure Caddy with a 64 KiB request body limit and HTTPS. `SECURE_SSL_REDIRECT` is on; the health endpoints are exempt. Caddy's health check must send a `Host` header that is listed in `DJANGO_ALLOWED_HOSTS`.
6. Use the direct Neon URL for the Procrastinate worker. Use the pooled URL for web only after testing it with server-side cursors disabled.
7. On Neon's free tier, disable scale-to-zero before a demo and expect a cold start after idle periods.
8. Run `python manage.py verify_audit` after the first requests.

## Demo reset

```bash
python manage.py seed_demo
```

The command suspends the active `demo-*` agent, creates a fresh agent and policy, and appends a `demo.reset` audit event. It deletes no rows, because audit events use `PROTECT` foreign keys.
