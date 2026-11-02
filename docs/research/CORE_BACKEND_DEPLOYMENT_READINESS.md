# AgentGate Core Backend — Deployment Readiness Audit

**Task:** AG-05 — Core Backend Deployment Readiness Audit
**Worktree:** `/home/winst/agent-gate/.kilo/worktrees/intergration`
**Branch:** `intergration`
**HEAD:** `6775c8df38484a748a6b11f346a0b3d428f150e0`
**Audit date:** 2026-11-01
**Mode:** Read-only audit + single report. No source edits, no migrations, no deployments.

> Verified facts are stated as such. Assumptions and recommendations are explicitly labeled.

---

## 1. Preflight

| Check | Result |
|---|---|
| Branch | `intergration` |
| HEAD | `6775c8df38484a748a6b11f346a0b3d428f150e0` |
| Status | `## intergration...origin/intergration` + untracked `docs/research/` + modified desktop/proxy files (AG-03/AG-04) |
| Remote | `origin` → `git@github.com:Root-node1/agent-gate.git` |

All existing changes preserved. No destructive operations performed.

---

## 2. Current Architecture and Verified Configuration

### 2.1 Stack

| Component | Version / Detail |
|---|---|
| Python | 3.13+ (verified local: 3.14) |
| Django | 6.1.2 |
| DRF | 3.18.3 |
| Database driver | psycopg 3.3.6 (binary + pool) |
| Database | PostgreSQL 17 (CI and production); SQLite for local dev/tests |
| Cache | Redis (production, via `RedisCache`); LocMemCache (dev) |
| Background jobs | Procrastinate 3.10.0 (PostgreSQL-backed, LISTEN/NOTIFY) |
| Auth | django-allauth 65.21.0 (headless + MFA + GitHub OAuth) |
| API docs | drf-spectacular 0.30.0 (runtime-generated OpenAPI) |
| Crypto | cryptography 50.0.2 (Fernet for MFA secrets) |
| WSGI/ASGI | `config.wsgi:application` / `config.asgi:application` |
| Entry point | `backend/manage.py` (settings default: dev) |

### 2.2 Settings profiles

| Profile | File | Purpose |
|---|---|---|
| Dev | `config/settings/dev.py` | Local development (SQLite, console email, DEBUG=True) |
| Test | `config/settings/test.py` | Tests (SQLite unless `TEST_DATABASE_URL` set) |
| Prod | `config/settings/prod.py` | Production (Contabo/Neon, fail-closed validation) |

### 2.3 Production settings (`prod.py`) — verified

- `DEBUG = False`
- Requires `DJANGO_SECRET_KEY` (raises `ImproperlyConfigured` if empty)
- Requires `DJANGO_ALLOWED_HOSTS` (comma-separated)
- `ALLOWED_HOSTS` parsed from env
- `TRUSTED_PROXY_COUNT` (default 1, for Caddy)
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
- `SECURE_SSL_REDIRECT = True` (exempts `/healthz`, `/readyz`)
- `SECURE_HSTS_SECONDS` (default 31536000, subdomains/preload False)
- `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`
- `SECURE_CONTENT_TYPE_NOSNIFF = True`, `X_FRAME_OPTIONS = "DENY"`
- `CSRF_TRUSTED_ORIGINS` from env (comma-separated)
- `STATIC_ROOT = BASE_DIR / "staticfiles"`
- Email: SMTP if `EMAIL_HOST` set, else console backend
- `REDIS_URL` required (raises if empty); `CACHES["default"]` = RedisCache with socket timeouts
- WSGI/ASGI fail-fast: calls `check_mfa_encryption_key`, `check_mfa_bypass_code`, `check_redis_cache_connection` at startup when `DEBUG=False`; raises `SystemExit` on failure

### 2.4 Health endpoints (verified)

- `GET /healthz` → `{"status": "ok"}` (200)
- `GET /readyz` → checks DB connection; returns 503 if unavailable
- `GET /api/health/` → `{"status": "ok"}` (200)
- All exempt from HTTPS redirect (prod)

### 2.5 Logging (verified)

- Security logger `agentgate.security` → StreamHandler → stderr, JSON formatter, no body/header/cookie serialization, `propagate=False`.
- Django `DEFAULT_LOGGING` preserved.

### 2.6 Database configuration (verified)

- `postgres_config(url)` parses `DATABASE_URL` (schemes: postgres, postgresql, postgresql+psycopg).
- `CONN_MAX_AGE` configurable via `DB_CONN_MAX_AGE` (default 0).
- `CONN_HEALTH_CHECKS = True`.
- Query params passed through `parse_qsl`.
- Procrastinate uses the same default DB alias; worker must use direct URL (not pooler) for LISTEN/NOTIFY.

