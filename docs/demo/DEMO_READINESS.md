# AgentGate Demo Readiness

Branch: `release/v0.1.0-ux-demo`  
HEAD: `fbe9323c0d4411dfcccf51760bfbf7fac33b4202`  
Assessed: November 2026

Statuses reflect actual execution evidence. Automated tests do not imply
browser behavior. "Not tested" means exactly that — the check was not performed.

---

## Automated Test Results

| Check | Result | Evidence |
|---|---|---|
| Frontend production build | **PASS** | `npm run build` — clean, 440 ms, 0 errors |
| Frontend ESLint | **PASS** | `npm run lint` — 0 warnings |
| Frontend Node unit tests | **PASS** | 17/17 — `auth-client.test.mjs`, `session-model.test.mjs` |
| Backend full test suite (SQLite) | **PASS** | 763 tests passed, 30 skipped (PG-only), 0 failures |
| Backend linting (Ruff) | **PASS** | `ruff check .` — "All checks passed!" |
| Django system check (dev) | **PASS** | 0 errors; 1 expected warning: `MFA_ENCRYPTION_KEY` not set |
| Django system check (prod) — CI | **PASS** | `check --deploy --settings=config.settings.prod` in GitHub Actions |
| Policy engine tests | **PASS** | 80 pure-Python tests — deterministic rules, AI advisory boundary |
| PayPal execution tests | **PASS** | 82 tests — executor, payout payload, webhooks, replay, idempotency |
| Auth / MFA tests | **PASS** | 56+ tests — TOTP, rate-limit, replay hardening, DRF bypass |
| Approval / policy boundary | **PASS** | CAS test: only APPROVED → EXECUTING; denied/pending never call executor |
| Webhook signature + replay | **PASS** | Invalid/unsigned/replayed events rejected |
| Fresh PostgreSQL 17 migration | **PASS** | Isolated Docker PG 17.11 container; `migrate --noinput` succeeded |
| Docker image build | **PASS (CI)** | `docker build` succeeds in `deployment-config` CI job |
| Compose topology assertions | **PASS (CI)** | Network isolation, port exposure, CSP headers verified |

---

## Browser and Manual Checks

| Check | Status | Notes |
|---|---|---|
| Anonymous `/app` redirects to login | **Not tested in browser** | Frontend guard implemented in `SessionGuards.tsx` |
| Successful login; session confirmed | **Not tested in browser** | Automated backend + JS unit tests pass |
| Session restored after refresh | **Not tested in browser** | — |
| Registration + email verification | **Not tested in browser** | Email appears in backend terminal (console backend) |
| TOTP enrollment and login | **Not tested in browser** | Automated tests pass; browser journey unverified |
| Recovery-code login | **Not tested in browser** | — |
| Logout + session invalidation | **Not tested in browser** | — |
| Password reset request + confirm | **Not tested in browser** | Automated backend tests pass |
| Password change | **Not tested in browser** | Implemented in `SecuritySection.tsx` → allauth |
| TOTP enrollment/removal via Settings | **Not tested in browser** | `SecuritySection.tsx` calls real allauth endpoints |
| Recovery code generation/display | **Not tested in browser** | — |
| Dashboard simulator (allow scenario) | **Not tested in browser** | Client-side implementation reviewed; looks correct |
| Dashboard simulator (deny scenario) | **Not tested in browser** | — |
| Dashboard simulator (approval scenario) | **Not tested in browser** | — |
| Approval detail + approve/deny | **Not tested in browser** | — |
| Audit log display | **Not tested in browser** | — |
| Mobile viewport rendering | **Not tested** | CSS is responsive; no device test performed |

---

## PayPal and External Services

| Check | Status | Notes |
|---|---|---|
| Dashboard PayPal settings page | **Source-verified** | `PaypalSection.tsx` correctly labels everything as simulated |
| Live PayPal Sandbox API operation | **Not tested** | Requires `PAYPAL_CLIENT_ID` + `PAYPAL_CLIENT_SECRET` |
| PayPal webhook signature verification | **Automated tests pass** | No live webhook delivery tested |
| PayPal AI Toolkit documentation | **Reviewed** | Official README and MCP docs reviewed Nov 2026 |
| PayPal AI Toolkit installation | **Not performed** | No plugin installed; no agent running |
| PayPal MCP connection | **Not configured** | No token or sandbox session |
| Live GitHub OAuth | **Not tested** | No provider credentials or callback configured |

