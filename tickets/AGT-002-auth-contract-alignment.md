# AGT-002: Authentication Contract Alignment

**Ticket ID:** AGT-002
**Title:** Align frontend and backend authentication contract
**Objective:** Establish one authoritative auth contract between our Django allauth headless backend and Delarum's dashboard frontend.
**Status:** Done
**Assigned owner:** Isaac (backend) + Del (frontend)

## Context
Our backend uses allauth headless at `/api/auth/headless/browser/v1/` with custom endpoints `/api/auth/user/` and `/api/auth/logout/`. Delarum's frontend expects `/api/auth/_allauth/browser/v1/` plus custom endpoints `/api/auth/csrf/`, `/api/auth/options/`, `/api/auth/session/`, `/api/auth/session/remember/`. We keep our backend contract as authority and add minimal extensions.

## Scope
- Add `GET /api/auth/csrf/` returning `{ csrfToken }`
- Add `GET /api/auth/options/` returning `{ csrfToken, googleOAuthEnabled, githubOAuthEnabled }`
- Add `GET /api/auth/session/` returning `{ authenticated, user?: { username } }`
- Add `POST /api/auth/session/remember/` for remember-me session expiry
- Add `GOOGLE_OAUTH_ENABLED` and `GITHUB_OAUTH_ENABLED` settings
- Adapt frontend `api/auth.ts` to our `/api/auth/headless/browser/v1/` base URL
- Add all Delarum frontend auth methods using our contract

## Acceptance Criteria
- All 4 custom endpoints return correct response shapes
- OAuth enablement flags derived from environment variables
- Session status endpoint always returns 200 (not 401 when unauthenticated)
- Frontend TypeScript, lint, and production build pass
- All 57 existing auth tests pass

## Dependencies
- AGT-001 (AccountProfile) - not strictly required but same area

## Files affected
- `backend/config/settings/base.py` (OAuth enablement flags)
- `backend/apps/accounts/views.py` (CsrfTokenView, AuthOptionsView, SessionStatusView, SessionRememberView)
- `backend/apps/accounts/urls.py`
- `frontend/src/api/auth.ts` (unified client)
- `frontend/src/App.tsx` (auth routes, ProtectedAppLayout)
- `frontend/src/session/context.ts` (auth state)
- `frontend/src/session/SessionProvider.tsx` (auth state management)

## Required tests
- Backend: GET /api/auth/csrf/ returns token
- Backend: GET /api/auth/options/ returns OAuth flags
- Backend: GET /api/auth/session/ returns authenticated state
- Backend: POST /api/auth/session/remember/ sets session expiry
- Frontend: build passes with adapted auth client

## Definition of done
- Code committed to `integration/agentgate-dashboard` branch
- Django `check` passes
- Frontend `tsc --noEmit` and `npm run build` pass
- All existing auth tests pass