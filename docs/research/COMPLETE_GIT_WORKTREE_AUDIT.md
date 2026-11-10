# AgentGate — Complete Git Worktree and Branch Audit

**Audit date:** 2026-11-09
**Repository:** https://github.com/Root-node1/agent-gate.git (SSH: git@github.com:Root-node1/agent-gate.git)
**Canonical repo root:** /home/winst/agent-gate
**Current worktree:** /home/winst/agent-gate/.kilo/worktrees/integration-agentgate-dashboard-2
**Integration baseline:** origin/integration/agentgate-dashboard = f6ad730ca1a07a4f23092fba4315bc9ae8197be0

---

## 1. Repository and Remote Inventory

| Item | Value |
|------|-------|
| Canonical repository root | /home/winst/agent-gate |
| Current working directory | /home/winst/agent-gate/.kilo/worktrees/integration-agentgate-dashboard-2 |
| Remote `origin` (fetch) | git@github.com:Root-node1/agent-gate.git |
| Remote `origin` (push) | git@github.com:Root-node1/agent-gate.git |
| Default branch (origin/HEAD) | origin/main |
| Remote tags | None |

### Remote branches (after `git fetch origin`)

| Remote branch | SHA | Subject |
|---------------|-----|---------|
| origin/audit/agentgate-predeployment-readiness | 4c021d0 | fix(security): update vulnerable Zod dependency |
| origin/ci/postgres-service | f9d9ceb | ci: run backend tests against a PostgreSQL service |
| origin/feat/dashboard | 4e82906 | run and test the reset links |
| origin/feat/request-detail | 538ff19 | TEST APROVALS AND DENIALS ON MOCK DATA |
| origin/feat/totp-2fa | b283719 | feat(auth): add privacy-safe MFA security event logging |
| origin/ft-backend | 7d3bae6 | Fix policy assignment in create_request method |
| origin/integration/agentgate-dashboard | f6ad730 | fix(schema): resolve OpenAPI generation errors |
| origin/intergration | beba6f3 | fix(frontend): remediate npm dependency vulnerabilities |
| origin/main | 6bce121 | Merge pull request #13 from Root-node1/ft-backend |

> **Note:** `origin/main` advanced from `0f24775` to `6bce121` during this audit (17 new commits not in integration). `origin/feat/github-oauth` and `origin/feat/paypal-sandbox` exist on GitHub but were not fetched as remote-tracking refs (only local branches exist for them).

---

## 2. Complete Worktree Inventory

