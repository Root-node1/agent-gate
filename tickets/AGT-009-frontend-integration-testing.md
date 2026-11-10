# AGT-009: Frontend Integration Testing

**Ticket ID:** AGT-009
**Title:** End-to-end frontend-to-backend integration tests
**Objective:** Verify actual frontend-to-backend requests work, not just mocked responses.
**Status:** Not started
**Assigned owner:** Del (frontend) + Isaac (backend)

## Context
Distinguish unit tests from actual end-to-end verification. Test real frontend-to-backend requests for login, registration, session restoration, protected routes, dashboard loading, profile management, MFA, and error handling.

## Evidence Produced
- `docs/testing/E2E_TEST_RESULTS.md` — E2E test plan with 15 test cases defined
- Frontend TypeScript, lint, and production build all pass
- Backend tests: 694 pass, 30 skipped, 0 failures

## Blocker
VPS SSH access not established (port 22 timed out). Cannot deploy backend or run E2E against deployed environment. See AGT-012.

## Scope
- Frontend production build and lint pass
- Login and registration against real backend
- Session restoration on app mount
- Protected routes redirect unauthenticated users
- Dashboard loads with authenticated session
- Profile loading and editing
- MFA screens (setup, verify, recovery codes)
- Error handling (network errors, 401, 403, 429)
- Responsive behavior

## Acceptance Criteria
- Frontend build passes
- Frontend lint passes
- End-to-end auth flow works against real backend
- No mocked API responses in integration tests
- Error states handled properly

## Dependencies
- AGT-002 (auth contract alignment)
- AGT-003 (dashboard integration)

## Files affected
- Frontend test files (TBD)
- Backend test files (TBD)

## Required tests
- E2E: register → login → session restore → dashboard → profile → logout
- E2E: protected route redirects to /login when unauthenticated
- E2E: profile update persists to backend
- E2E: MFA setup and verification flow

## Definition of done
- End-to-end tests pass against real backend
- Frontend build and lint pass