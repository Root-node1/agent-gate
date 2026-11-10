# AGT-019: Integrate Frontend Dashboard Commits from origin/feat/dashboard into Integration Branch

**Ticket ID:** AGT-019
**Title:** Review and integrate 6 frontend/dashboard commits from origin/feat/dashboard into integration/agentgate-dashboard
**Objective:** Review each of the 6 commits on origin/feat/dashboard that are not yet in integration/agentgate-dashboard, and selectively integrate approved ones via pull requests.
**Priority:** High (blocks presentation readiness)
**Status:** Not started
**Assigned owner:** Del (frontend), with Isaac (backend auth support)

## Context

`origin/feat/dashboard` is at `4e82906` with 6 commits not present in `origin/feat/dashboard`/`integration/agentgate-dashboard`. These commits implement Django dashboard login, protected session logins/logouts, Google OAuth sign-in, browser auth flow wiring, React implementations, and reset link testing. The local `feat/dashboard` worktree is at `0f24775` (stale, already contained in integration), while the remote has advanced with new work.

## Commit inventory (6 commits)

| SHA | Subject | Area |
|-----|---------|------|
| e09923c | Implement django dashboard login, add protected session logins and logouts with endpoints and account creation, add the sign in screen and update the read me | Frontend/Auth |
| 8906154 | Add Google OAuth dashboard sign-in | Frontend/Auth |
| 86d359d | Wire alluths supported browser flows | Frontend/Auth |
| 9988fbc | Wire all the backend authflows and the full backend auth passes | Frontend/Auth |
| c7bcc5d | Fix all the react implementations | Frontend |
| 4e82906 | Run and test the reset links | Frontend |

## Scope

- Review each commit's diff for correctness and consistency with the backend auth contract established in AGT-002
- Verify frontend TypeScript type check passes (`tsc --noEmit`)
- Verify frontend lint passes (`npm run lint`)
- Verify frontend production build passes (`npm run build`)
- Verify no hardcoded localhost API URLs in release builds
- Create PRs into `integration/agentgate-dashboard` for approved commits
- Do not force-push; do not discard either side's work if branches diverge

## Acceptance Criteria

- Each of the 6 commits reviewed and dispositioned (approve / reject / request changes)
- Approved commits integrated via PR into `integration/agentgate-dashboard`
- Frontend TypeScript passes
- Frontend lint passes
- Frontend production build passes
- Auth flow: login → session → dashboard → profile → logout works end-to-end (against real backend when deployed)

## Dependencies

- AGT-002 (auth contract alignment — already done, in integration branch)
- AGT-003 (dashboard integration — already done, in integration branch)

## Files affected

- `frontend/src/App.tsx` (auth routes, ProtectedAppLayout)
- `frontend/src/api/auth.ts` (auth client)
- `frontend/src/session/context.ts` (auth state)
- `frontend/src/session/SessionProvider.tsx` (auth state management)
- `frontend/src/pages/LoginPage.tsx` (new/existing)
- `frontend/src/pages/RegisterPage.tsx` (new/existing)
- `frontend/src/pages/MfaPage.tsx` (new/existing)
- `frontend/src/pages/VerifyEmailPage.tsx` (new/existing)
- `frontend/src/pages/AuthFields.tsx` (new/existing)
- `frontend/src/pages/AuthProviders.tsx` (new/existing)
- `frontend/src/pages/AuthShell.tsx` (new/existing)
- `frontend/src/pages/AuthPages.css` (new/existing)
- `frontend/src/pages/app/settings/SecuritySection.tsx` (new/existing)
- `frontend/src/pages/app/settings/settingsData.ts` (new/existing)
- `frontend/src/pages/app/SettingsPage.tsx` (new/existing)
- Backend auth endpoints in `backend/apps/accounts/views.py` (if any backend changes included)

## Required tests

- Frontend `tsc --noEmit` passes
- Frontend `npm run lint` passes
- Frontend `npm run build` passes
- E2E auth flow verification (when backend deployed — see AGT-009)

## Definition of done

- All 6 commits reviewed and dispositioned
- Approved commits merged into `integration/agentgate-dashboard` via PR
- Frontend build, lint, and type check all pass