| # | Worktree path | Branch | HEAD SHA | Upstream | Clean/dirty | Modified/untracked files | Ahead/behind upstream | Ancestor of integration? | Unpublished commits? | Duplicate branch? |
|---|---------------|--------|----------|----------|-------------|-------------------------|----------------------|-------------------------|---------------------|-------------------|
| 1 | /home/winst/agent-gate | feat/dashboard | 0f24775 | origin/feat/dashboard | Clean | none | ahead 91, behind 6 | Yes | Yes (91 vs origin/feat/dashboard) | No |
| 2 | /home/winst/.local/share/kilo/worktree-pool/agent-gate-7307b6af2040/pastoral-libra | (detached) | b22dc64 | none | Clean | none | N/A | Yes | No | No (detached) |
| 3 | .../worktrees/desktop-tauri | desktop-tauri | 6775c8d | none | Clean | none | N/A | Yes | No | No |
| 4 | .../worktrees/feat-account-recovery-3f7b03f85e52a554 | feat/account-recovery | 801bda0 | none | Clean | none | N/A | Yes | No | No |
| 5 | .../worktrees/feat-auth-foundation-1e8e999a34107b77 | feat/auth-foundation | c35287d | none | Clean | none | N/A | Yes | No | No |
| 6 | .../worktrees/feat-backend-crud-d7120dc7ef61d20b | feat/backend-crud | 00a82d5 | none | Clean | none | N/A | Yes | No | No |
| 7 | .../worktrees/feat-background-jobs-1dac528fa493d860 | feat/background-jobs | ea17381 | none | Clean | none | N/A | Yes | No | No |
| 8 | .../worktrees/feat-dashboard-integration-ad49a1fe97eeb2a8 | feat/dashboard-integration | b1c8d84 | none | Clean | none | N/A | Yes | No | No |
| 9 | .../worktrees/feat-gemini-chatbot-2bb42abd556eaecf | feat/gemini-chatbot | 986cf4a | none | Clean | none | N/A | Yes | No | No |
| 10 | .../worktrees/feat-github-oauth-ef2eb1204fb1af96 | feat/github-oauth | 434d87f | none | Clean | none | N/A | Yes | No | No |
| 11 | .../worktrees/feat-paypal-sandbox-1102e54aa82dee50 | feat/paypal-sandbox | b1a0ee2 | none | Clean | none | N/A | **No** | Yes (19 unique commits) | No |
| 12 | .../worktrees/feat-totp-2fa-bcc3872d90d4265e | feat/totp-2fa | b283719 | origin/feat/totp-2fa | **Dirty** | ?? AUTH-05B.3C-Final-Report.md, ?? AUTH-05B.3D-Final-Report.md | Clean vs upstream | Yes | No | No |
| 13 | .../worktrees/infra/contabo-deployment-31d55c9827d0b411 | infra/contabo-deployment | 986cf4a | none | Clean | none | N/A | Yes | No | No |
| 14 | .../worktrees/integration-agentgate-dashboard | integration/agentgate-dashboard | f6ad730 | origin/main | **Dirty** | M x5 (schema fix files) | ahead 9, behind 17 vs origin/main | Yes | Yes (f6ad730 was pushed) | No |
| 15 | .../worktrees/integration-agentgate-dashboard-2 | integration-agentgate-dashboard-2 | f6ad730 | none | Clean | none | N/A | Yes | No | **Yes** (same SHA as integration/agentgate-dashboard) |
| 16 | .../worktrees/integration-auth-crud | integration/auth-crud | 3d6fef9 | none | Clean | none | N/A | Yes | No | No |
| 17 | .../worktrees/intergration | intergration | beba6f3 | origin/intergration | Clean | none | Clean vs upstream | Yes | No | **Yes** (misspelled; superseded) |
| 18 | .../worktrees/merge | merge | bc6987e | none | Clean | none | N/A | Yes | No | No |

### Worktree-specific notes

- **Worktree 14 (integration-agentgate-dashboard):** Has 5 modified files matching the `f6ad730` commit. Its local branch `integration/agentgate-dashboard` tracks `origin/main` (misconfigured — should track `origin/integration/agentgate-dashboard`). Shows `[ahead 9, behind 17]` relative to origin/main.
- **Worktree 15 (integration-agentgate-dashboard-2):** Clean, at same SHA `f6ad730` as worktree 14. Duplicate working branch for the same integration commit. No upstream configured.
- **Worktree 12 (feat/totp-2fa):** Has 2 untracked report files (`AUTH-05B.3C-Final-Report.md`, `AUTH-05B.3D-Final-Report.md`). Must be preserved.
- **Worktree 2 (pastoral-libra):** Detached HEAD at `b22dc64`. No branch, no upstream.
- **Worktree 1 (feat/dashboard):** Local branch at `0f24775` (old origin/main), but remote `origin/feat/dashboard` is at `4e82906`. Diverged: ahead 91, behind 6.

---

## 3. Complete Local and Remote Branch Inventory

### Local branches (19 total)

| Branch | SHA | Upstream tracking | Status vs upstream |
|--------|-----|-------------------|--------------------|
| audit/agentgate-predeployment-readiness | 4c021d0 | origin/audit/... | Clean (equal) |
| backup/feat-dashboard-local | 0f24775 | none | Local only |
| ci/postgres-service | f9d9ceb | origin/ci/postgres-service | Clean (equal) |
| desktop-tauri | 6775c8d | none | Local only |
| feat/account-recovery | 801bda0 | none | Local only |
| feat/auth-foundation | c35287d | none | Local only |
| feat/backend-crud | 00a82d5 | none | Local only |
| feat/background-jobs | ea17381 | none | Local only |
| feat/dashboard | 0f24775 | origin/feat/dashboard | **Diverged** (ahead 91, behind 6) |
| feat/dashboard-integration | b1c8d84 | none | Local only |
| feat/gemini-chatbot | 986cf4a | none | Local only |
| feat/github-oauth | 434d87f | none | Local only (remote exists but not tracked) |
| feat/paypal-sandbox | b1a0ee2 | none | Local only (remote exists but not tracked) |
| feat/totp-2fa | b283719 | origin/feat/totp-2fa | Clean (equal) |
| infra/contabo-deployment | 986cf4a | none | Local only |
| integration-agentgate-dashboard-2 | f6ad730 | none | Local only |
| integration/agentgate-dashboard | f6ad730 | origin/main | **Misconfigured** (tracks origin/main, not origin/integration/agentgate-dashboard) |
| integration/auth-crud | 3d6fef9 | none | Local only |
| intergration | beba6f3 | origin/intergration | Clean (equal) |
| main | 221a977 | origin/main | **Behind by 68** |

