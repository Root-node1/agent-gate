# AgentGate — Production Readiness Assessment

Assessed on branch `release/v0.1.0-ux-demo`
(HEAD `fbe9323c0d4411dfcccf51760bfbf7fac33b4202`, November 2026).

---

## 1. Release Readiness Summary

| Domain | Status | Evidence |
|---|---|---|
| **Frontend build & lint** | **VERIFIED** | `npm run build` clean (440 ms, 0 errors); `npm run lint` (ESLint) clean |
| **Frontend Node unit tests** | **VERIFIED** | 17/17 passed — `auth-client.test.mjs`, `session-model.test.mjs` |
| **Backend test suite (SQLite)** | **VERIFIED** | 763 passed, 30 skipped (PostgreSQL-only), 0 failures — `python manage.py test` |
| **Backend linting** | **VERIFIED** | `ruff check .` → "All checks passed!" |
| **Django system check (dev)** | **VERIFIED** | Zero errors; one warning: `MFA_ENCRYPTION_KEY` not set (expected in dev without key) |
| **Django system check (prod)** | **VERIFIED in CI** | `check --deploy --settings=config.settings.prod` passes in GitHub Actions |
| **Policy engine tests** | **VERIFIED** | 80 pure-Python engine tests pass; AI classifier is strictly advisory (verified in `test_classifier.py`, `test_rules.py`) |
| **PayPal execution tests** | **VERIFIED** | 82 tests: mock PayPal client, payout payload, webhook ingestion, signature verification, replay protection, duplicate handling |
| **Auth / MFA / password-reset tests** | **VERIFIED** | 56+ tests covering TOTP enrollment, rate-limiting, replay, DRF bypass hardening |
| **API endpoint tests** | **VERIFIED** | 104+ tests covering spend requests, approvals, agents, audit, policies |
| **Approval / payment policy boundary** | **VERIFIED** | CAS state transition in `services.py`; only `APPROVED` → `EXECUTING` is permitted; unapproved requests never call executor |
| **Webhook signature + replay** | **VERIFIED** | `test_paypal_webhooks.py` — unsigned/invalid events rejected; duplicate delivery handled idempotently |
| **Idempotency** | **VERIFIED** | Same key + body → stored response replayed; same key + different body → 409 |
| **Docker image build** | **VERIFIED in CI** | `docker build` succeeds in `deployment-config` CI job |
| **Compose topology** | **VERIFIED in CI** | Automated assertions: network isolation, port exposure (Caddy-only), no PayPal in deployment files, CSP headers |
| **Fresh PG 17 migration** | **VERIFIED** | Isolated Docker PG 17.11 container; `migrate --noinput` succeeded |
| **Browser authentication journeys** | **NOT TESTED** | No Playwright/Cypress suite; manual browser check still required |
| **Live GitHub OAuth** | **NOT TESTED** | Requires developer's own OAuth app credentials |
| **Live PayPal Sandbox API operation** | **NOT TESTED** | Requires `PAYPAL_CLIENT_ID` + `PAYPAL_CLIENT_SECRET` from developer |
| **Full local app startup against PG 17** | **NOT TESTED** | Host has PG 18.6; isolated container migration confirmed; full health-check startup not performed |

---

## 2. Security Controls

