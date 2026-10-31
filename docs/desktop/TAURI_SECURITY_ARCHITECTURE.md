# AgentGate Desktop — Tauri v2 Security Architecture

Status: architecture for Tech Lead review. No authentication behavior changes are implemented by this document.

## 1. Existing authentication contracts

### 1.1 Dashboard (human) authentication

- Mechanism: Django session cookies + allauth Headless browser JSON API. No JWT, no OAuth for dashboard users.
  - `backend/config/settings/base.py:197-201`: `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`; `CSRF_COOKIE_HTTPONLY = False`, `CSRF_COOKIE_SAMESITE = "Lax"`.
  - `backend/apps/agents/authentication.py:14-24`: `DashboardSessionAuthentication(SessionAuthentication)` returns 401 (not 403) for unauthenticated users and enforces CSRF.
- Login/logout and registration go through allauth Headless endpoints under `/api/auth/headless/browser/v1` (see `frontend/src/api/auth.ts:16`).
- Frontend primes CSRF via `bootstrapCsrf()` (`frontend/src/api/auth.ts:58-62`) GET `/config`, then sends `X-CSRFToken` read from the `csrftoken` cookie with `credentials: "include"` (`frontend/src/api/auth.ts:64-90`).
- Session state is probed with `GET /auth/session` (`frontend/src/api/auth.ts:92-98`).

### 1.2 Agent (machine) authentication

- `backend/apps/agents/authentication.py:44-80`: `AgentKeyAuthentication` — `Authorization: Bearer <agent key>`, prefix lookup + constant-time hash check, revocation and active-agent checks, last-used throttling.
- Used by spend submission (`backend/apps/spend/views.py:33-35`: `authentication_classes = [AgentKeyAuthentication]`).

### 1.3 MFA

- Django-allauth MFA (TOTP + recovery codes): `backend/config/settings/base.py:264-294`.
- `MFA_TRUST_ENABLED = False` (no trust devices), `MFA_TOTP_TOLERANCE = 0`, `MFA_RECOVERY_CODES_SHOW_ONCE = True`.
- `backend/apps/accounts/permissions.py:64+`: `IsMFAEnforced`, `MFAEnrollmentRequired` (403 with `mfa_enrollment_required` code) gate privileged roles.
- MFA secrets encrypted at rest with Fernet (`MFA_ENCRYPTION_KEY`).
- Security events logged (MFA challenge success/failure) via `agentgate.security` logger.

### 1.4 Authorization and organization scoping

- Roles: `OrgMembership.Role` = admin / approver / viewer (`backend/apps/accounts/models.py:34-38`).
- `backend/apps/accounts/permissions.py`: `IsDashboardUser`, `IsApprover` (admin/approver), `IsOrganizationAdmin`, with MFA enrollment required for privileged roles.
- `backend/apps/spend/views.py:17-23`: `spend_queryset(user)` filters `SpendRequest` by `organization__memberships__user=user` — organization scoping enforced server-side.

### 1.5 Financial actions

- Spend submission requires `Idempotency-Key` header (validated in `backend/apps/spend/views.py:46-53` and `backend/apps/spend/idempotency.py`).
- Idempotency conflict / policy-missing handled with 409.
- Approvals: `backend/apps/approvals/views.py` `_decide` requires authenticated approver.
- Webhook processing is backend-only (PayPal webhooks handled server-side; not in frontend).

### 1.6 Frontend session handling

- `frontend/src/session/SessionProvider.tsx`: holds agent key and recent requests in React state only — no persistent token storage.
- `frontend/src/App.tsx`: no client-side route guards; backend 401s are the enforcement point.
- Spend requests use agent key as `Authorization: Bearer` (`frontend/src/api/spendRequests.ts:70-76`).

## 2. Desktop threat model

