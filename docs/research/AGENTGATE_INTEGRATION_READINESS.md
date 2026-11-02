# AgentGate Integration Readiness Audit

**Task:** AG-01 — Worktree, Branch and Integration Readiness Audit
**Mode:** Read-only audit (single report created)
**Repository:** `Root-node1/agent-gate` (git@github.com:Root-node1/agent-gate.git)
**Audit branch:** `intergration` (exact spelling)
**Audit date:** 2026-11-01
**Auditor:** Kilo (automated)

> Verified facts are stated as such. Assumptions and limitations are explicitly flagged.

---

## 1. Worktree / Branch Inventory

### 1.1 Repository root

- `git rev-parse --show-toplevel` → `/home/winst/agent-gate/.kilo/worktrees/intergration` (the current worktree is the integration worktree).
- The canonical bare/clone root is `/home/winst/agent-gate` (worktree on `audit/agentgate-predeployment-readiness`).
- Remote: `origin` → `git@github.com:Root-node1/agent-gate.git` (fetch + push).

### 1.2 Worktrees (17 total)

| # | Path | Branch / HEAD | HEAD (full) | Upstream | A/B | Status |
|---|---|---|---|---|---|---|
| 1 | `/home/winst/agent-gate` | `audit/agentgate-predeployment-readiness` | `4c021d042df3e31cb043746bef67eaa9b243c254` | `origin/audit/agentgate-predeployment-readiness` | 0/0 | Dirty — untracked `package.json`, `package-lock.json` |
| 2 | `/home/winst/.local/share/kilo/worktree-pool/agent-gate-7307b6af2040/better-gibbon` | detached HEAD | `bc6987ece9ce1215c41295ea7bb4daa056f11f51` | (none) | — | Clean |
| 3 | `/home/winst/agent-gate/.kilo/worktrees/desktop-tauri` | `desktop-tauri` | `6775c8df38484a748a6b11f346a0b3d428f150e0` | (none) | — | Clean |
| 4 | `/home/winst/agent-gate/.kilo/worktrees/feat-account-recovery-3f7b03f85e52a554` | `feat/account-recovery` | `801bda0dd6db0322cec665c23e19d5970375fbb5` | (none) | — | Clean |
| 5 | `/home/winst/agent-gate/.kilo/worktrees/feat-auth-foundation-1e8e999a34107b77` | `feat/auth-foundation` | `c35287d4e6fd3c962d3ecae1e4f28aeb6f29290e` | (none) | — | Clean |
| 6 | `/home/winst/agent-gate/.kilo/worktrees/feat-backend-crud-d7120dc7ef61d20b` | `feat/backend-crud` | `00a82d50736f3d28df2a6f322e909521fef786ed` | (none) | — | Clean |
| 7 | `/home/winst/agent-gate/.kilo/worktrees/feat-background-jobs-1dac528fa493d860` | `feat/background-jobs` | `ea173814f0a060e96fe83c5290ddabbeadd56a16` | (none) | — | Clean |
| 8 | `/home/winst/agent-gate/.kilo/worktrees/feat-dashboard-integration-ad49a1fe97eeb2a8` | `feat/dashboard-integration` | `b1c8d84a39a56ca8511c3293a62b8c46cab9c571` | (none) | — | Clean |
| 9 | `/home/winst/agent-gate/.kilo/worktrees/feat-gemini-chatbot-2bb42abd556eaecf` | `feat/gemini-chatbot` | `986cf4a5a88b5782826072e508fbe4b554c2a687` | (none) | — | Clean |
| 10 | `/home/winst/agent-gate/.kilo/worktrees/feat-github-oauth-ef2eb1204fb1af96` | `feat/github-oauth` | `434d87f24a683a02f36112216c5d254711bcd172` | (none) | — | Clean |
| 11 | `/home/winst/agent-gate/.kilo/worktrees/feat-paypal-sandbox-1102e54aa82dee50` | `feat/paypal-sandbox` | `b1a0ee26bd61af04354a5f7a11c126e3af8142b2` | (none) | — | Clean |
| 12 | `/home/winst/agent-gate/.kilo/worktrees/feat-totp-2fa-bcc3872d90d4265e` | `feat/totp-2fa` | `b283719f78015dd2dbe33cde59f2e8f361ec04ac` | `origin/feat/totp-2fa` | 0/0 | Dirty — untracked `AUTH-05B.3C-Final-Report.md`, `AUTH-05B.3D-Final-Report.md` |
| 13 | `/home/winst/agent-gate/.kilo/worktrees/infra-contabo-deployment-31d55c9827d0b411` | `infra/contabo-deployment` | `986cf4a5a88b5782826072e508fbe4b554c2a687` | (none) | — | Clean |
| 14 | `/home/winst/agent-gate/.kilo/worktrees/integration-auth-crud` | `integration/auth-crud` | `3d6fef9679eedb12cb1174ca2e24e199478d948c` | (none) | — | Clean |
| 15 | `/home/winst/agent-gate/.kilo/worktrees/intergration` | `intergration` | `d991f25dbcbf3fc3301aacd0637799cece45561d` | `origin/intergration` | 0/0 | Clean |
| 16 | `/home/winst/agent-gate/.kilo/worktrees/merge` | `merge` | `bc6987ece9ce1215c41295ea7bb4daa056f11f51` | (none) | — | Clean |