---

## Demo Data Boundaries

The table below clarifies exactly what is simulation versus real for each
demo scenario:

| Demo area | Type | Reset on reload? | Requires backend? | PayPal involved? |
|---|---|---|---|---|
| Policy simulator outcomes | Browser-memory simulation | Yes | No | No |
| Approval queue actions | Browser-memory simulation | Yes | No | No |
| Payment results (completed/failed) | Browser-memory simulation | Yes | No | No |
| Audit log in dashboard | Browser-memory simulation | Yes | No | No |
| Agent list, policy data | Browser-memory seed | Yes | No | No |
| Login / session | Real backend auth (allauth) | No | **Yes** | No |
| Email verification code | Real backend email (console) | No | **Yes** | No |
| MFA enrollment / login | Real backend MFA | No | **Yes** | No |
| Password reset | Real backend email + allauth | No | **Yes** | No |
| Live API tester request | Real backend policy engine | No | **Yes** | No (executor=fake) |
| Live API tester — PayPal exec. | Real PayPal Sandbox | No | **Yes** | **Yes (when enabled)** |

---

## Commands to Reproduce Test Evidence

```bash
# Frontend
cd frontend
npm run build
npm run lint
node --test --test-reporter=spec tests/auth-client.test.mjs tests/session-model.test.mjs

# Backend (SQLite — no PostgreSQL required)
cd backend
source venv/bin/activate
export DJANGO_SETTINGS_MODULE=config.settings.test
python manage.py test

# Backend lint
ruff check .

# Django system check (dev, with SQLite)
python manage.py check

# Django check with fresh PG17 container
docker run --rm -d --name agentgate-pg17 \
  -e POSTGRES_USER=agentgate \
  -e POSTGRES_PASSWORD=agentgate-local-only \
  -e POSTGRES_DB=agentgate \
  -p 127.0.0.1:55432:5432 postgres:17
export DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:55432/agentgate'
python manage.py migrate --noinput
docker stop agentgate-pg17
```

---

## Manual Browser Verification Checklist

Record each as **PASS**, **FAIL**, or **BLOCKED** with browser, timestamp,
and non-sensitive evidence. Do not capture passwords, codes, or secrets.

- [ ] Anonymous `/app` redirects to `/login`
- [ ] Login succeeds; dashboard loads; `GET /api/auth/user/` confirms session
- [ ] Session persists after page reload; protected route still protected
- [ ] Registration reaches "verify email" state; code appears in backend terminal
- [ ] Email verification completes with correct code
- [ ] Login with incorrect password shows error message
- [ ] TOTP enrollment: scan QR / enter setup key; enter 6-digit code; confirm active
- [ ] TOTP login: use authenticator code after credentials
- [ ] Recovery-code login: use a recovery code after credentials
- [ ] Logout invalidates session; `/app` redirects to login
- [ ] Password-reset request: code appears in backend terminal
- [ ] Password-reset confirmation: new password accepted; old rejected
- [ ] Password change via Settings → Security works
- [ ] TOTP removal via Settings → Security works
- [ ] Recovery-code regeneration via Settings → Security works
- [ ] CSRF cookie is present; no credentials in localStorage / sessionStorage
- [ ] Dashboard simulator: "allow" scenario shows allow result
- [ ] Dashboard simulator: "deny" scenario shows deny with rule codes
- [ ] Dashboard simulator: "approval" scenario shows needs-approval; visible in Approvals
- [ ] Approval detail: Approve action marks approval approved; payment result simulated
- [ ] Approval detail: Deny action marks approval denied
- [ ] Audit log: events for the above scenarios appear
- [ ] Settings tabs: all tabs load without error
- [ ] PayPal settings tab: correctly shows "Sandbox · demo mode" badge
- [ ] Mobile viewport (375 px wide): nav collapses, layout is usable

**Do not bypass email verification, MFA, or CSRF to make a step pass.**  
If a step fails, record the error and follow [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