### Branches without upstream tracking (14)

backup/feat-dashboard-local, desktop-tauri, feat/account-recovery, feat/auth-foundation,
feat/backend-crud, feat/background-jobs, feat/dashboard-integration, feat/gemini-chatbot,
feat/github-oauth, feat/paypal-sandbox, infra/contabo-deployment,
integration-agentgate-dashboard-2, integration/auth-crud, merge

### Duplicate / misspelled / potentially obsolete branches

| Branch | SHA | Assessment |
|--------|-----|------------|
| `intergration` | beba6f3 | **Misspelled** (should be `integration`). Fully contained in integration/agentgate-dashboard. Superseded. |
| `integration-agentgate-dashboard-2` | f6ad730 | **Duplicate** — same SHA as `integration/agentgate-dashboard`. No upstream. Working branch for integration. |
| `backup/feat-dashboard-local` | 0f24775 | **Backup** — points to old origin/main. Fully contained in integration. |
| `merge` | bc6987e | Merge PR #6 worktree branch. Fully contained in integration. |

---

## 4. Branch Ancestry and Divergence Analysis

### Ancestry vs origin/integration/agentgate-dashboard (f6ad730)

**Contained (ancestor) — 18 branches:**
audit/agentgate-predeployment-readiness, backup/feat-dashboard-local, ci/postgres-service,
desktop-tauri, feat/account-recovery, feat/auth-foundation, feat/backend-crud,
feat/background-jobs, feat/dashboard, feat/dashboard-integration, feat/gemini-chatbot,
feat/github-oauth, feat/totp-2fa, infra/contabo-deployment, integration-agentgate-dashboard-2,
integration/agentgate-dashboard, integration/auth-crud, intergration, main, merge

**NOT contained — 1 branch:**
feat/paypal-sandbox (19 unique commits)

### Remote branches NOT contained in integration

| Remote branch | SHA | Unique commits vs integration | Relationship to origin/main |
|---------------|-----|------------------------------|------------------------------|
| origin/ft-backend | 7d3bae6 | 16 | **Is ancestor of origin/main** (merged into main) |
| origin/feat/dashboard | 4e82906 | 6 | **NOT ancestor of origin/main** (diverged) |
| origin/main | 6bce121 | 17 | N/A (advanced ahead of integration) |
| origin/integration/agentgate-dashboard | f6ad730 | 0 | Matches local integration branch |
| origin/intergration | beba6f3 | 0 | Contained |

### Unique commits detail

**origin/main NOT in integration (17 commits):**
```
6bce121 Merge pull request #13 from Root-node1/ft-backend
7d3bae6 Fix policy assignment in create_request method
d1818e8 record actual agent status transitions in audit log
87a9b08 Implement webhook payload retention with purging logic
0ebb552 Enhance security and deployment documentation
c3621d1 add strict type checking to CI
1f87f8a Remove 'gate' app from installed apps
daa3d33 Implement external audit head anchoring
de56b15 Refactor approval notification logic
339bf04 add AgentListSerializer and optimize agent list query
9322414 Refactor error handling to use ApiError
12e3a73 Enforce tenant consistency at model boundary
8d27c19 enhance merchant rule validation
acb2667 implement demo mode safety checks
f851618 fix(backend): use policy timezone for budget windows
cd9cf2c Implement currency precision handling in policy serializers
e9a2416 Add merchant mode handling with allowlist and blocklist
```

**origin/feat/dashboard NOT in integration (6 commits):**
```
4e82906 run and test the reset links
c7bcc5d fix all the react implementations
9988fbc wire all the backend authflows
86d359d wire alluths supported browser flows
8906154 Add Google OAuth dashboard sign-in
e09923c implement django dashboard login, protected session logins/logouts
```

