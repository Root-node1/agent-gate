# AGT-018: Integrate Backend Commits from origin/main into Integration Branch

**Ticket ID:** AGT-018
**Title:** Review and integrate 17 backend commits from origin/main into integration/agentgate-dashboard
**Objective:** Review each of the 17 commits on origin/main that are not yet in integration/agentgate-dashboard, and selectively integrate approved ones via pull requests.
**Priority:** High (blocks release readiness)
**Status:** Not started
**Assigned owner:** Isaac (backend), with Anthony (security review) and Winstone (CI/type checking)

## Context

`origin/main` advanced to `6bce121` with 17 commits not present in `origin/integration/agentgate-dashboard` (`f6ad730`). All 16 non-merge commits originated on `origin/ft-backend` (PR #13). These commits touch policy assignment, audit logging, webhook retention, tenant consistency, merchant rules, demo mode safety, currency precision, merchant mode handling, error handling, and CI type checking. They must be reviewed individually before integration — do not merge origin/main wholesale.

## Commit inventory (17 commits)

| SHA | Type | Subject | Primary review | Security review |
|-----|------|---------|---------------|-----------------|
| 6bce121 | Merge | Merge PR #13 from ft-backend | Winstone | N/A |
| 7d3bae6 | feat(backend) | Fix policy assignment in create_request method | Isaac | Anthony |
| d1818e8 | feat(backend) | Record actual agent status transitions in audit log | Isaac | Anthony |
| 87a9b08 | feat(backend) | Implement webhook payload retention with purging logic | Isaac | Anthony |
| 0ebb552 | docs/security | Enhance security and deployment documentation; add header verification script | Anthony | Anthony |
| c3621d1 | ci | Add strict type checking to CI | Winstone | N/A |
| 1f87f8a | chore(backend) | Remove 'gate' app from installed apps | Isaac | N/A |
| daa3d33 | feat(backend) | Implement external audit head anchoring | Isaac | Anthony |
| de56b15 | refactor(backend) | Refactor approval notification logic | Isaac | N/A |
| 339bf04 | feat(backend) | Add AgentListSerializer and optimize agent list query | Isaac | N/A |
| 9322414 | refactor(backend) | Refactor error handling to use ApiError | Isaac | N/A |
| 12e3a73 | feat(backend) | Enforce tenant consistency at model boundary | Isaac | Anthony |
| 8d27c19 | fix(backend) | Enhance merchant rule validation | Isaac | Anthony |
| acb2667 | feat(backend) | Implement demo mode safety checks | Isaac | Anthony |
| f851618 | fix(backend) | Use policy timezone for budget windows | Isaac | N/A |
| cd9cf2c | feat(backend) | Implement currency precision handling in policy serializers | Isaac | N/A |
| e9a2416 | feat(backend) | Add merchant mode handling with allowlist and blocklist | Isaac | Anthony |

## Scope

- Review each commit's diff for correctness, test coverage, and no unintended runtime behavior changes
- Verify no secrets, credentials, or production values are committed
- Verify `makemigrations --check --dry-run` passes for migration-related commits
- Verify `python manage.py spectacular --file /tmp/schema.yaml --validate` returns 0 errors
- Verify `python manage.py test` passes (694 tests, 0 failures)
- Verify `ruff check .` passes
- Create individual PRs into `integration/agentgate-dashboard` for each approved commit or logical group
- Do not fast-forward integration to origin/main
- Do not merge origin/main into integration wholesale

## Acceptance Criteria

- Each of the 17 commits reviewed and dispositioned (approve / reject / request changes)
- Approved commits integrated via PR into `integration/agentgate-dashboard`
- No runtime API behavior changes without documentation and justification
- No secrets committed
- Schema validation passes (0 errors)
- All backend tests pass (0 failures)
- Ruff passes
- Migration check passes

## Dependencies

- None (standalone review task)

## Files affected

- `backend/apps/agents/views.py` (status transitions, error handling, AgentListSerializer)
- `backend/apps/agents/serializers.py` (AgentListSerializer)
- `backend/apps/audit/models.py` (status transitions, head anchoring)
- `backend/apps/audit/anchors.py` (external audit head anchoring)
- `backend/apps/audit/views.py` (audit endpoints)
- `backend/apps/audit/services.py` (audit services)
- `backend/apps/accounts/views.py` (error handling)
- `backend/apps/accounts/serializers.py` (security docs header)
- `backend/apps/payments/` (webhook retention, error handling)
- `backend/apps/policies/` (policy assignment, merchant rules, currency precision, merchant mode)
- `backend/apps/approvals/notifications.py` (approval notification refactor)
- `backend/apps/spend/services.py` (budget windows, merchant mode)
- `backend/engine/rules.py` (strict type checking)
- `backend/.github/workflows/ci.yml` (strict type checking)
- `backend/config/settings/base.py` (multiple commits)
- `scripts/check_production_headers.py` (security docs)

## Required tests

- All 694 existing backend tests pass
- New tests included with each commit pass
- `makemigrations --check --dry-run` reports no changes
- Schema validation passes
- Ruff passes

## Definition of done

- All 17 commits reviewed and dispositioned
- Approved commits merged into `integration/agentgate-dashboard` via PR
- Anthony signs off on security-relevant changes
- CI passes on integration branch