| Control | Implementation | Status |
|---|---|---|
| Session cookies | `HttpOnly=True`, `SameSite=Lax`; `Secure=True` in production | Implemented |
| CSRF | `CsrfViewMiddleware`; `CSRF_COOKIE_HTTPONLY=False` (SPA reads token); `Secure` in production | Implemented |
| MFA (TOTP + recovery codes) | django-allauth MFA; Fernet at-rest encryption of TOTP secrets and recovery-code seeds | Implemented |
| Password reset | 1-hour token expiry; rate-limited (3/h/key, 20/m/IP) | Implemented |
| Rate limiting | DRF throttling per agent key and anonymous; `THROTTLE_AGENT=60/min` | Implemented |
| Request body cap | 64 KiB max; `RequestDataTooBig` returns 400 | Implemented |
| Audit log | Append-only, hash-chained per organization; `AUDIT_ANCHOR_PATH` optional off-host anchoring | Implemented |
| Payment policy boundary | CAS `APPROVED → EXECUTING`; denied/unapproved requests never call executor | Implemented and tested |
| AI classifier boundary | Advisory only; score contributes to risk display, never overrides DENY or bypasses approval | Implemented and tested |
| Webhook verification | HMAC signature check via PayPal API; unsigned events rejected | Implemented and tested |
| Idempotency | Per-agent key+body hash; replays return stored response; key reuse with different body → 409 | Implemented and tested |
| PayPal live-mode guard | `allow_live=False` by default; `PAYPAL_ALLOW_LIVE=1` required explicitly | Implemented |
| Secret leakage | Credentials in env vars only; never logged, never in frontend env, never in Git | Verified |
| Container isolation | Only Caddy exposes public ports; PostgreSQL and Redis on internal `backend` network only | Verified in CI |
| Security headers | CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy` via Caddy | Implemented |
| HSTS | Enabled in production (`SECURE_HSTS_SECONDS=31536000`); subdomains/preload off until confirmed | Implemented |
| SQL injection | Django ORM throughout; no raw SQL in application code | Verified by code inspection |
| XSS | React escaping + CSP `script-src 'self'` on non-admin pages | Implemented |

---

## 3. Environment Variables — Production Checklist

All of these must be set in `Coolify → Environment Variables` (or `.env.production`
on the VPS). Never commit real values.

| Variable | Purpose | Required |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | Yes |
| `DJANGO_SECRET_KEY` | 50+ char random string | Yes |
| `DJANGO_DEBUG` | `False` | Yes |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated domain names | Yes |
| `DATABASE_URL` | PostgreSQL 17 connection URL | Yes |
| `REDIS_URL` | Redis connection URL (internal Docker network) | Yes |
| `REDIS_PASSWORD` | Redis password (also embedded in `REDIS_URL`) | Yes |
| `MFA_ENCRYPTION_KEY` | Fernet key (AES-256-CBC) for TOTP/recovery-code at-rest encryption | Yes |
| `CSRF_TRUSTED_ORIGINS` | `https://app.example.com` | Yes |
| `FRONTEND_ORIGIN` | `https://app.example.com` | Yes |
| `DOMAIN` | Caddy TLS domain | Yes |
| `TRUSTED_PROXY_COUNT` | `1` (Caddy only) | Yes |
| `SECURE_HSTS_SECONDS` | `31536000` | Yes |
| `GUNICORN_WORKERS` | `2` (minimum) | Yes |
| `PAYMENT_EXECUTOR` | `fake` initially; `paypal` after sandbox sign-off | Yes |
| `PAYMENTS_EXECUTION_ENABLED` | `false` initially | Yes |
| `WEBHOOK_RETENTION_DAYS` | `30` | Yes |
| `PAYPAL_MODE` | `sandbox` | Required when executor=paypal |
| `PAYPAL_CLIENT_ID` | Sandbox app client ID | Required when executor=paypal |
| `PAYPAL_CLIENT_SECRET` | Sandbox app client secret | Required when executor=paypal |
| `PAYPAL_WEBHOOK_ID` | Webhook ID from PayPal Developer Dashboard | Required when executor=paypal |
| `BACKUP_ENCRYPTION_PASSPHRASE` | For `scripts/backup_database.sh` | Recommended |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Off-site backup storage | Recommended |
| `EMAIL_HOST`, `EMAIL_PORT`, etc. | SMTP for password reset / verification emails | Required for real users |
| `MFA_BYPASS_CODE` | Emergency admin bypass (store securely, rarely used) | Recommended |

---

## 4. Pre-Deployment Checklist

Before deploying to production, verify each item:

- [ ] `DJANGO_SECRET_KEY` is 50+ chars, randomly generated, not reused elsewhere
- [ ] `DEBUG=False` in production settings
- [ ] `ALLOWED_HOSTS` lists only the production domain(s)
- [ ] `CSRF_TRUSTED_ORIGINS` lists only the production HTTPS origin
- [ ] `DATABASE_URL` points to the production PostgreSQL 17 instance
- [ ] `REDIS_URL` and `REDIS_PASSWORD` point to the internal Redis service
- [ ] `MFA_ENCRYPTION_KEY` is a fresh Fernet key (not `change-me` or test key)
- [ ] `PAYMENT_EXECUTOR=fake` until PayPal sandbox is explicitly signed off
- [ ] `PAYMENTS_EXECUTION_ENABLED=false` until execution is intentionally enabled
- [ ] `PAYPAL_ALLOW_LIVE` is unset (live mode disabled by default)
- [ ] No PayPal credentials in `compose.yaml`, `Dockerfile`, or committed env files
- [ ] No `DEBUG=True` in any production config file
- [ ] Container health checks are enabled and passing
- [ ] Only Caddy publishes ports 80 and 443
- [ ] PostgreSQL and Redis are on the internal Docker network only
- [ ] Database migrations have been run in the production environment
- [ ] `python manage.py collectstatic` has run (entrypoint.sh handles this)
- [ ] Email delivery is configured (at minimum, check console backend is not used in production)
- [ ] Automatic backups are configured and tested
- [ ] Restore test has been performed on an isolated environment

---

## 5. Remaining Blockers Before Live Deployment

| Blocker | Owner | Prerequisite |
|---|---|---|
| PostgreSQL 17 production instance provisioned | Founder | Contabo VPS + Coolify |
| Redis production instance provisioned | Founder | Contabo VPS + Coolify |
| `MFA_ENCRYPTION_KEY` generated and stored securely | Founder | Key management |
| `DJANGO_SECRET_KEY` generated for production | Founder | Key management |
| SMTP email provider configured | Founder | Email provider |
| PayPal Sandbox credentials added (when enabling executor) | Founder | PayPal Developer account |
| DNS pointing to Contabo VPS | Founder | Domain registrar |
| Caddy `DOMAIN` variable set to production domain | Founder | DNS |
| Browser authentication journeys manually verified | UX person / Founder | Local setup |
| Off-site backup destination provisioned and tested | Founder | S3-compatible storage |