Note: `git worktree list --porcelain` reported 16 entries; the detached `better-gibbon` pool entry is included. (Task said 17 total including the audit root; counted 16 distinct worktree entries above — the audit root `/home/winst/agent-gate` is entry #1.)

### 1.3 Local branches (17)

| Branch | HEAD | Upstream | A/B | Notes |
|---|---|---|---|---|
| `audit/agentgate-predeployment-readiness` | `4c021d0` | `origin/audit/...` | 0/0 | Has untracked files in its worktree |
| `ci/postgres-service` | `f9d9ceb` | `origin/ci/postgres-service` | (not reported) | Ancestor of `intergration` |
| `desktop-tauri` | `6775c8d` | (none) | — | **Unique work** — 10 commits ahead of `intergration`, 0 behind |
| `feat/account-recovery` | `801bda0` | (none) | — | Ancestor of `intergration` |
| `feat/auth-foundation` | `c35287d` | (none) | — | Ancestor of `intergration` |
| `feat/backend-crud` | `00a82d5` | (none) | — | Ancestor of `intergration` |
| `feat/background-jobs` | `ea17381` | (none) | — | Ancestor of `intergration` |
| `feat/dashboard-integration` | `b1c8d84` | (none) | — | Ancestor of `intergration` |
| `feat/gemini-chatbot` | `986cf4a` | (none) | — | Ancestor of `intergration` (merge into intergration) |
| `feat/github-oauth` | `434d87f` | (none) | — | Ancestor of `intergration` |
| `feat/paypal-sandbox` | `b1a0ee2` | (none) | — | **Unique work** — 19 commits ahead of `intergration`, 0 behind |
| `feat/totp-2fa` | `b283719` | `origin/feat/totp-2fa` | 0/0 | Ancestor of `intergration`; dirty worktree |
| `infra/contabo-deployment` | `986cf4a` | (none) | — | Ancestor of `intergration` |
| `integration/auth-crud` | `3d6fef9` | (none) | — | Ancestor of `intergration` |
| `intergration` | `d991f25` | `origin/intergration` | 0/0 | **Integration target** |
| `main` | `221a977` | `origin/main` | (behind 4) | Base branch; behind `origin/main` by 4 |
| `merge` | `bc6987e` | (none) | — | Ancestor of `intergration` (== `origin/main`) |

### 1.4 Remote branches (after `git fetch --all --prune`)

| Remote ref | HEAD | Notes |
|---|---|---|
| `origin/HEAD` | → `origin/main` | Default branch is `main` |
| `origin/main` | `bc6987e` | `Merge pull request #6 from .../audit/...` |
| `origin/intergration` | `d991f25` | Synchronized with local |
| `origin/audit/agentgate-predeployment-readiness` | `4c021d0` | |
| `origin/ci/postgres-service` | `f9d9ceb` | |
| `origin/feat/dashboard` | `9d37953` | (`add the accessibility icon...`) |
| `origin/feat/request-detail` | `538ff19` | (`TEST APROVALS AND DENIALS ON MOCK DATA`) |
| `origin/feat/totp-2fa` | `b283719` | |
| `origin/ft-backend` | `1112c9c` | |
| (none) | — | No `origin/desktop-tauri`, no `origin/feat/paypal-sandbox`, no `origin/feat/background-jobs`, etc. — those are local-only branches |

### 1.5 Uncommitted / untracked changes requiring preservation

1. `/home/winst/agent-gate` (audit branch) — untracked `package.json`, `package-lock.json` at the root (not in any worktree's tracked set; likely stray files). **Preserve.**
2. `/home/winst/agent-gate/.kilo/worktrees/feat-totp-2fa-...` — untracked `AUTH-05B.3C-Final-Report.md`, `AUTH-05B.3D-Final-Report.md`. **Preserve.**

All other 14 worktrees are clean.

---

## 2. Unique Commit Analysis

### 2.1 Ancestor classification (vs `intergration`)

All of the following are **ancestors** of `intergration` (verified via `git merge-base --is-ancestor <branch> intergration` = YES). They contain **zero unique commits** relative to `intergration` and require **no action**:

`feat/background-jobs`, `feat/dashboard-integration`, `feat/gemini-chatbot`, `feat/github-oauth`, `feat/account-recovery`, `feat/auth-foundation`, `feat/backend-crud`, `feat/totp-2fa`, `infra/contabo-deployment`, `integration/auth-crud`, `audit/agentgate-predeployment-readiness`, `ci/postgres-service`, `merge`.

### 2.2 Branches with unique work (only two)

#### A. `desktop-tauri` (HEAD `6775c8d`) — 10 commits, 0 behind `intergration`

```
6775c8d docs(desktop): define distribution architecture and release readiness
5bea71a docs(desktop): record linux lifecycle and gui acceptance audit
bf669b3 fix(desktop): harden loopback transport security and add regression tests
4fe8b2a feat(desktop): implement embedded loopback transport for packaged auth
2997ab0 docs(desktop): validate packaged desktop auth transport
10d0eb4 docs(desktop): validate tauri session authentication compatibility
b6adc5c docs(desktop): define secure tauri authentication architecture
1fe9574 Merge branch 'intergration' into desktop-tauri
7838722 chore(desktop): ignore src-tauri build artifacts in ESLint
915557a feat(desktop): initialize Tauri v2 project with secure defaults
```

- Includes a merge commit pulling `intergration` in, so it is based on the latest `intergration` (merge-base = `d991f25`).
- Adds `frontend/src-tauri/` (Rust/Tauri v2 project: `Cargo.toml`, `Cargo.lock`, `tauri.conf.json`, `src/{lib,main,server}.rs`, capabilities, icons) plus `docs/desktop/*`.
- Modifies `frontend/package.json` and `frontend/eslint.config.js` (Tauri deps + ignore build artifacts).
- **No backend changes, no migrations, no config changes.**
- No file overlap with `feat/paypal-sandbox` (verified via `comm`).

#### B. `feat/paypal-sandbox` (HEAD `b1a0ee2`) — 19 commits, 0 behind `intergration`

```
b1a0ee2 docs(payments): prepare isolated paypal sandbox environment
b1f992b fix(payments): verify denied captures before webhook transition
b5271b3 test(payments): cover webhook financial reconciliation safety
396af99 fix(payments): harden webhook financial reconciliation
9551622 feat(payments): process verified sandbox webhooks
59f9090 fix(payments): harden webhook ingestion reliability
3fb440e feat(payments): add verified sandbox webhook ingestion
d229e2d fix(payments): correct payout financial state classification
c748c32 fix(payments): harden sandbox payout submission safety
fbbc477 feat(payments): add sandbox payout submission
01736c2 fix(payments): harden payout reservation concurrency
ccfc896 feat(payments): add durable payout authorization
c7fc185 fix(payments): preserve uncertain checkout capture states
b017bbc feat(payments): add sandbox checkout capture
28969c7 feat(payments): add sandbox checkout order creation
1326b34 fix(payments): verify sandbox client and API hostname
79fb34d feat(payments): add sandbox PayPal OAuth HTTP client
ca9c46c feat(payments): add checkout domain and operation records
50dd3e9 feat(payments): add sandbox-only PayPal feature configuration
```

- No merge commits; linear 19 commits on top of `intergration` (merge-base = `d991f25`).
- Touches **only** `backend/`:
  - `backend/apps/payments/` — expands the minimal payments app (which already has `models`, `executors`, `admin`, `apps`, migration `0001`) with checkout, payouts, paypal client/config, webhook processing/views/service, checks, management commands (`check_paypal_sandbox`, `process_paypal_webhooks`), urls, serializers, and migrations `0002`–`0005`.
  - `backend/apps/audit/migrations/0006_alter_auditevent_event_type.py`.
  - `backend/config/settings/base.py` (PayPal env/credentials/feature flags) and `backend/config/urls.py` (adds `path("v1/", include("apps.payments.urls"))`).
  - `backend/.env.example` (PayPal sandbox block).
  - 10 new test files under `backend/tests/`.

### 2.3 Shared files / conflict risk

- `desktop-tauri` and `feat/paypal-sandbox` share **no files** (verified via `comm -12` on changed-file lists).
- `feat/paypal-sandbox` modifies `backend/config/urls.py` (single additive line) and `backend/config/settings/base.py` (append-only PayPal block). These are append-only changes on top of `intergration`, so a merge from `intergration`'s current state should apply cleanly.
- `feat/paypal-sandbox` adds `audit/migrations/0006_alter_auditevent_event_type.py`; `intergration` has `0005_alter_auditevent_event_type.py` as the latest. No numbering collision.
- `feat/paypal-sandbox` adds `payments/migrations/0002`–`0005` on top of `intergration`'s existing `payments/migrations/0001_initial.py`. Sequential, no collision.
- Potential risk: if `intergration` advances (e.g., new audit migration `0006`) before merging `feat/paypal-sandbox`, the audit migration numbering would collide. **Mitigation:** merge `feat/paypal-sandbox` before any further audit migrations land on `intergration`.

### 2.4 Migration ordering note

`feat/paypal-sandbox`'s migrations must run after `intergration`'s `0005_alter_auditevent_event_type` (audit) and `payments/0001_initial`. Both are present on `intergration`, so ordering is satisfied. No generated files require special handling beyond standard `migrate`.

---

## 3. PayPal Sandbox State (feat/paypal-sandbox branch)

### 3.1 Database isolation

- `backend/.env` exists but is **untracked** (`.gitignore` lists `.env`). ✅ Not committed.
- `DATABASE_URL` in the local `.env` resolves to database name **`agentgate_sandbox`** (verified by parsing the URL's path component only — host/credentials not read or printed). ✅ Isolated.
- `DATABASE_URL` does **not** contain `test_` or `prod`. ✅
- The `.env.example` documents `agentgate_sandbox` as the required isolated database and forbids `test_agentgate` and production databases.

### 3.2 Credentials / secrets (presence only)

| Key | Present in `.env`? | Non-empty? |
|---|---|---|
| `PAYPAL_ENV` | No (defaults to `sandbox` in code) | n/a |
| `PAYPAL_CLIENT_ID` | No | — |
| `PAYPAL_CLIENT_SECRET` | No | — |
| `PAYPAL_WEBHOOK_ID` | No | — |
| `PAYPAL_CHECKOUT_ENABLED` | No (defaults to `false`) | — |
| `PAYPAL_PAYOUTS_ENABLED` | No (defaults to `false`) | — |
| `MFA_ENCRYPTION_KEY` | Yes | **No (empty)** |
| `DATABASE_URL` | Yes | Yes |
| `DJANGO_DEBUG` | Yes | Yes |

- **No live PayPal credentials are configured.** Feature flags default to `false`, so checkout/payout flows are disabled. ✅ Sandbox-only by default.
- `PAYPAL_ENV` defaults to `"sandbox"` in `base.py`; the system check (`apps/payments/checks.py`) rejects any value other than `"sandbox"`. Production endpoints are never configured (constants point at `api-m.sandbox.paypal.com`).
- MFA encryption key is **not set** in the sandbox `.env` — `check_paypal_sandbox` would report `MFA_ENCRYPTION_KEY is not configured`. This is a blocker for running the check locally (see §3.4).

### 3.3 Feature-flag status

- `PAYPAL_CHECKOUT_ENABLED=false` (default), `PAYPAL_PAYOUTS_ENABLED=false` (default). Both disabled. No credentials required in this state. Enabling either requires `PAYPAL_CLIENT_ID` + `PAYPAL_CLIENT_SECRET`.

### 3.4 `check_paypal_sandbox` output (static analysis)

Could not be executed in this audit because:
- The sandbox `.env` has an **empty `MFA_ENCRYPTION_KEY`** (required by the check), and
- No running PostgreSQL instance was reachable with the configured credentials (peer-auth role `winst` does not exist; password auth not available to this session).

Expected output when run with a valid MFA key and `agentgate_sandbox` DB, per the command's logic (`backend/apps/payments/management/commands/check_paypal_sandbox.py`):

```
PayPal Sandbox readiness: OK
WARNING: Both PAYPAL_CHECKOUT_ENABLED and PAYPAL_PAYOUTS_ENABLED are false.
WARNING: CSRF_TRUSTED_ORIGINS is empty.
Database: agentgate_sandbox
No secret values were printed.
```

(With the current empty MFA key it would instead emit `ERROR: MFA_ENCRYPTION_KEY is not configured.` and exit 1.)

### 3.5 Database preservation

Per task requirements, the following databases must be preserved (not enumerated here — this audit did not connect to PostgreSQL due to auth limitations; see §8 limitations). No reset/drop/truncate/migration-rollback was performed.

Databases to preserve: `agentgate`, `agentgate_test`, `agentgate_sandbox`, `paysplit`, `infinite_mushrooms`, `postgres`.

---

## 4. MCP and Teammate Onboarding Inventory

### 4.1 MCP server status

- **No MCP server implementation exists in the repository.** `frontend/src/pages/app/settings/DevelopersSection.tsx` lists "MCP server" under a "Planned" badge alongside "Python and TypeScript SDKs" and "Webhooks".
- MCP is referenced only as a concept in `README.md` and `Doc.md`: provenance (`source=trusted`) is self-reported by the caller, and "the SDK or MCP wrapper must set it from the instruction's actual provenance."
- **Conclusion:** MCP developer onboarding is not yet possible from this repo. There is no entry point, transport, auth, or config example. This is a **gap**, not a bug.

### 4.2 What a teammate needs today (REST API path)

- Clone `Root-node1/agent-gate`, run `./run.sh` (creates venv, `.env`, installs deps, migrates, starts backend :8000 + frontend :5173).
- Requirements: Python 3.13+, Node 22+.
- Backend env: `backend/.env` (copy from `.env.example`); set `DJANGO_SECRET_KEY`. PayPal sandbox credentials added when integration lands.
- API auth: agent keys (`agk_...`) passed as `Authorization: Bearer`. Dashboard uses session auth.
- OpenAPI schema: `GET /api/schema/`; Swagger UI: `/api/docs/`; health: `/api/health/`, `/healthz`, `/readyz`.
- Example curl provided in `frontend/src/pages/app/settings/settingsData` (referenced via `CURL_EXAMPLE`).
- Security boundary: `source` defaults to `untrusted` when missing; all non-trusted sources fail closed.

### 4.3 Gaps for MCP/onboarding

- No MCP server, transport (stdio/SSE), or auth scaffold.
- No SDK (Python/TS) — only raw REST + curl.
- No webhook delivery implementation (planned).
- No pairing codes / access tokens documented for MCP clients (none exist yet).
- Hosted MCP endpoint: none (project is local-first; production target is Contabo per `infra/contabo-deployment`).

---

## 5. API Documentation Inventory

### 5.1 Django URL configuration (`backend/config/urls.py`)

Mounted routes (intergration):
- `admin/` (via `ADMIN_PATH`), `healthz`, `readyz`, `api/health/`
- `api/schema/` (SpectacularAPIView), `api/docs/` (Swagger)
- `accounts/` (allauth patterns + GitHub OAuth), `3rdparty/`, `mfa/`
- `api/auth/headless/`, `api/auth/` (accounts urls)
- `v1/` → spend, approvals, audit, policies, agents
- `api-auth/` (DRF browsable auth)

Note: `apps.payments.urls` is **not** mounted on `intergration` (payments app is minimal). It is added by `feat/paypal-sandbox`.

### 5.2 OpenAPI / Swagger

- `drf_spectacular` is installed and configured (`SPECTACULAR_SETTINGS` in `base.py`).
- Schema is **generated at runtime** via `/api/schema/` (SpectacularAPIView). No committed schema file exists.
- Swagger UI at `/api/docs/`.
- No hand-maintained OpenAPI spec file in the repo.

### 5.3 Postman collection

- File: `docs/postman/AgentGate.postman_collection.json`
- Valid JSON: yes.
- Name: `AgentGate API`; version: `agentgate-api-0.1.0`; schema: Postman Collection v2.1.0.
- 8 top-level items: Health & Readiness, OpenAPI Schema, Dashboard Authentication, Dashboard: Agents, (one unnamed), Dashboard: Approvals, Dashboard: Policies, Dashboard: Audit Log.
- The payments endpoints are not represented (payments app not integrated yet).

### 5.4 API tests

Tests live under `backend/tests/` and `backend/apps/*/` (per-app). `lint-imports` enforces architecture contracts. Not enumerated in detail here.

### 5.5 API contract gaps

- No committed OpenAPI schema (generated only). For teammate/SDK generation, a committed/generated schema artifact would be useful.
- Postman collection version `0.1.0` predates PayPal payments work; will need regeneration after `feat/paypal-sandbox` merges.
- No API versioning beyond the `v1/` prefix.

---

## 6. Integration Dependency Order

Based on ancestor analysis and file overlap:

1. `intergration` is the integration target (already includes all historical feature branches via merges).
2. `feat/paypal-sandbox` (19 commits) — **merge candidate**; depends on `intergration` (already based on it). Adds payments domain + audit migration. Should land before any new audit migration on `intergration`.
3. `desktop-tauri` (10 commits) — **merge candidate**; depends on `intergration`. Adds Tauri desktop shell. Independent of PayPal. Can merge in either order relative to PayPal (no file overlap), but PayPal-first is recommended to keep backend migrations contiguous.

All other branches are ancestors of `intergration` → **already integrated, no action**.

---

## 7. Conflict Risks

- **Low** between the two merge candidates (no shared files).
- **Medium** audit-migration numbering collision if `intergration` gains a new audit migration before PayPal merges (PayPal adds `0006_alter_auditevent_event_type`).
- **Low** config merge: PayPal's `urls.py` change is a single additive line; `base.py` change is an append-only block. Both apply cleanly on top of `intergration`.
- **Untracked files** in two worktrees must be preserved (see §1.5). They are not tracked, so they will not interfere with merges, but must not be deleted.
- `main` is 4 commits behind `origin/main` and 39 behind `intergration` — `main` is stale relative to `intergration`. Not a blocker for this audit but noted for Tech Lead.

---

## 8. Limitations of this audit

- **PostgreSQL not accessible:** peer-auth role `winst` does not exist and no password was available in this session. Databases (`agentgate`, `agentgate_test`, `agentgate_sandbox`, `paysplit`, `infinite_mushrooms`, `postgres`) were **not enumerated or mutated**. Preservation is assumed; no DB operations were performed.
- **`check_paypal_sandbox` not executed** because the sandbox `.env` has an empty `MFA_ENCRYPTION_KEY`. Expected output documented from static analysis of the command.
- **No MCP server exists** — MCP onboarding is a gap, not an implemented feature.
- **No committed OpenAPI schema** — schema is runtime-generated only.

---

## 9. Proposed Integration Sequence

1. (Tech Lead approval) Merge `feat/paypal-sandbox` into `intergration` (fast-forward, 19 commits). Run migrations + `check_paypal_sandbox` with a valid MFA key.
2. (Tech Lead approval) Merge `desktop-tauri` into `intergration` (fast-forward, 10 commits). Verify frontend build + Tauri build.
3. Regenerate Postman collection and commit a generated OpenAPI schema artifact.
4. Push `intergration` to `origin/intergration` (already in sync as of this audit).
5. Decide disposition of the 14 ancestor branches and 2 dirty worktrees (archive only with explicit approval — not done here).

---

## 10. Branch-by-Branch Recommendation

| Branch | Recommendation |
|---|---|
| `desktop-tauri` | **Merge into `intergration`** (fast-forward). Unique Tauri work. |
| `feat/paypal-sandbox` | **Merge into `intergration`** (fast-forward). Unique PayPal sandbox work. |
| `feat/background-jobs` | Already integrated (ancestor). No action. |
| `feat/dashboard-integration` | Already integrated (ancestor). No action. |
| `feat/gemini-chatbot` | Already integrated (ancestor, merged). No action. |
| `feat/github-oauth` | Already integrated (ancestor, merged). No action. |
| `feat/account-recovery` | Already integrated (ancestor, merged). No action. |
| `feat/auth-foundation` | Already integrated (ancestor). No action. |
| `feat/backend-crud` | Already integrated (ancestor). No action. |
| `feat/totp-2fa` | Already integrated (ancestor). No action. (Dirty worktree — preserve reports.) |
| `infra/contabo-deployment` | Already integrated (ancestor, merged). No action. |
| `integration/auth-crud` | Already integrated (ancestor). No action. |
| `audit/agentgate-predeployment-readiness` | Already integrated (ancestor, merged via PR #6). No action. (Dirty worktree — preserve stray package files.) |
| `ci/postgres-service` | Already integrated (ancestor, merged via PR #1). No action. |
| `merge` | Already integrated (== `origin/main`). No action. |
| `main` | Stale (39 behind `intergration`, 4 behind `origin/main`). Tech Lead decision. |
| `feat/dashboard` (remote only) | Remote-only; not an ancestor of `intergration`. Tech Lead decision. |
| `feat/request-detail` (remote only) | Remote-only; not an ancestor. Tech Lead decision. |
| `ft-backend` (remote only) | Remote-only; not an ancestor. Tech Lead decision. |

No branches were archived or deleted in this audit.

---

## 11. Blockers / Decisions Requiring Tech Lead Approval

1. **Merge approval** for `feat/paypal-sandbox` and `desktop-tauri` into `intergration`.
2. **MFA_ENCRYPTION_KEY** must be provisioned for the PayPal sandbox (currently empty in `.env`) before `check_paypal_sandbox` can pass.
3. **PostgreSQL access** for this environment — credentials/role needed to verify/preserve the six named databases.
4. **Disposition of stale branches** (`main`, `feat/dashboard`, `feat/request-detail`, `ft-backend`) and the two dirty worktrees.
5. **MCP server implementation** is entirely unbuilt — scope/ownership decision needed.
6. **Committed OpenAPI schema** — decide whether to commit a generated schema artifact and regenerate the Postman collection.

---

**STOP. Awaiting Tech Lead review before any integration.**
filePath">
/home/winst/agent-gate/.kilo/worktrees/intergration/docs/research/AGENTGATE_INTEGRATION_READINESS.md