| # | Threat | Severity | Likelihood | Notes |
|---|---|---|---|---|
| T1 | Token/agent-key theft from local storage | High | Medium | Agent keys are bearer tokens; if persisted insecurely, full agent impersonation. |
| T2 | XSS in WebView | High | Medium | React renders untrusted content; CSP currently `null` in generated config (must be hardened). |
| T3 | Native IPC abuse | Medium | Low | Capabilities must be minimal; deny shell/fs by default. |
| T4 | Malicious deep links | Medium | Low | No deep-link handler needed for MVP; avoid registering. |
| T5 | External browser redirects / phishing | Medium | Medium | System-browser login requires validated callback. |
| T6 | CSRF on session cookie | Medium | Low | `SameSite=Lax` + CSRF token; desktop origin is `tauri://localhost`, backend on localhost. |
| T7 | Session expiration / logout | Low | Medium | Must clear local state on 401. |
| T8 | MFA bypass/replay | High | Low | Backend enforces MFA for privileged roles; desktop must not cache MFA state. |
| T9 | Unauthorized org switching | Medium | Low | Org scoping is server-side; desktop must not claim org authority. |
| T10 | Financial replay / duplicate submission | High | Medium | Idempotency keys must be generated once per intent and not auto-retried. |
| T11 | Update/package tampering | High | Low | Updater must verify signatures; not needed for MVP (manual install). |
| T12 | Local logs/crash reports leaking secrets | Medium | Medium | Never log agent keys, session cookies, or MFA secrets. |

## 3. Recommended authentication architecture

**Choose Option A: Backend session cookies**, reused as-is.

Rationale:
- The existing backend is session-cookie + CSRF based for dashboard users. Reusing it avoids introducing JWT/OAuth/refresh tokens, which would require new backend endpoints and key management.
- Tauri's WebView supports cookies for `http://localhost` backends via `credentials: "include"`, matching the existing SPA contract.
- No new authentication mechanism is introduced.

Required Tauri behavior:
- The desktop frontend continues to call `bootstrapCsrf()` and `headlessFetch(..., { credentials: 'include' })` exactly as the web SPA does.
- Backend must be reachable at a stable origin (e.g. `http://127.0.0.1:8000`) in desktop dev; for packaged apps, either bundle/run the backend locally or require the user to point at a backend URL. Default: local backend on 127.0.0.1:8000.
- Session cookie attributes remain `HttpOnly`, `SameSite=Lax`. Desktop origin is `tauri://localhost` (opaque origin); backend on `http://127.0.0.1:8000` is cross-origin for cookies but `SameSite=Lax` applies to top-level navigations; fetch with `credentials: include` is permitted because backend CORS/CSRF must allow the desktop origin. See required backend changes below.

### Required minimal backend changes (if any)

1. CORS: allow the desktop origin (`tauri://localhost`, and `https://tauri.localhost` on Windows) in `CORS_ALLOWED_ORIGINS` / Django `CSRF_TRUSTED_ORIGINS`. Currently none configured (grep shows no CORS settings in base.py). Add `CSRF_TRUSTED_ORIGINS` including the desktop origins so session+CSRF works cross-origin. This is the only backend change required for desktop auth.
2. Optionally: a settings toggle `DESKTOP_ALLOWED_ORIGINS` env var to avoid hard-coding.
3. No new token endpoints, no JWT, no OAuth.

### Why not B or C

- B (short-lived access tokens + native secure storage): requires new backend token issuance/refresh endpoints and a secure storage plugin — over-engineering relative to the existing session contract.
- C (system-browser login + callback): useful later for SSO/OAuth, but the backend has no OAuth callback for dashboard users; adds redirect complexity without benefit. Defer.

## 4. Trust boundaries

- Backend (Django) is the sole authorization authority. Desktop is an untrusted client.
- Native layer (Tauri) must not elevate privileges: no shell, no arbitrary fs, no auto-updater without signature verification.
- Agent keys are user-supplied at runtime and held in React state only; never persisted to disk or logged.
- Session cookies are managed by the WebView cookie jar; desktop code never reads `sessionid` (HttpOnly). Only `csrftoken` is readable (by design, for CSRF header).

## 5. Native permissions (minimum)

Current capabilities/default.json uses `core:default` only. Keep it minimal:
- `core:default` (window management, basic events) — sufficient.
- No `shell`, `fs`, `http` (native), `updater`, `deep-link`, `notification`, `clipboard` plugins unless a concrete feature requires them.
- If backend HTTP is needed from Rust (not the case — WebView fetch suffices), use `tauri-plugin-http` with a strict allowlist; otherwise deny.
- Secure native storage: not needed (agent keys stay in memory; session cookie in WebView jar). Revisit if offline credential caching is required.
- Updater: not needed for MVP; if added later, require signed updates and a trusted endpoint.
- Deep links: not needed for MVP.

### CSP (production)

