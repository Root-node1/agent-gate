# AgentGate Playwright / Firefox E2E Test Runbook for GitHub Copilot

## 1. Environment and Repository Baseline
- **Repository Location:** `/home/winst/agent-gate`
- **Branch:** `release/v0.1.0-ux-demo`
- **Commit HEAD:** `ce28f99` (`Merge release/v0.1.0-integrated into main`)
- **Target Browser Engine:** **Firefox** (`projects: [{ name: 'firefox', use: { ...devices['Desktop Firefox'] } }]`)
- **Execution Tooling:** GitHub Copilot using Playwright Test (`npx playwright test --project=firefox`)

---

## 2. Service Startup Instructions

### Step 2.1 — Start Test Database (PostgreSQL 17)
```bash
docker run --rm -d --name agentgate-test-pg17 \
  -e POSTGRES_USER=agentgate \
  -e POSTGRES_PASSWORD=agentgate-local-only \
  -e POSTGRES_DB=agentgate \
  -p 127.0.0.1:55432:5432 postgres:17

# Wait for DB readiness
for attempt in $(seq 1 30); do
  docker exec agentgate-test-pg17 pg_isready -U agentgate -d agentgate >/dev/null 2>&1 && break
  sleep 1
done

export DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:55432/agentgate'
```

### Step 2.2 — Backend Service Setup
```bash
cd /home/winst/agent-gate/backend
export DATABASE_URL='postgresql://agentgate:agentgate-local-only@127.0.0.1:55432/agentgate'
export DJANGO_SETTINGS_MODULE=config.settings.dev
export DJANGO_DEBUG=True
export PAYMENT_EXECUTOR=fake
export MFA_ENCRYPTION_KEY='0123456789abcdef0123456789abcdef0123456789a=' # 32-byte urlsafe Fernet key

./venv/bin/python manage.py migrate
./venv/bin/python manage.py runserver 0.0.0.0:8000
```
Health & Readiness:
- `curl http://localhost:8000/healthz` -> `{"status":"ok"}`
- `curl http://localhost:8000/readyz` -> `{"status":"ok"}`

### Step 2.3 — Frontend Development Server
```bash
cd /home/winst/agent-gate/frontend
npm run dev -- --host 127.0.0.1 --port 5173
```
- Base URL: `http://localhost:5173`
- API Proxy: Automatically forwards `/api/*` and `/v1/*` to `http://localhost:8000`.

---

## 3. Test Fixtures and Credentials

Safe test credentials (never use production accounts):
- **User A (Admin):** `admin@example.test` / `Password123!@#$`
- **User B (Approver):** `approver@example.test` / `Password123!@#$`
- **User C (Unverified/New):** `newbie@example.test` / `Password123!@#$`
- **Fake Agent Key:** Generated via `POST /v1/agents/` during test flows (one-time reveal `agk_...`).

---

## 4. User Workflows to Test with Playwright on Firefox

1. **Registration & Email Verification:**
   - Navigate to `/register`.
   - Submit email + password. Verification code emitted to console email backend.
   - Fill 6-digit code at `/verify-email`.
2. **Organization Onboarding:**
   - Newly verified user is redirected to `/onboarding`.
   - Enter workspace name: e.g. "Acme Corp".
   - Submits workspace creation and transitions to `/app` as `admin`.
3. **Dashboard Navigation & Mobile Responsive:**
   - Check desktop sidebar layout and mobile viewports (< 768px).
   - Test "Skip to content" keyboard accessibility.
4. **Agent Lifecycle & One-Time Key Display:**
   - Open `/app/agents`.
   - Click "Register agent", supply name and description.
   - Confirm raw API key `agk_...` modal renders with copy button.
   - Dismiss modal; verify key is never redisplayed in plain text.
5. **Spending Policy Management:**
   - Navigate to `/app/policies`.
   - Update transaction limit, approval threshold, and merchant rules.
   - Save policy and assert backend confirms version increment.
6. **Non-Executing Simulation:**
   - Open `/app/simulate`.
   - Run simulated scenarios (routine payment, limit exceeded, suspicious merchant).
   - Verify that NO executable payment claim is generated.
7. **Approval Lifecycle & Concurrency:**
   - Submit spend request requiring approval.
   - Review pending approval under `/app/approvals`.
   - Test simultaneous/duplicate approval actions; assert server-side idempotency.
8. **Audit Trail Verification:**
   - Open `/app/audit`.
   - Inspect event list (`spend_request.received`, `decision.made`, `approval.requested`).
   - Run audit verification check to confirm SHA-256 hash chain validity.
9. **Session Expiry & Logout:**
   - Invalidate session cookie or simulate 401 response.
   - Assert `agentgate:session-expired` event redirects to `/login`.

---

## 5. Security & Payment Invariants for Playwright Tests
- **Zero Real Provider Calls:** `PAYMENT_EXECUTOR` must always be `fake`. Never inject live PayPal client credentials.
- **Authoritative Backend:** Front-end validations must not bypass server-side rules.
- **Append-only Audit:** Verify no update or delete mutations can succeed on audit records.
