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

## Procrastinate background jobs

### Version

`procrastinate[django]==3.10.0` (pinned in `requirements.txt`).

### Database schema initialization

Procrastinate's Django integration (`procrastinate.contrib.django` in
`INSTALLED_APPS`) ships its own migrations under the `procrastinate` app
label. Schema is created automatically by:

```bash
python manage.py migrate
```

No separate schema bootstrap step is required. The core tables in 3.10.0 are:
`procrastinate_jobs`, `procrastinate_events`, `procrastinate_periodic_defers`,
`procrastinate_workers`.

### Worker startup

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod \
python manage.py procrastinate worker \
  -q smoke --listen-notify --delete-jobs=SUCCESSFUL
```

For one-shot mode (process all current jobs then exit, useful in CI):

```bash
python manage.py procrastinate worker -q smoke --no-listen-notify
```

Environment variables that override CLI defaults:

| Variable | Purpose |
|---|---|
| `PROCRASTINATE_WORKER_NAME` | Unique worker name (used in logs and `pg_locks`). |
| `PROCRASTINATE_WORKER_QUEUES` | Comma-separated queue list (defaults to task default). |
| `PROCRASTINATE_WORKER_CONCURRENCY` | Parallel jobs per worker (default 1). |
| `PROCRASTINATE_WORKER_WAIT` | `1` or `0`; set to `0` to exit after queue drains. |
| `PROCRASTINATE_WORKER_LISTEN_NOTIFY` | Set to `0` to disable LISTEN/NOTIFY polling. |
| `PROCRASTINATE_WORKER_SHUTDOWN_GRACEFUL_TIMEOUT` | Seconds to wait for in-flight jobs on SIGTERM. |
| `PROCRASTINATE_DATABASE_ALIAS` | Django DB alias for Procrastinate (defaults to `default`). |

### Required environment variables

- `DATABASE_URL` — direct PostgreSQL connection string. The worker must use the
  **direct** Neon URL (not the transaction pooler). LISTEN/NOTIFY does not work
  through a pooler such as PgBouncer. Web-tier requests may use the pooled URL
  with server-side cursors disabled.
- `DJANGO_SETTINGS_MODULE` — typically `config.settings.prod` in production.
- `PROCRASTINATE_DATABASE_ALIAS` — only needed if Procrastinate should use a
  different Django database alias than `default`.

### Local smoke-test procedure

```bash
export TEST_DATABASE_URL="postgresql://user:password@localhost:5432/agentgate_test"
python manage.py test tests.test_procrastinate_smoke -v 2
```

The smoke tests use `PostgresTransactionTestCase` (not `TestCase`) because
Procrastinate's `SELECT FOR UPDATE` inside the worker conflicts with
Django's transactional test isolation. If the `TEST_DATABASE_URL` is unset,
tests run on SQLite and the PostgreSQL-dependent tests are skipped.

### Periodic approval expiration

The `expire_approvals_periodic` task (`apps/background/tasks.py`) expires
overdue pending approvals on a ~60-second schedule. It delegates to the
existing, idempotent `apps.approvals.services.expire_due`, preserving its
`limit=1000` and row-level (`SELECT FOR UPDATE`) locking:

```python
@app.periodic(cron="*/1 * * * *", periodic_id="approval_expiry")
@app.task(
    queue="approvals",
    retry=RetryStrategy(max_attempts=3, wait=1),
    queueing_lock="approval_expiry",
)
def expire_approvals_periodic(timestamp: int) -> int:
    from apps.approvals.services import expire_due
    return expire_due()
```

The worker owns scheduling, not cron: each worker defers periodic occurrences
keyed by `periodic_id` + `defer_timestamp`, and the database deduplicates them,
so the same scheduled occurrence is deferred at most once even with multiple
workers.

#### Scheduling safety

- **No duplicate occurrences**: `defer_periodic_job` returns `NULL` (via
  `ON CONFLICT DO NOTHING` on the `procrastinate_periodic_defers` unique
  constraint on `(periodic_id, defer_timestamp)`) when a timestamp was already
  deferred — it does not raise. `AlreadyEnqueued` is raised separately by the
  `queueing_lock` unique index (see next bullet). In-worker `last_defers`
  tracking plus a 10-minute lateness cutoff (`procrastinate.periodic.MAX_DELAY`)
  prevent catch-up storms after an outage.
- **No duplicate transitions / audit events**: `expire_due` re-checks
  `outcome == PENDING` and `expires_at <= now` under row locks before
  transitioning and records a single `APPROVAL_EXPIRED` audit event per
  approval within the same transaction. Retries and re-runs are no-ops.
- **No queued backlog**: `queueing_lock="approval_expiry"` maps to the unique
  index `procrastinate_jobs_queueing_lock_idx_v1` on `(queueing_lock) WHERE
  status = 'todo'`, so a second expiry job cannot be enqueued while one is still
  queued. The lock is released the moment a job is fetched (status `todo` →
  `doing`), so the next scheduled occurrence can be enqueued and run naturally
  without gaps. With the recommended worker (concurrency 1) only one run is
  in-flight at a time.
- **Retries**: `max_attempts=3` permits the initial execution plus up to 3
  retries (4 total executions before the job is marked `failed`), with a 1s
  constant backoff (`wait=1`). Because `retry_exceptions` is unset, every
  exception type is retried — safe here because `expire_due` is idempotent and
  has no payment or webhook side effects. When `attempts` reaches
  `max_attempts`, no further retry is scheduled and the job is marked
  `failed`, remaining observable in `procrastinate_jobs` / `procrastinate_events`
  (see Failed-job inspection).

Run the worker on the `approvals` queue:

```bash
python manage.py procrastinate worker -q approvals \
  --listen-notify --delete-jobs=SUCCESSFUL