Already set in `frontend/src-tauri/tauri.conf.json`:
`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' http://127.0.0.1:8000 http://localhost:8000; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`.

Notes:
- `unsafe-inline` for styles is required by Vite/React runtime; keep scripts strict (`'self'` only).
- `connect-src` restricted to local backend. If a remote backend is supported, add it explicitly (no wildcards).
- `freezePrototype: true` enabled.

## 6. Session lifecycle

1. App start: call `bootstrapCsrf()`; on failure show "backend unreachable".
2. Authenticated probe: `getSession()`; redirect to login on 401.
3. On any 401 from a protected endpoint: clear in-memory session state and route to login.
4. Logout: call allauth logout endpoint; clear React state; WebView cookie cleared by backend (`Set-Cookie` expiry).
5. Session expiry: backend `SESSION_COOKIE_AGE` (Django default 2 weeks) governs; desktop does not extend sessions.

## 7. MFA flow

- Desktop delegates entirely to allauth Headless MFA endpoints; no MFA state cached locally.
- Privileged actions (approvals, policy edits) are gated server-side by `IsMFAEnforced`/`MFAEnrollmentRequired` (`backend/apps/accounts/permissions.py`).
- Desktop must surface `mfa_enrollment_required` (403 code) and prompt enrollment; never attempt to bypass.
- MFA trust devices disabled (`MFA_TRUST_ENABLED = False`); desktop must not implement "remember this device".
- Replay protection: `MFA_TOTP_TOLERANCE = 0`; desktop must not retry a failed TOTP code.

## 8. Financial-action boundaries

- Django remains sole authorization authority; desktop never computes decisions.
- MFA cannot be bypassed by desktop requests (server-enforced).
- Desktop never stores PayPal client credentials (none are shipped; backend holds them).
- Checkout capture and payout submission are backend-only (webhooks + services); desktop only submits spend requests via agent key with `Idempotency-Key`.
- Desktop must not auto-retry ambiguous financial POSTs (network timeout on POST → surface error, let user decide).
- Idempotency keys generated once per user intent; reused only on explicit retry of the same request.
- Webhook processing remains backend-only.

## 11. TAURI-07A: Desktop session authentication compatibility proof

### 11.1 Actual runtime origins

| Context | Frontend origin | Backend origin | Relationship |
|---|---|---|---|
| Vite dev | `http://localhost:5173` | `http://127.0.0.1:8000` (proxied via Vite `/api`, `/v1`) | Same-origin from browser perspective (Vite proxy); backend sees `Origin: http://localhost:5173` |
| Tauri dev WebView | `http://localhost:5173` (devUrl) | `http://127.0.0.1:8000` | Same as Vite dev |
| Packaged Tauri (Linux) | `tauri://localhost` | `http://127.0.0.1:8000` | **Cross-origin and cross-site** |
| Packaged Tauri (Windows) | `https://tauri.localhost` | `http://127.0.0.1:8000` | **Cross-origin and cross-site** |

`tauri.conf.json` build.devUrl = `http://localhost:5173`; production serves `frontendDist` (`../dist`) over the `tauri://` protocol.

### 11.2 Cookie compatibility findings

- `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE=Lax`, `CSRF_COOKIE_HTTPONLY=False`, `CSRF_COOKIE_SAMESITE=Lax` (`base.py:197-201`).
- In **dev** (Tauri dev WebView origin `http://localhost:5173`), requests are same-origin via the Vite proxy, so `SameSite=Lax` cookies are sent and CSRF works. Compatible.
- In **packaged** Tauri (origin `tauri://localhost`), the backend (`http://127.0.0.1:8000`) is cross-site. `SameSite=Lax` cookies are **not** sent on cross-site subresource requests (fetch/XHR), so the session cookie will not accompany credentialed fetches. `CSRF_TRUSTED_ORIGINS` alone does **not** fix this — it only permits the CSRF check to pass; it cannot make the browser send a `SameSite=Lax` cookie cross-site.
- `Secure` is not set (dev HTTP). Setting `SameSite=None` would require `Secure=True` and HTTPS, which `tauri://localhost` is not. Weakening `SameSite` to `None` without HTTPS is not acceptable and is not pursued.
- Conclusion: the existing session-cookie architecture works in **dev** but **fails in the packaged app** unless the API is same-origin.

### 11.3 CSRF/CORS findings