### 2.7 Static files

- `STATIC_ROOT = BASE_DIR / "staticfiles"` (prod). `collectstatic` required before deployment.
- `STATIC_URL = "static/"`.
- No media file configuration (no user uploads beyond admin).

### 2.8 CI/CD (verified)

- `.github/workflows/ci.yml`: backend (PostgreSQL 17 service + Redis 7 service), frontend, security-audit jobs.
- Triggers: push to `main`/`intergration`, pull_request, workflow_dispatch.
- Backend checks: `check --deploy` (prod settings), `check` (test settings), `makemigrations --check --dry-run`, `test`.
- No deployment workflow exists.

---

## 3. Required Production Environment Variables (names only)

### Mandatory (fail-closed if missing)

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `DATABASE_URL` | PostgreSQL connection URL (production DB) |
| `REDIS_URL` | Redis connection URL (cache) |
| `MFA_ENCRYPTION_KEY` | Fernet key for TOTP/recovery-code encryption at rest |

### Strongly recommended

| Variable | Purpose |
|---|---|
| `CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins (HTTPS) |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `TRUSTED_PROXY_COUNT` | Number of reverse proxies (default 1 for Caddy) |
| `SECURE_HSTS_SECONDS` | HSTS max-age (default 31536000) |
| `DJANGO_ADMIN_PATH` | Admin URL path (default `admin/`) |
| `FRONTEND_ORIGIN` | Frontend origin for password-reset links |
| `DB_CONN_MAX_AGE` | Persistent DB connections (default 0) |
| `MFA_ENCRYPTION_PREVIOUS_KEYS` | Comma-separated older Fernet keys for rotation |
| `MFA_BYPASS_CODE` | MFA bypass code for emergency access (checked at startup) |

### Optional (feature-dependent)

| Variable | Purpose |
|---|---|
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | SMTP email |
| `THROTTLE_AGENT`, `THROTTLE_ANON` | Rate-limit overrides |
| `DEMO_ORG_NAME` | Demo organization name |
| `PROCRASTINATE_DATABASE_ALIAS` | Procrastinate DB alias (default `default`) |
| `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_SECRET` | GitHub OAuth (allauth) |
| `PAYPAL_ENV`, `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID` | PayPal (only if integration merged and enabled) |
| `PAYPAL_CHECKOUT_ENABLED`, `PAYPAL_PAYOUTS_ENABLED` | PayPal feature flags (default `false`) |

### Never in production

- PayPal sandbox credentials (`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` from sandbox) — must not enter production config.
- `DJANGO_DEBUG=True`.
- SQLite `DATABASE_URL` (production must use PostgreSQL).

---

## 4. Database and Migration Safety

### 4.1 Production database plan

- **Database name:** A new, dedicated database (e.g., `agentgate_prod` or `agentgate_production`). Must be entirely separate from `agentgate`, `agentgate_test`, `agentgate_sandbox`, `paysplit`, `infinite_mushrooms`, and `postgres`.
- **Role:** A least-privilege role (e.g., `agentgate_app`) with `CONNECT`, `USAGE` on schema, and DML/DDL on application tables. No superuser. No `CREATEDB`. Migration user (e.g., `agentgate_migrate`) with temporary DDL privileges, or use the same role if migrations run as the app role.
- **Connection:** PostgreSQL 17. Direct URL for migrations and the Procrastinate worker (LISTEN/NOTIFY). Pooled URL for web only if tested with server-side cursors disabled.
- **SSL:** `sslmode=require` (Neon) or equivalent.

### 4.2 Migration ordering

1. `python manage.py migrate` (all app migrations including `procrastinate`).
2. `python manage.py createcachetable` (throttle cache table).
3. `python manage.py collectstatic --noinput`.
4. `python manage.py createsuperuser` (manual, interactive).
5. `python manage.py seed_demo` (optional, demo only).

### 4.3 Migration risks

- **Audit chain:** The audit log is append-only with hash-chaining and database triggers blocking TRUNCATE/DELETE. Migrations must not disable triggers. Demo reset requires schema drop (documented in OPERATIONS.md) — not for production.
- **Procrastinate migrations:** Auto-created by `migrate` (app label `procrastinate`). No separate bootstrap.
- **PayPal migrations:** On `intergration`, only `payments.0001_initial` (WebhookEvent table) exists. If `feat/paypal-sandbox` is merged, migrations `0002`–`0005` (CheckoutOrder, PayoutReservation) would also run. These create new tables only — no data-loss or locking risk on an empty production database. Safe to include even with PayPal disabled.
- **No rollback tested:** Migration rollback (`migrate <app> <previous>`) is not documented or tested. Recommend forward-only migrations in production.

### 4.4 Backup and restore

- **Off-server `pg_dump`** of audit tables (recommended daily). Neon provides managed backups (plan-dependent).
- **Audit chain verification:** `python manage.py verify_audit` walks events and recomputes hashes.
- **Restore:** `pg_restore` from dump; re-run `migrate` to ensure schema currency.

---

## 5. PayPal Isolation Audit

### 5.1 Current state on `intergration`

- The `apps.payments` app is **minimal**: `WebhookEvent` model, `FakeExecutor`, admin, apps config, migration `0001_initial`. No PayPal routes, no views, no services, no client, no feature flags, no checks.
- `config/urls.py` does **not** include `apps.payments.urls`. No PayPal endpoints are registered.
- No PayPal environment variables are required. No PayPal credentials in `.env.example` beyond commented placeholders.

**Conclusion for intergration HEAD:** PayPal is entirely absent. Deploying this backend does not expose any PayPal functionality. The 503-policy question does not apply yet.

### 5.2 PayPal sandbox implementation (feat/paypal-sandbox, unmerged)

The isolation policy requires: routes registered, feature flags default false, all operations fail closed with consistent 503 + stable machine-readable error code, frontend cannot override, missing credentials never switch to live, production doesn't require credentials when disabled, sandbox creds never enter production.

| Requirement | Status in feat/paypal-sandbox | Finding |
|---|---|---|
| Routes registered | ✅ | `urls.py` registers checkout-orders, payout-reservations, webhooks/paypal/ |
| Feature flags default false | ✅ | `PAYPAL_CHECKOUT_ENABLED`/`PAYPAL_PAYOUTS_ENABLED` default `"false"` |
| Fail closed on disabled | ⚠️ Partial | Create view: `get_paypal_config` fails → 503 "PayPal is not configured." (if no creds). `checkout_enabled=False` → 403 "Checkout is not enabled." (not 503). |
| Consistent 503 + stable error code | ❌ Not met | Error messages are human-readable strings, not stable machine-readable codes. Status codes inconsistent (503 vs 403). |
| Frontend cannot override | ✅ | Flags read from Django settings (env), not request body |
| Missing creds → no live switch | ✅ | `SUPPORTED_ENVIRONMENTS = ("sandbox",)` only; `PAYPAL_ENV` must be "sandbox" or `PayPalConfigError` |
| No creds required when disabled | ✅ | `get_paypal_config` only requires creds when a flag is enabled |
| Sandbox creds never in production | ✅ | `.env` untracked; no credentials committed; `.env.example` has empty placeholders |
| Webhook disabled → 503 | ✅ | `WebhookDisabled` → 503 "Webhooks are not configured." |
| Payout disabled → 503 | ✅ (mostly) | `_require_payouts_enabled` raises `PayoutFeatureDisabled` → 503 "Payouts is not configured." |
| Capture disabled → 503 | ❌ | Returns 403 "Checkout is not enabled." (should be 503) |

**PayPal migration history (feat/paypal-sandbox):** `0001_initial` (WebhookEvent) → `0002` (CheckoutOrder) → `0003` (payer_action_url) → `0004` (PayoutReservation) → `0005` (sender_batch_id + more). All additive (new tables). Safe to run in production with PayPal disabled — tables exist but are never populated because all operations return 503/403.

**System check:** `check_paypal_config` (payments.E001) validates env/flags/creds at startup. Passes when both flags are false (no creds required).

### 5.3 Remediation required before PayPal isolation is production-ready

1. Standardize all disabled-operation responses to **503 Service Unavailable** with a stable machine-readable error code (e.g., `{"code": "paypal_disabled", "detail": "..."}`).
2. Fix `CheckoutOrderCaptureView` to return 503 (not 403) when checkout is disabled.
3. Ensure `PayoutReservationReconcileView` fails closed (currently calls `reconcile_payout` without a feature-flag check in some paths — verify).
4. Define and document the stable error code contract (e.g., `paypal_not_configured`, `checkout_disabled`, `payouts_disabled`, `webhooks_disabled`).
5. Add tests asserting 503 + stable code for every operation when disabled.

---

## 6. Authentication and Browser Security

### 6.1 Verified

- Session cookies: `HttpOnly=True`, `SameSite=Lax`, `Secure=True` (prod).
- CSRF: `CSRF_COOKIE_HTTPONLY=False` (JS reads it for `X-CSRFToken`), `SameSite=Lax`, `Secure=True`.
- CSRF trusted origins from env (`CSRF_TRUSTED_ORIGINS`).
- Allauth headless JSON API (no form-based reset surface).
- MFA: TOTP + recovery codes, Fernet-encrypted at rest, MFA enforced for privileged roles, `MFA_TRUST_ENABLED=False`.
- Organization scoping enforced server-side (`spend_queryset` filters by membership).
- Idempotency keys required for spend submission.
- Security headers: `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`, HSTS (no preload/subdomains by default).
- SSL redirect with health-endpoint exemption.
- Trusted proxy count configurable (default 1 for Caddy).
- Security logging: JSON to stderr, no body/header/cookie serialization.

### 6.2 Gaps

- `SECURE_HSTS_PRELOAD=False` and `SECURE_HSTS_INCLUDE_SUBDOMAINS=False` (conservative; acceptable for initial deploy).
- No CORS configuration (not needed — same-origin SPA + backend; desktop uses loopback proxy).
- Admin site mounted at `settings.ADMIN_PATH` (default `admin/`) — Doc.md recommends IP allowlist or non-public route.
- No rate-limiting on auth endpoints beyond DRF throttle (configured but anonymous throttle has no public endpoints yet).

---

## 7. HTTPS, Firewall and Networking Plan

### 7.1 Recommended architecture (from Doc.md + OPERATIONS.md)

- **Reverse proxy:** Caddy (automatic HTTPS via Let's Encrypt, TLS termination).
- **App server:** gunicorn (WSGI) behind Caddy.
- **Worker:** Procrastinate worker process (separate container/process) using direct DB URL.
- **Database:** Managed Neon PostgreSQL (eu-central-1) or dedicated PostgreSQL 17 container.
- **Static files:** `collectstatic` → `staticfiles/`, served by Caddy or WhiteNoise.

### 7.2 Firewall rules (recommended)

- Inbound: 22 (SSH, restricted IP), 80 (HTTP → redirect), 443 (HTTPS).
- Outbound: 443 (Neon, email SMTP), 5432 (if self-hosted PG on same network).
- PostgreSQL port NOT exposed publicly (if self-hosted, bind to private network only).
- Redis NOT exposed publicly (if self-hosted).

### 7.3 SSH hardening (recommended)

- Key-based auth only, disable password auth.
- Non-root user for deployment.
- Fail2ban or equivalent.
- SSH over port 443 (documented in Doc.md — some networks block 22).

### 7.4 Private networking

- Caddy, gunicorn, worker on same host (localhost or Docker network).
- Database connection over TLS (Neon) or private VPC.
- No direct public access to gunicorn or worker.

---

## 8. Backup, Restore and Rollback

### 8.1 Backup

- Daily off-server `pg_dump` (custom format) of the production database.
- Neon managed backups (plan-dependent; free tier has limited retention).
- Audit tables specifically (append-only, hash-chained).
- `.env` file backed up securely (contains secrets).

### 8.2 Restore

1. Provision new database.
2. `pg_restore` from dump.
3. Set `DATABASE_URL` to new instance.
4. Run `migrate` (should be no-op if schema matches).
5. Run `verify_audit`.
6. Restart gunicorn + worker.

### 8.3 Rollback

- **Code:** Revert to previous Git commit/tag, rebuild, restart. No blue-green currently.
- **Database:** Restore from `pg_dump` (forward-only migrations recommended; no rollback tested).
- **Config:** Restore `.env` from backup.

---

## 9. CI/CD and Deployment Workflow Recommendation

### 9.1 Current CI

- GitHub Actions: backend (PG 17 + Redis 7), frontend, security-audit.
- Triggers: push to `main`/`intergration`, PR, workflow_dispatch.
- No deployment step.

### 9.2 Recommended addition (not implemented)

- A separate `deploy.yml` workflow triggered on push to `main` (or a release tag):
  1. Run full CI.
  2. SSH to Contabo VPS.
  3. `git pull` (or deploy artifact).
  4. `python manage.py migrate`.
  5. `python manage.py collectstatic --noinput`.
  6. Restart gunicorn + worker (systemd or Docker Compose).
  7. Health-check verification (`/readyz`).
- Use GitHub Secrets for SSH key and env vars (or a server-side env file managed by ops).
- Never store secrets in the repo.

---

## 10. Blockers and Remediation Tasks

### Blockers (must resolve before deployment)

| # | Blocker | Severity | Remediation |
|---|---|---|---|
| 1 | No Docker/Compose or deployment configuration exists | High | Create Dockerfile + docker-compose.yml for Django + Caddy + worker, or document manual gunicorn/Caddy setup |
| 2 | PayPal isolation not production-ready (inconsistent 503, no stable error code) | High | Standardize 503 + machine-readable codes across all PayPal operations (see §5.3) — only relevant when PayPal is merged |
| 3 | No automated backup/restore procedure | High | Implement daily `pg_dump` cron + off-server storage; test restore |
| 4 | No deployment workflow in CI | Medium | Add `deploy.yml` or document manual deployment runbook |
| 5 | `SECURE_HSTS_PRELOAD` / subdomains not configured | Low | Decide and set before public launch |
| 6 | Admin site publicly accessible | Medium | IP-allowlist or non-public path |
| 7 | No rollback tested | Medium | Test migration rollback or adopt forward-only policy |
| 8 | MFA bypass code / encryption key provisioning | High | Generate and securely store `MFA_ENCRYPTION_KEY` and `MFA_BYPASS_CODE` for production |
| 9 | `createcachetable` not automated | Low | Add to deployment runbook/migration step |
| 10 | No monitoring/alerting configured | Medium | Add health-check monitoring (uptime, `/readyz`) |

### Non-blockers (improvements)

- Add WhiteNoise for static file serving if not using Caddy for static.
- Add Sentry or equivalent error reporting.
- Add log aggregation (journald → Loki/Grafana or similar).
- Enable HSTS preload after domain is stable.
- Configure CORS if a separate frontend origin is needed (currently same-origin).

---

## 11. GO / NO-GO Recommendation

**Recommendation: NO-GO for production deployment at this time.**

**Rationale:**

1. **No deployment artifacts exist.** There is no Dockerfile, docker-compose.yml, Caddyfile, systemd unit, or deployment runbook in the repository. The deployment architecture is documented in `Doc.md` and `OPERATIONS.md` but not implemented as runnable configuration.

2. **PayPal isolation is not production-ready** (on `feat/paypal-sandbox`, which is not yet merged). The inconsistent 503/403 responses and lack of stable machine-readable error codes mean the "disabled by default, fail closed" policy is not fully enforced. This is only a blocker if PayPal is merged before deployment; deploying `intergration` HEAD (which has no PayPal) avoids this.

3. **No backup/restore or rollback has been tested.** The procedures are documented but not verified.

4. **No deployment workflow or monitoring exists.**

**What IS ready (structural):**

- Production settings profile (`prod.py`) with fail-closed validation for all mandatory secrets.
- Health and readiness endpoints (`/healthz`, `/readyz`, `/api/health/`).
- Security headers, secure cookies, HSTS, proxy SSL header.
- WSGI/ASGI fail-fast startup checks for MFA key and Redis.
- Migration framework with additive-only PayPal migrations (safe when disabled).
- CI pipeline with PostgreSQL 17 + Redis 7 integration tests.
- Audit log with hash-chaining and append-only triggers.

**Path to GO:**

1. Create deployment configuration (Dockerfile + Compose or manual runbook).
2. Provision production database, Redis, and secrets.
3. Run migrations + `createcachetable` + `collectstatic`.
4. Implement backup cron + test restore.
5. Add health-check monitoring.
6. (If PayPal is merged) Standardize 503 + stable error codes.
7. Deploy to staging first, verify, then production.

---

## 12. Commands Used (read-only)

```
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short --branch
git remote -v
cat backend/requirements.txt (head)
cat backend/manage.py
cat backend/config/wsgi.py
cat backend/config/asgi.py
cat backend/config/settings/prod.py
sed -n '27,140p' backend/config/settings/base.py
sed -n '300,360p' backend/config/settings/base.py
cat backend/config/urls.py
cat backend/apps/payments/models.py
cat backend/apps/payments/executors.py
cat backend/apps/payments/apps.py
cat backend/apps/payments/migrations/0001_initial.py
cat backend/.env.example
sed -n '80,160p' README.md
sed -n '140,210p' Doc.md
cat backend/OPERATIONS.md (head 80)
ls docs/ ; ls infra (none)
find . -iname "Dockerfile*" ...
grep -rn "deploy|docker|gunicorn|caddy" README.md Doc.md
# feat/paypal-sandbox branch (read-only):
cat .../payments/urls.py, views, webhook_views, webhook_service, executors, config.py, checks.py, base.py (PAYPAL section)
cat .../payments/management/commands/process_paypal_webhooks.py
cat .../payments/webhook_processing.py
```

No source code, configuration, database, or deployment changes were made. No migrations were run. No containers were built or deployed.

---

**STOP. Awaiting Tech Lead review.**
filePath">
/home/winst/agent-gate/.kilo/worktrees/intergration/docs/research/CORE_BACKEND_DEPLOYMENT_READINESS.md