```

#### Cron coexistence

A legacy `* * * * * .../manage.py expire_approvals` cron may already be
deployed. Running it concurrently with the periodic task is harmless (both call
the idempotent `expire_due`), but to avoid duplicate work, disable the cron
*before* relying on the periodic task in production:

1. Start the worker on the `approvals` queue and confirm the periodic task
   registered (startup log `Registering task ... with periodic id 'approval_expiry'`,
   or via the shell: `python manage.py procrastinate shell` then `list_tasks`).
2. Confirm the worker has deferred at least one occurrence:

   ```sql
   SELECT count(*) FROM procrastinate_jobs
   WHERE task_name = 'apps.background.tasks.expire_approvals_periodic';
   ```

3. On the host, remove or comment out the `* * * * * ... expire_approvals`
   crontab entry (`crontab -e`) and disable the systemd timer that invokes the
   command, if any.
4. Leave the cron in place until step 2 is confirmed — until then the cron
   remains the active scheduler.

This change does not modify any production cron schedule.

### Failed-job inspection

List failed jobs via the Procrastinate shell:

```bash
python manage.py procrastinate shell
```

At the shell prompt (`procrastinate >`):

```
help      # list available commands
stats     # show job counts by status
```

Or query directly:

```sql
SELECT id, task_name, status, args, attempts
FROM procrastinate_jobs
WHERE status = 'failed'
ORDER BY id DESC LIMIT 20;
```

Retry a single failed job by re-deferring it from your application code.
Procrastinate does not ship a CLI re-defer command in 3.10.0.

### Worker shutdown behavior

- `SIGTERM` — waits up to `PROCRASTINATE_WORKER_SHUTDOWN_GRACEFUL_TIMEOUT`
  seconds (default 3600) for in-flight jobs to finish, then aborts them and
  exits.
- `SIGINT` — same graceful period, with the default Python KeyboardInterrupt
  fallback if the timeout is exceeded.
- After shutdown the worker's heartbeat record ages out; it does not delete its
  row from `procrastinate_workers` automatically.

### Production deploy checklist

1. Set `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and the direct Neon `DATABASE_URL`.
2. Run `python manage.py migrate` and `python manage.py createcachetable`.
3. Run `python manage.py collectstatic --noinput`; Caddy serves `backend/staticfiles` and proxies `/healthz` and `/readyz` over plain HTTP to gunicorn.
4. Keep `/admin/` off the public route or behind an IP allowlist.
5. Configure Caddy with a 64 KiB request body limit and HTTPS. `SECURE_SSL_REDIRECT` is on; the health endpoints are exempt. Caddy's health check must send a `Host` header that is listed in `DJANGO_ALLOWED_HOSTS`.
6. Set `TRUSTED_PROXY_COUNT` to the number of trusted reverse proxies in front of Django: `1` for Caddy only, `2` for a CDN plus Caddy, `0` when Django is reached directly. `NUM_PROXIES` uses the same value so throttling reads the correct client address from `X-Forwarded-For`.
7. Use the direct Neon URL for the Procrastinate worker. Use the pooled URL for web only after testing it with server-side cursors disabled.
8. On Neon's free tier, disable scale-to-zero before a demo and expect a cold start after idle periods.
9. Run `python manage.py verify_audit` after the first requests.
10. Deploy the Procrastinate worker as a separate process from the Django web server. Use a process manager (e.g. systemd, Docker) so the worker restarts on failure.

## Demo reset

```bash
python manage.py seed_demo
```

The command suspends the active `demo-*` agent, creates a fresh agent and policy, and appends a `demo.reset` audit event. It deletes no rows, because audit events use `PROTECT` foreign keys.