**feat/paypal-sandbox NOT in integration (19 commits):**
Full PayPal sandbox webhook, payout, checkout, and OAuth client implementation.

**Integration NOT in origin/main (9 commits):**
```
f6ad730 fix(schema): resolve OpenAPI generation errors
b22dc64 docs: update Doc.md status with ticket references
6bdba5d tickets: create AGT-012 through AGT-017
6b83322 docs: add deployment, security, testing, presentation docs
42511e8 fix(accounts): fix import order in views.py
8f36204 feat(frontend): add Security section to settings
1748224 feat(frontend): integrate Delarum's auth dashboard pages
e042f49 feat(accounts): add session/auth contract endpoints
2ec267e feat(accounts): integrate AccountProfile linked to accounts.User
```

### Divergence summary

- **integration/agentgate-dashboard vs origin/main:** Diverged. Integration has 9 commits origin/main lacks; origin/main has 17 commits integration lacks.
- **feat/dashboard (local) vs origin/feat/dashboard:** Diverged. Local at 0f24775, remote at 4e82906. Neither is ancestor of the other.
- **main (local) vs origin/main:** Local at 221a977 is ancestor of origin/main at 6bce121 — fast-forward possible, local is behind by 68.

---

## 5. Unique Commits by Branch

Branches with unique commits not in any other branch (non-integration):

| Branch | Unique commit count | Sample unique commits |
|--------|--------------------|----------------------|
| feat/paypal-sandbox | 19 | PayPal sandbox webhooks, payouts, checkout, OAuth client |
| origin/feat/dashboard | 6 | Dashboard sign-in, reset links, auth flows |
| origin/ft-backend | 16 | Policy assignment fix, audit status, webhook retention, AgentListSerializer |
| origin/main | 17 | Includes all ft-backend commits + 1 merge |

Branches fully contained in integration (no unique commits beyond integration): all others listed in section 4.

---

## 6. Dirty / Uncommitted Work Requiring Protection

| Worktree | Branch | Uncommitted state | Files | Action required |
|----------|--------|-------------------|-------|-----------------|
| feat/totp-2fa | feat/totp-2fa | Untracked files | AUTH-05B.3C-Final-Report.md, AUTH-05B.3D-Final-Report.md | Preserve; do not stash, clean, or discard |
| integration-agentgate-dashboard | integration/agentgate-dashboard | Modified files | backend/apps/accounts/serializers.py, views.py; agents/serializers.py, views.py; config/settings/base.py | Preserve; these match commit f6ad730 but working tree wasn't updated after ref move |

All other 16 worktrees are clean.

---

## 7. Integration Coverage Matrix

| Branch | Contained in integration? | Unique vs integration | Integration unique vs branch | Ready to merge? |
|--------|--------------------------|----------------------|------------------------------|-----------------|
| feat/account-recovery | Yes | 0 | 9 | Yes |
| feat/auth-foundation | Yes | 0 | 9 | Yes |
| feat/backend-crud | Yes | 0 | 9 | Yes |
| feat/background-jobs | Yes | 0 | 9 | Yes |
| feat/dashboard-integration | Yes | 0 | 9 | Yes |
| feat/gemini-chatbot | Yes | 0 | 9 | Yes |
| feat/github-oauth | Yes | 0 | 9 | Yes |
| feat/totp-2fa | Yes | 0 | 9 | Yes |
| desktop-tauri | Yes | 0 | 9 | Yes |
| infra/contabo-deployment | Yes | 0 | 9 | Yes |
| integration/auth-crud | Yes | 0 | 9 | Yes |
| merge | Yes | 0 | 9 | Yes |
| intergration | Yes | 0 | 9 | Yes |
| backup/feat-dashboard-local | Yes | 0 | 9 | Yes |
| ci/postgres-service | Yes | 0 | 9 | Yes |
| audit/... | Yes | 0 | 9 | Yes |
| feat/dashboard | Yes (local at 0f24775) | 0 | 9 | Local is stale; remote diverged |
| feat/paypal-sandbox | **No** | 19 | 9 | **No** — requires review |
| origin/ft-backend | **No** | 16 | 9 | Partially (merged into origin/main) |
| origin/feat/dashboard | **No** | 6 | 9 | **No** — diverged from both main and integration |
| origin/main | **No** | 17 | 9 | **No** — ahead of integration |
| main (local) | Yes | 0 | 9 | Yes (but 68 commits behind origin/main) |

