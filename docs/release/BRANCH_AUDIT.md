# AgentGate Branch Audit

Audit performed: 2026-11-10
Repository: `Root-node1/agent-gate`
Working tree: `/home/winst/agent-gate` (HEAD detached at `ce28f99`, then `release/v0.1.0-ux-demo`)

## Key finding

**`origin/main` is NOT the latest.** The local `main` branch (commit `ce28f99`) is 50 commits ahead of `origin/main` (`6bce121`). `origin/main` is missing the entire PayPal integration, dashboard auth, desktop release pages, and all supporting documentation. All valuable completed work already exists in local `main`.

`release/v0.1.0-ux-demo` and `feat/dashboard-auth-integration` are both **direct ancestors** of local `main` — their work is already fully integrated.

## Branch table

| Branch | Purpose | Unique work | Already integrated? | Status | Recommended action |
|---|---|---|---|---|---|
| `main` (local) | Canonical release target | Full PayPal + auth + desktop + docs | n/a | Complete, verified by prior merge | Target of this release |
| `origin/main` | Remote canonical | Stale (PR #13) | No — 50 commits behind local `main` | Superseded | Do not push to; use local `main` |
| `release/v0.1.0-ux-demo` | UX release candidate | Desktop release pages, Windows CI, installer checksums | Yes — ancestor of local `main` | Complete | Re-create from `main` as integration staging |
| `release/v0.1.0-integrated` | Integrated release | Dashboard auth + PayPal fixes | Yes — ancestor of local `main` | Complete | Historical; already merged into `main` |
| `feat/dashboard-auth-integration` | Dashboard auth + security settings | Auth contract endpoints, Security settings page, TOTP/recovery UI | Yes — ancestor of local `main` | Complete | Already integrated |
| `feat/dashboard` | Frontend dashboard | Landing/dashboard/auth pages | Yes — integrated via `integration/agentgate-dashboard` → `main` | Complete | Already integrated |
| `feat/totp-2fa` | MFA security event logging | Privacy-safe MFA logging | Yes — ancestor of `main` | Complete | Already integrated |
| `feat/auth-foundation` | Session auth foundation | Session auth | Yes — ancestor of `main` | Complete | Already integrated |
| `feat/account-recovery` | Account recovery | Recovery contract + tests | Yes — ancestor of `main` | Complete | Already integrated |
| `feat/backend-crud` | Immutable merchant rule / versioned policy CRUD | CRUD contracts | Yes — ancestor of `main` | Complete | Already integrated |
| `feat/background-jobs` | Idempotent approval expiration | Background scheduling | Yes — ancestor of `main` | Complete | Already integrated |
| `feat/paypal-sandbox` | Sandbox PayPal env prep | Isolated sandbox docs | Yes — ancestor of `main` | Complete | Already integrated |
| `feat/github-oauth` | GitHub OAuth backend | OAuth flow | Yes — ancestor of `main` | Complete | Already integrated |
| `feat/gemini-chatbot` | Gemini chatbot | Merge of github-oauth | Yes — ancestor of `main` | Complete | Already integrated |
| `feat/dashboard-integration` | Org-scoped dashboard spend list | Spend list | Yes — ancestor of `main` | Complete | Already integrated |
| `feat/request-detail` | Approval/denial request detail | Mock-data request detail | Yes — ancestor of `main` | Complete | Already integrated |
| `desktop-tauri` | Tauri desktop architecture | Loopback transport, security hardening | Yes — ancestor of `main` | Complete | Already integrated |
| `ci/postgres-service` | PostgreSQL CI | DB from `DATABASE_URL` | Yes — ancestor of `main` | Complete | Already integrated |
| `audit/agentgate-predeployment-readiness` | Security audit | Zod vuln fix | Yes — ancestor of `main` | Complete | Already integrated |
| `integration/agentgate-dashboard` | Main integration reconciliation | PayPal config contracts, IDOR tests, CI triggers | Yes — ancestor of `main` | Complete | Already integrated |
| `integration/auth-crud` | Auth + CRUD compatibility tests | Integration tests | Yes — ancestor of `main` | Complete | Already integrated |
| `intergration` | Frontend dependency remediation | npm audit fixes | Yes — ancestor of `main` | Complete | Already integrated |
| `infra/contabo-deployment` | Contabo infra | Merge of github-oauth | Yes — ancestor of `main` | Complete | Already integrated |
| `backup/feat-dashboard-local` | Backup of dashboard | Duplicate of `feat/dashboard` | Yes | Superseded | Do not merge |
| `merge` | Local merge scratch | PR #6 merge | Yes — ancestor of `main` | Superseded | Do not merge |
| `agt-018-integrate-main-commits` | Backend main integration | Backend commits | Yes — ancestor of `main` | Complete | Already integrated |
| `agt-019-integrate-frontend` | Frontend integration | ResetPasswordPage fix | Yes — ancestor of `main` | Complete | Already integrated |
| `agt-020-integrate-paypal` | PayPal integration | PayPal commits | Yes — ancestor of `main` | Complete | Already integrated |

## Verdict

No branch requires merging. Local `main` already contains every required completed work. The release task reduces to: verify `main`, fix the two known defects (Cloudflare deploy config, PostgreSQL TOTP failure), test, and deploy.