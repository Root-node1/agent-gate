# AgentGate — Integration Reconciliation Plan

**Date:** 2026-11-09
**Source audit:** `docs/research/COMPLETE_GIT_WORKTREE_AUDIT.md`
**Integration baseline:** `origin/integration/agentgate-dashboard` = `f6ad730ca1a07a4f23092fba4315bc9ae8197be0`
**Current origin/main:** `6bce12149525456afb226bae3be984a7b6e631bd`
**Current local HEAD:** `f6ad730ca1a07a4f23092fba4315bc9ae8197be0`

---

## 1. Verified Branch Baseline

| Ref | SHA | Notes |
|-----|-----|-------|
| `origin/integration/agentgate-dashboard` | `f6ad730` | Matches local `integration/agentgate-dashboard` HEAD. Pushed successfully. |
| Local `integration/agentgate-dashboard` | `f6ad730` | Same as remote. Branch is clean. |
| `origin/main` | `6bce121` | Advanced ahead of integration. 17 commits not in integration. |
| Local `main` | `221a977` | 68 commits behind `origin/main`. Not fast-forwarded per safety rules. |
| `integration/agentgate-dashboard` tracking | `origin/main` | **MISCONFIGURED** — tracks `origin/main` instead of `origin/integration/agentgate-dashboard`. |

Local HEAD and remote `origin/integration/agentgate-dashboard` match at `f6ad730`.

---

## 2. New Main Commits Requiring Review (17 commits)