---

## 8. Risk Register

| Risk | Severity | Description | Affected branches/worktrees |
|------|----------|-------------|------------------------------|
| Tracking misconfiguration | High | `integration/agentgate-dashboard` tracks `origin/main` instead of `origin/integration/agentgate-dashboard`. Status shows `[ahead 9, behind 17]` which is misleading. | integration-agentgate-dashboard worktree, local branch integration/agentgate-dashboard |
| origin/main advanced ahead of integration | High | origin/main moved 0f24775 → 6bce121 (17 commits). Integration does not contain these. Merging integration into main now would lose origin/main's 17 commits; merging main into integration would introduce unreviewed changes. | origin/main, integration/agentgate-dashboard |
| feat/paypal-sandbox not integrated | Medium | 19 unique commits (PayPal sandbox webhooks, payouts, checkout) not in integration. Potential overlap with payments code in origin/main/ft-backend. | feat/paypal-sandbox worktree, local branch feat/paypal-sandbox |
| feat/dashboard diverged | Medium | Local feat/dashboard (0f24775) diverged from origin/feat/dashboard (4e82906). Neither is ancestor of the other. Local feat/dashboard is NOT ancestor of origin/main either. | feat/dashboard worktree, local branch feat/dashboard, origin/feat/dashboard |
| Duplicate integration branch | Low | `integration-agentgate-dashboard-2` at same SHA as `integration/agentgate-dashboard`. No upstream. | integration-agentgate-dashboard-2 worktree |
| Misspelled branch | Low | `intergration` (misspelled) at beba6f3, fully contained. Superseded by integration/agentgate-dashboard. | intergration worktree |
| Untracked report files | Low | feat/totp-2fa worktree has 2 untracked .md files. Not part of git history. | feat/totp-2fa worktree |
| Local main behind origin/main | Medium | Local main at 221a977, 68 commits behind origin/main (6bce121). Fast-forward safe but not yet done. | main worktree branch |
| Unpublished integration commit (now resolved) | Resolved | f6ad730 was pushed to origin/integration/agentgate-dashboard during prior task. Now matches remote. | — |

---

## 9. Recommended Target Structure

```
main                              (stable release baseline; fast-forward from origin/main when approved)
└── integration/agentgate-dashboard  (shared development baseline; feature branches merge here)
    ├── feat/account-recovery        (archived — already integrated)
    ├── feat/auth-foundation         (archived — already integrated)
    ├── feat/backend-crud            (archived — already integrated)
    ├── feat/background-jobs         (archived — already integrated)
    ├── feat/dashboard-integration   (archived — already integrated)
    ├── feat/gemini-chatbot          (archived — already integrated)
    ├── feat/github-oauth            (archived — already integrated)
    ├── feat/totp-2fa                (archived — already integrated)
    ├── desktop-tauri                (archived — already integrated)
    ├── infra/contabo-deployment     (archived — already integrated)
    ├── integration/auth-crud        (archived — already integrated)
    ├── feat/paypal-sandbox          (ACTIVE — 19 unique commits, needs review before integration)
    └── feat/dashboard               (ACTIVE — diverged, needs reconciliation before integration)
```

### Branches to archive / mark superseded

- `intergration` — misspelled, fully contained, superseded by `integration/agentgate-dashboard`
- `backup/feat-dashboard-local` — backup, fully contained, points to stale origin/main
- `merge` — PR #6 work, fully contained
- `integration-agentgate-dashboard-2` — duplicate of `integration/agentgate-dashboard` at same SHA

### Branches requiring attention before integration

- `feat/paypal-sandbox` — 19 unique commits, not yet in integration. Review for overlap with origin/main payments code.
- `feat/dashboard` — diverged from both origin/feat/dashboard and origin/main. Reconcile or abandon.
- `origin/ft-backend` — 16 commits now in origin/main. Decide if any should be cherry-picked or merged into integration separately.
- `origin/main` — 17 commits ahead of integration. Do not merge into integration without review.

---

## 10. Ordered Reconciliation Plan (EXECUTE ONLY AFTER APPROVAL)

All commands below are listed for reference. **Do not execute without explicit approval.**

### Stage 1: Fix tracking configuration (safe, no data movement)