- No `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` configured in `base.py` today.
- Required for dev (and any cross-origin packaging): add desktop origins to `CSRF_TRUSTED_ORIGINS`. For packaged, this alone is insufficient (see 11.2); a same-origin proxy is required.
- No wildcard-with-credentials. Desktop origins must be enumerated explicitly.

### 11.4 Local test evidence (same-origin dev contract)

Controlled proof against the local Django dev server (PostgreSQL `agentgate` DB, disposable user `desktop-proof@example.com`, ephemeral creds, no PayPal):

1. CSRF bootstrap `GET /api/auth/headless/browser/v1/config` -> **200**, `csrftoken` cookie present. ✓
2. Login `POST /auth/login` -> **200**. ✓
3. Authenticated `GET /auth/session` -> **200**, `is_authenticated: true`. ✓
4. CSRF-protected `POST /account/password/change` -> **200**. ✓
5. Logout `DELETE /auth/session` -> **401** (session invalidated; session cookie cleared by backend). ✓
6. Post-logout `GET /auth/session` -> **401**. ✓

Evidence: Django dev server logs and urllib/curl runs (2026-10-31). No secrets logged. No production or PayPal access.

### 11.5 Authentication strategy recommendation (TAURI-07)

Given 11.2, the chosen implementation path is **A. Same-origin local API proxy**:

- Serve the Django API behind the same origin as the packaged frontend. Options: (a) run Django as a Tauri sidecar on `http://127.0.0.1:<port>` and have the WebView treat it as same-origin via a custom protocol / reverse proxy, or (b) use Tauri's `tauri://localhost` asset protocol with a registered `http` handler that proxies `/api` and `/v1` to the local backend so the browser sees same-origin requests.
- This keeps `SameSite=Lax` + HttpOnly session cookies and CSRF intact — no cookie security weakening.
- Backend changes: only `CSRF_TRUSTED_ORIGINS` for the desktop origin as defense-in-depth; no new auth endpoints.
- Alternative B (secure backend-supported desktop flow) and C (system-browser callback) are deferred; only pursue if the same-origin proxy proves infeasible on a target platform.

### 11.6 Security risks

- Packaged app cannot authenticate today without the same-origin proxy (cross-site `SameSite=Lax` blocks session cookie on fetch).
- `unsafe-inline` styles in CSP (required by Vite/React) — keep scripts strict.
- Agent keys in React state only; ensure no persistence or logging.
- No auto-retry on financial POSTs.

### 11.7 Required backend/frontend changes

- Backend: `CSRF_TRUSTED_ORIGINS` += desktop origins; optional `DESKTOP_ALLOWED_ORIGINS` env toggle.
- Frontend/Tauri: register same-origin proxy for `/api` and `/v1` in packaged mode; reuse existing `bootstrapCsrf`/`headlessFetch`.
- No auth code changes.

### 11.8 Updated security acceptance criteria

- [ ] Same-origin proxy verified in packaged Linux build (session cookie sent on fetch).
- [ ] CSRF bootstrap + login + authenticated GET + CSRF POST + logout + 401 all pass in packaged app.
- [ ] No `SameSite=None` or CSRF disablement introduced.
- [ ] `CSRF_TRUSTED_ORIGINS` includes desktop origins.
- [ ] Capabilities remain `core:default`.
- [ ] No secrets in logs/crash reports.

## 9. Security acceptance criteria

- [ ] CSP applied in both dev and prod builds (verified via tauri.conf).
- [ ] Capabilities remain `core:default` (or narrower) unless a feature justifies an addition.
- [ ] No shell/fs/http-native plugins without documented need.
- [ ] No agent key or session cookie in logs/crash reports.
- [ ] No auto-retry on financial POSTs.
- [ ] Backend `CSRF_TRUSTED_ORIGINS` includes desktop origins before release.
- [ ] MFA enforcement verified end-to-end on desktop.

## 10. Implementation sequence

1. Add `CSRF_TRUSTED_ORIGINS` (and CORS if needed) for desktop origins in backend settings (minimal change).
2. Verify session login/logout + CSRF on desktop dev build.
3. Add frontend route guard that redirects to login on 401 (optional enhancement).
4. MFA enrollment/verification smoke test on desktop.
5. Spend request submission + approval flow smoke test with idempotency.
6. Security review of logs and CSP in packaged build.
7. Updater/signing decision (deferred).

No push. Architecture report ready for Tech Lead review.
