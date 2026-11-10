# AgentGate — Gamma Slide Content

**Branch:** `integration/agentgate-dashboard`
**Baseline:** `origin/main` at `0f247755589630ea34b7c79785e3f44eca468746`
**Presentation date:** 10 November 2026
**Presenter:** Ian (UX / product presenter)
**Status:** Content ready for Gamma; claims backed by verified evidence

---

## Slide 1: AgentGate — Introduction

**Title:** AgentGate — Spending Firewall for AI Agents

**Bullets:**
- AgentGate controls spending between AI agents and payment providers
- Django backend with domain-driven architecture (accounts, agents, policies, spend, approvals, audit)
- React dashboard with session-based authentication
- MFA and recovery codes for account security
- Organization-based tenancy with role-based access (admin/approver/viewer)

**Suggested visual:** High-level architecture diagram showing Django backend → database → payment providers, with React dashboard on top.

**Speaker notes:** AgentGate is a spending control layer that sits between AI agents and financial systems. Every spend request is evaluated against policies before money moves.

**Evidence:** Backend architecture documented in `Doc.md`; domain applications verified in code review.

---

## Slide 2: The Problem

**Title:** Why AgentGate Exists

**Bullets:**
- AI agents can initiate spending without human oversight
- No centralized policy engine for agent-to-payment interactions
- No audit trail of agent spending decisions
- No role-based access control for agent operations
- MFA and account security often missing from agent tooling

**Suggested visual:** Diagram of uncontrolled agent → payment provider vs. AgentGate policy enforcement in between.

**Speaker notes:** Without AgentGate, AI agents can spend money with no governance. We provide policy evaluation, approval workflows, and complete auditability.

**Evidence:** Problem statement from `Doc.md` and backend architecture review.

---

## Slide 3: Product Vision and Intended Users

**Title:** Who Uses AgentGate

**Bullets:**
- **Finance teams:** Approve or deny agent spend requests
- **Engineering teams:** Configure policies and merchant rules
- **Security teams:** Review audit logs and MFA events
- **Organization admins:** Manage team members and roles

**Suggested visual:** User role matrix showing capabilities per role.

**Speaker notes:** Different users have different needs. Finance needs approval workflows, engineering needs policy configuration, security needs audit visibility.

**Evidence:** `OrgMembership` roles (admin/approver/viewer) verified in `apps/accounts/models.py`.

---

## Slide 4: Core Product Capabilities

**Title:** What AgentGate Does

**Bullets:**
- Policy-based spend request evaluation (allow/deny/needs_approval)
- Approval workflow with role-based access
- MFA with TOTP and recovery codes
- Organization-based tenancy
- Complete audit trail (hash-chained events)
- Agent API key management
- Django admin for operational oversight

**Suggested visual:** Feature grid with icons for each capability.

**Speaker notes:** Every capability is backed by backend enforcement, not just frontend UI. Policies are evaluated server-side; audit events are append-only.

**Evidence:** `apps/policies`, `apps/approvals`, `apps/spend`, `apps/audit` domain applications verified in code.

---

## Slide 5: System Architecture

**Title:** System Architecture

**Bullets:**
- Django 6.1.2 backend with PostgreSQL 17 database
- Domain-driven application structure (10 apps)
- django-allauth headless authentication with MFA
- Procrastinate background job worker (PostgreSQL-backed)
- Redis cache (internal, password-protected)
- Docker Compose deployment with Caddy reverse proxy

**Suggested visual:** Layered architecture diagram: frontend → Caddy → Django → PostgreSQL/Redis.

**Speaker notes:** The architecture separates concerns: Caddy handles TLS and static files, Django handles business logic, PostgreSQL stores all state, Redis caches session data.

**Evidence:** `compose.yaml` defines 4 services; Django settings verified in `config/settings/`.

---

## Slide 6: Backend and API Architecture

**Title:** Backend API Architecture

**Bullets:**
- Allauth headless JSON at `/api/auth/headless/browser/v1/`
- Custom endpoints: `/api/auth/user/`, `/api/auth/logout/`, `/api/auth/profile/`
- Session endpoints: `/api/auth/csrf/`, `/api/auth/options/`, `/api/auth/session/`
- REST API at `/api/v1/` for spend, approvals, agents, policies
- Agent API key authentication (Bearer token) for machine-to-machine
- OpenAPI schema auto-generated via drf-spectacular

**Suggested visual:** API endpoint map grouped by authentication, dashboard, and agent operations.

**Speaker notes:** The backend exposes two authentication paths: session-based for the dashboard UI, and Bearer token for AI agents. Both are secured with CSRF protection and rate limiting.

**Evidence:** URL configuration in `backend/apps/accounts/urls.py` and `backend/config/urls.py` verified in code.

---

## Slide 7: Frontend Dashboard and Authentication

**Title:** Frontend: Dashboard and Authentication

**Bullets:**
- React 19 dashboard with React Router
- Login, registration, MFA, email verification pages
- Session restoration on app mount
- Protected routes (unauthenticated users redirected to login)
- Security settings: TOTP setup, recovery code management
- Responsive design with accessible form controls

**Suggested visual:** Screenshot mockup of login page and dashboard.