```bash
# In the integration-agentgate-dashboard worktree:
git -C /home/winst/agent-gate/.kilo/worktrees/integration-agentgate-dashboard \
    branch --set-upstream-to=origin/integration/agentgate-dashboard integration/agentgate-dashboard
```

### Stage 2: Fast-forward local main to origin/main (safe, local main is ancestor)

```bash
git -C /home/winst/agent-gate checkout main
git -C /home/winst/agent-gate merge --ff-only origin/main
```

### Stage 3: Evaluate feat/paypal-sandbox for integration

```bash
# Review unique commits
git log --oneline origin/integration/agentgate-dashboard..feat/paypal-sandbox

# Check for file overlap with integration
git diff --stat origin/integration/agentgate-dashboard..feat/paypal-sandbox
```

If approved, create PR targeting `integration/agentgate-dashboard`.

### Stage 4: Reconcile feat/dashboard divergence

```bash
# Review what local feat/dashboard has that remote doesn't
git log --oneline origin/feat/dashboard..feat/dashboard

# Review what remote has that local doesn't
git log --oneline feat/dashboard..origin/feat/dashboard
```

Decide: keep local work, abandon local work, or merge remote changes in. Do not force-push.

### Stage 5: Archive obsolete branches (after team confirmation)

```bash
# Mark intergration as superseded (do not delete without approval)
git branch -m intergration intergration-superseded  # optional, only with approval

# Mark backup as superseded
git branch -m backup/feat-dashboard-local backup/feat-dashboard-local-superseded  # optional
```

### Stage 6: Clean up duplicate worktree (after team confirmation)

The `integration-agentgate-dashboard-2` worktree duplicates `integration/agentgate-dashboard` at the same SHA. Keep or remove based on team preference. Do not auto-delete.

---

## 11. Verification Criteria for Declaring Reconciliation

The repository is reconciled when ALL of the following are true:

1. `integration/agentgate-dashboard` tracks `origin/integration/agentgate-dashboard` (not `origin/main`).
2. `git status --short --branch` in the integration worktree shows clean (no modified files from ref mismatch).
3. `origin/integration/agentgate-dashboard` SHA equals local `integration/agentgate-dashboard` SHA.
4. `origin/integration/agentgate-dashboard` contains all previously integrated feature branches (ancestry check passes for all contained branches).
5. `feat/paypal-sandbox` has been either merged into integration via PR or explicitly deferred with a tracking issue.
6. `feat/dashboard` divergence has been resolved (local and remote aligned, or local abandoned with team approval).
7. `main` has been fast-forwarded to `origin/main` (or intentionally kept behind with documented reason).
8. No worktree has uncommitted changes that were not intentionally preserved and documented.
9. All schema validation passes: `python manage.py spectacular --file /tmp/schema.yaml --validate` returns 0 errors.
10. All backend tests pass: `python manage.py test` returns 0 failures.

---

## Executive Summary

The AgentGate repository has 18 registered worktrees, 19 local branches, and 9 remote branches. The integration branch `integration/agentgate-dashboard` is currently at `f6ad730` and matches its remote counterpart `origin/integration/agentgate-dashboard` (successfully pushed in a prior operation). However, several issues require attention:

1. **Tracking misconfiguration:** `integration/agentgate-dashboard` tracks `origin/main` instead of `origin/integration/agentgate-dashboard`, causing misleading git status output.

2. **origin/main advanced:** `origin/main` moved to `6bce121` with 17 commits not in integration. These include backend CRUD fixes, security docs, API error handling, tenant consistency, and demo mode safety checks. Integration cannot be merged into main or vice versa without review.

3. **feat/paypal-sandbox not integrated:** 19 unique commits of PayPal sandbox webhook/payout/checkout work exist locally but are not in integration.

4. **feat/dashboard diverged:** Local worktree at `0f24775` diverged from remote `origin/feat/dashboard` at `4e82906`; neither is ancestor of the other.

5. **Duplicate/obsolete branches:** `intergration` (misspelled), `backup/feat-dashboard-local`, `merge`, and `integration-agentgate-dashboard-2` are all fully contained in integration and candidates for archival.

6. **Dirty worktrees:** `feat/totp-2fa` has 2 untracked report files; `integration-agentgate-dashboard` has 5 modified schema-fix files. Both must be preserved.

**No mutations were performed during this audit.** All findings are read-only. Reconciliation requires explicit team approval and should proceed in the staged order described in Section 10.