`origin/main` is 17 commits ahead of `origin/integration/agentgate-dashboard`. All 16 non-merge commits originated on `origin/ft-backend` (PR #13) and were merged into main via `6bce121`.

### Commit list

| SHA | Type | Subject | Area |
|-----|------|---------|------|
| 6bce121 | Merge | Merge pull request #13 from Root-node1/ft-backend | Integration |
| 7d3bae6 | feat(backend) | Fix policy assignment in create_request method | Backend/API |
| d1818e8 | feat(backend) | Record actual agent status transitions in audit log | Backend/API |
| 87a9b08 | feat(backend) | Implement webhook payload retention with purging logic | Backend/API |
| 0ebb552 | docs/security | Enhance security and deployment documentation; add production header verification script | Security/Docs |
| c3621d1 | ci | Add strict type checking to CI | CI/CD |
| 1f87f8a | chore(backend) | Remove 'gate' app from installed apps | Backend/API |
| daa3d33 | feat(backend) | Implement external audit head anchoring | Backend/API |
| de56b15 | refactor(backend) | Refactor approval notification logic | Backend/API |
| 339bf04 | feat(backend) | Add AgentListSerializer and optimize agent list query | Backend/API |
| 9322414 | refactor(backend) | Refactor error handling to use ApiError | Backend/API |
| 12e3a73 | feat(backend) | Enforce tenant consistency at model boundary | Backend/API |
| 8d27c19 | fix(backend) | Enhance merchant rule validation | Backend/API |
| acb2667 | feat(backend) | Implement demo mode safety checks | Backend/API |
| f851618 | fix(backend) | Use policy timezone for budget windows | Backend/API |
| cd9cf2c | feat(backend) | Implement currency precision handling in policy serializers | Backend/API |
| e9a2416 | feat(backend) | Add merchant mode handling with allowlist and blocklist | Backend/API |

### Assessment

- **14 of 17 are backend/API commits** — owned by Isaac (backend), with security-relevant ones needing Anthony review.
- **1 is CI** (c3621d1 strict type checking) — owned by Winstone.
- **1 is security docs** (0ebb552) — owned by Anthony.
- **1 is a merge commit** (6bce121) — owned by Winstone.

None of these 17 commits are in `integration/agentgate-dashboard`. They must be reviewed before integration.

---

## 3. Integration Gaps

### Gap A: origin/main (17 commits) — Not in integration

All backend/API work from ft-backend PR #13. Includes security-sensitive changes (tenant consistency, merchant rule validation, webhook retention, audit head anchoring, demo mode safety, currency precision, merchant mode handling).

**Owner:** Isaac (primary), Anthony (security review), Winstone (CI/type checking).

### Gap B: origin/feat/dashboard (6 commits) — Not in integration

| SHA | Subject | Area |
|-----|---------|------|
| e09923c | Implement django dashboard login, protected session logins/logouts | Frontend/Auth |
| 8906154 | Add Google OAuth dashboard sign-in | Frontend/Auth |
| 86d359d | Wire all auth supported browser flows | Frontend/Auth |
| 9988fbc | Wire all backend authflows | Frontend/Auth |
| c7bcc5d | Fix all the React implementations | Frontend |
| 4e82906 | Run and test the reset links | Frontend |

**Owner:** Del (primary frontend), Isaac (backend auth support).

### Gap C: feat/paypal-sandbox (19 commits) — Not in integration

Full PayPal sandbox implementation: webhook ingestion, payout submission, checkout capture/order creation, OAuth HTTP client, financial reconciliation, denied capture handling.

**Owner:** Isaac (primary backend).

---

## 4. Branch-Specific Reconciliation Recommendations

| Branch | SHA | Status | Recommendation |
|--------|-----|--------|----------------|
| `integration/agentgate-dashboard` | `f6ad730` | Clean, matches remote | Fix upstream tracking to `origin/integration/agentgate-dashboard`. Do not merge origin/main into it yet. |
| `origin/main` | `6bce121` | 17 commits ahead of integration | Review each commit (Isaac + Anthony). Selectively integrate approved commits via PR into integration. Do not fast-forward integration to main. |
| `origin/feat/dashboard` | `4e82906` | 6 commits ahead, diverged from local feat/dashboard | Del reviews the 6 commits. Integrate approved ones via PR into integration. |
| `feat/paypal-sandbox` (local) | `b1a0ee2` | 19 commits ahead, not in integration | Isaac reviews. Integrate via PR into integration after security review of payment handling. |
| `feat/dashboard` (local worktree) | `0f24775` | Already contained in integration; stale vs origin/feat/dashboard | No action needed on local branch; origin/feat/dashboard has new work to integrate. |
| `main` (local) | `221a977` | 68 commits behind origin/main | Do not fast-forward (per safety rules). Fast-forward only after integration branch is stable and approved. |
| `intergration` | `beba6f3` | Misspelled, fully contained | Archive/mark superseded after team confirmation. |
| `backup/feat-dashboard-local` | `0f24775` | Fully contained, points to stale origin/main | Archive/mark superseded after team confirmation. |
| `merge` | `bc6987e` | Fully contained | Archive/mark superseded after team confirmation. |
| `integration-agentgate-dashboard-2` | `f6ad730` | Duplicate of integration/agentgate-dashboard | Keep or remove after team confirmation. |

---

## 5. Risks and Dependencies

| Risk | Severity | Dependency | Owner |
|------|----------|------------|-------|
| origin/main has 17 unreviewed commits ahead of integration | High | Must be reviewed by Isaac + Anthony before any integration | Isaac, Anthony |
| Integration branch tracks wrong upstream (origin/main) | Medium | Fix tracking config to `origin/integration/agentgate-dashboard` | Winstone |
| feat/paypal-sandbox payment code not security-reviewed | High | Anthony must review before integration | Anthony, Isaac |
| origin/feat/dashboard diverged from local feat/dashboard | Medium | Del must review 6 remote commits | Del |
| AGT-008 security remediation blocked by AGT-007 | High | Anthony must complete security assessment first | Anthony |
| AGT-013 VPS deployment blocked by AGT-012 VPS access | High | Winstone must establish SSH access | Winstone |
| VULN-001 MFA_ENCRYPTION_KEY not configured | High | Blocks MFA demo and production startup | Isaac + Anthony |
| 694 backend tests pass locally but CI not verified on integration branch | Medium | Winstone must verify CI passes on integration branch | Winstone |

---

## 6. Ordered Integration Plan

### Phase 1: Stabilize integration branch (Winstone)

1. Fix `integration/agentgate-dashboard` upstream tracking to `origin/integration/agentgate-dashboard` (no data movement).
2. Verify `git status --short --branch` is clean in integration worktree.
3. Verify `origin/integration/agentgate-dashboard` SHA equals local HEAD (`f6ad730`).

### Phase 2: Review and integrate origin/main backend commits (Isaac + Anthony + Winstone)

4. Isaac reviews each of the 14 backend commits for correctness, test coverage, and no runtime behavior changes.
5. Anthony reviews security-relevant commits (tenant consistency, merchant rule validation, webhook retention, audit anchoring, demo mode safety, currency precision, merchant mode).
6. Winstone reviews CI/type checking commit (c3621d1).
7. Anthony reviews security docs commit (0ebb552).
8. Create PRs into `integration/agentgate-dashboard` for approved commits. Do not merge origin/main wholesale.

### Phase 3: Review and integrate origin/feat/dashboard commits (Del + Isaac)

9. Del reviews the 6 frontend/dashboard commits.
10. Isaac reviews any backend auth components.
11. Create PR into `integration/agentgate-dashboard` for approved commits.

### Phase 4: Review and integrate feat/paypal-sandbox commits (Isaac + Anthony)

12. Isaac reviews all 19 PayPal sandbox commits.
13. Anthony reviews payment security (webhook signature verification, financial reconciliation, denied capture handling).
14. Create PR into `integration/agentgate-dashboard` for approved commits.

### Phase 5: Complete remaining tickets

15. Anthony completes AGT-007 security assessment.
16. Isaac starts AGT-008 security remediation (after AGT-007 done).
17. Winstone resolves AGT-012 VPS access, then AGT-013 deployment.
18. Del starts AGT-009 frontend integration testing (after backend deployed).
19. Winstone completes AGT-010 CI/CD verification on integration branch.
20. Ian completes AGT-017 presentation readiness.
21. Del completes AGT-016 Tauri desktop distribution (after backend deployed).

### Phase 6: Release to main (Winstone, after all approvals)

22. Fast-forward local `main` to `origin/main` only after integration branch is stable and all PRs merged.
23. Create release PR from `integration/agentgate-dashboard` into `main`.

---

## 7. Test and Release Gates

| Gate | Command | Owner | Required before |
|------|---------|-------|-----------------|
| Schema validation | `python manage.py spectacular --file /tmp/schema.yaml --validate` | Isaac | Any backend/PR merge |
| Backend tests | `python manage.py test` | Isaac | Any backend/PR merge |
| Ruff lint | `ruff check .` | Isaac | Any backend/PR merge |
| Frontend TypeScript | `tsc --noEmit` | Del | Any frontend/PR merge |
| Frontend lint | `npm run lint` | Del | Any frontend/PR merge |
| Frontend build | `npm run build` | Del | Any frontend/PR merge |
| Migration check | `makemigrations --check --dry-run` | Isaac | Any migration change |
| CI pipeline | GitHub Actions on integration branch | Winstone | Before release to main |

**Definition of reconciled:**
- `integration/agentgate-dashboard` tracks `origin/integration/agentgate-dashboard` (not `origin/main`)
- All 17 origin/main commits reviewed; approved ones integrated via PR
- All 6 origin/feat/dashboard commits reviewed; approved ones integrated via PR
- All 19 feat/paypal-sandbox commits reviewed; approved ones integrated via PR
- All gates pass on integration branch
- AGT-007 security assessment complete
- AGT-010 CI/CD verification passes on integration branch

---

## 8. Ticket Mapping

| Ticket | Owner | Status | Relation to this plan |
|--------|-------|--------|----------------------|
| AGT-001 to AGT-006 | Various | Done | Already in integration branch |
| AGT-007 | Anthony | In Progress | Security assessment; prerequisite for AGT-008 |
| AGT-008 | Isaac | Blocked by AGT-007 | Security remediation |
| AGT-009 | Del + Isaac | Blocked by AGT-012 | Frontend E2E testing |
| AGT-010 | Winstone | In Progress | CI/CD verification on integration branch |
| AGT-011 | Ian + Winstone | In Progress | Presentation readiness |
| AGT-012 | Winstone | In Progress | VPS access (blocks AGT-013, AGT-009) |
| AGT-013 | Winstone + Isaac | Blocked by AGT-012 | VPS deployment |
| AGT-014 | Winstone + Isaac | Not started | Backup automation |
| AGT-015 | Winstone | Not started | Team VPS access |
| AGT-016 | Del + Winstone | Not started | Tauri desktop |
| AGT-017 | Ian + Winstone | In Progress | Presentation |
| AGT-018 | Isaac + Anthony | New | Integrate origin/main backend commits |
| AGT-019 | Del + Isaac | New | Integrate origin/feat/dashboard commits |
| AGT-020 | Isaac + Anthony | New | Integrate feat/paypal-sandbox commits |

---

## 9. Decisions Requiring Winstone's Approval

1. **Fix integration branch upstream tracking** — Change `integration/agentgate-dashboard` to track `origin/integration/agentgate-dashboard` instead of `origin/main`.
2. **Do not fast-forward local main** — Local main remains at `221a977` (68 behind origin/main) until integration is stable.
3. **Selective integration of origin/main** — Review each of the 17 commits individually rather than merging origin/main wholesale into integration.
4. **Archive obsolete branches** — `intergration`, `backup/feat-dashboard-local`, `merge`, `integration-agentgate-dashboard-2` after team confirmation.
5. **AGT-012 VPS access** — Winstone to diagnose and document SSH timeout resolution steps.