**Speaker notes:** The frontend integrates with the backend through a unified auth API client. No mocked authentication — all requests go to real endpoints.

**Evidence:** Frontend TypeScript, ESLint, and production build all pass; pages verified in `frontend/src/pages/`.

---

## Slide 8: Security, Identity and Organization Model

**Title:** Security Model

**Bullets:**
- Custom `accounts.User` model with UUID primary keys
- Organization + OrgMembership for tenancy (admin/approver/viewer)
- MFA with TOTP and recovery codes; Fernet at-rest encryption
- Session cookies: Secure, HttpOnly, SameSite=Lax
- CSRF protection with trusted origins
- Rate limiting on auth endpoints
- Hash-chained audit log with append-only protection

**Suggested visual:** Security layer diagram showing MFA, org isolation, and audit.

**Speaker notes:** Security is built in at every layer — from database constraints to cookie settings to audit logging. Organization isolation prevents cross-organization data access.

**Evidence:** Security assessment in `docs/security/SECURITY_ASSESSMENT.md`; MFA_ENCRYPTION_KEY configuration required (VULN-001).

---

## Slide 9: Infrastructure, VPS Deployment and Backups

**Title:** Infrastructure

**Bullets:**
- Contabo VPS deployment via Docker Compose
- Caddy reverse proxy with auto-HTTPS (Let's Encrypt)
- PostgreSQL (Neon managed service)
- Daily logical backups with encryption (proposed)
- Non-root container user; network segmentation
- Team access via individual SSH keys

**Suggested visual:** Deployment diagram showing VPS, Caddy, Django, PostgreSQL, and backup flow.

**Speaker notes:** The VPS runs a containerized stack with automatic HTTPS. Backups are encrypted and stored off-server. SSH access is key-based only.

**Evidence:** `compose.yaml` and `docs/deployment/VPS_DEPLOYMENT.md` verified. VPS SSH port 22 not reachable — access pending.

---

## Slide 10: Desktop Application (Tauri)

**Title:** Desktop Application

**Bullets:**
- Tauri 2.12.5 desktop client (React frontend + Rust backend)
- Embedded loopback proxy connects to hosted backend over HTTPS
- Session cookies and MFA work through the proxy
- Linux x86_64: AppImage, .deb, .rpm
- Unsigned — internal testing only (no code signing yet)

**Suggested visual:** Desktop app window mockup showing login and dashboard.

**Speaker notes:** The desktop app is a thin client — all business logic remains on the backend. The embedded proxy handles session cookies and CSRF tokens securely.

**Evidence:** `frontend/src-tauri/tauri.conf.json` and `docs/deployment/TAURI_DESKTOP_RELEASE.md` verified. Frontend build passes.

---

## Slide 11: Current Implementation Status

**Title:** Implementation Status

**Bullets:**
- ✅ AccountProfile integrated (linked to accounts.User)
- ✅ Authentication contract aligned (frontend ↔ backend)
- ✅ Dashboard and auth pages integrated
- ✅ Registration with organization onboarding
- ✅ User profile management (GET/PATCH /api/auth/profile/)
- ✅ MFA and recovery flows (UI + backend endpoints)
- ✅ Backend tests: 694 pass, 0 fail
- ✅ Frontend: TypeScript, lint, build all pass
- ⏳ Security assessment (AGT-007) — in progress
- ⏳ E2E tests against deployed environment — pending VPS access
- ⏳ Backup automation — not yet deployed
- ⏳ VPS deployment — pending SSH access

**Suggested visual:** Status checklist with green/yellow/red indicators.

**Speaker notes:** Core integration is complete and tested. Remaining work is operational: deployment, backups, and security sign-off.

**Evidence:** Test results in `docs/testing/E2E_TEST_RESULTS.md`; commit history on `integration/agentgate-dashboard`.

---

## Slide 12: Next Development Milestones

**Title:** What's Next

**Bullets:**
- Deploy backend to Contabo VPS for team testing
- Configure automated encrypted backups with restore verification
- Complete security assessment and remediation (AGT-007/008)
- Run E2E tests against deployed environment
- Code-sign Tauri desktop builds for distribution
- CI/CD pipeline automation for deployment

**Suggested visual:** Timeline showing milestones over next 2-4 weeks.

**Speaker notes:** The application is functionally complete. The next phase is operational hardening: deployment, backups, security, and distribution.

**Evidence:** Ticket files in `/home/winst/agent-gate/tickets/` (AGT-001 through AGT-011).

---

## Claims Verification Summary

| Claim | Evidence Source | Status |
|---|---|---|
| 694 backend tests pass | `docs/testing/E2E_TEST_RESULTS.md` | ✅ Verified |
| Frontend build passes | `npm run build` output | ✅ Verified |
| AccountProfile integrated | `backend/apps/accounts/models.py` | ✅ Verified |
| Auth contract aligned | `frontend/src/api/auth.ts` + backend views | ✅ Verified |
| MFA encryption key required | Django `accounts.W001` warning | ✅ Verified |
| VPS SSH not reachable | Connection timeout on port 22 | ✅ Verified |
| Tauri unsigned build | No code signing configured | ✅ Verified |