# AGT-006: MFA and Recovery Flows

**Ticket ID:** AGT-006
**Title:** MFA setup, activation, and recovery code management
**Objective:** Integrate Delarum's MFA and recovery code UI with our allauth MFA backend endpoints.
**Status:** Done
**Assigned owner:** Del (frontend) + Isaac (backend)

## Context
Our backend uses allauth MFA with CustomMFAAdapter (Fernet at-rest encryption). Endpoints at `/api/auth/headless/browser/v1/account/authenticators/totp` and `/account/authenticators/recovery-codes`. Delarum's SecuritySection provides TOTP setup, activation, deactivation, and recovery code management UI.

## Scope
- SecuritySection component with TOTP setup key display, 6-digit verification, activation
- Recovery code generation, viewing, copying
- MFA page for sign-in verification (TOTP or recovery code)
- Reauthentication before sensitive security changes
- Backend MFA endpoints already exist (allauth + CustomMFAAdapter)

## Acceptance Criteria
- TOTP setup key displayed with QR code URI
- 6-digit code verification activates TOTP
- Recovery codes generated, displayed once, copyable
- TOTP can be disabled
- Reauthentication required before disabling TOTP or regenerating codes
- MFA sign-in page supports TOTP and recovery code verification
- Frontend TypeScript, lint, and build pass

## Dependencies
- AGT-002 (auth contract alignment)
- CustomMFAAdapter (already exists in backend)
- MFA_ENCRYPTION_KEY setting (must be configured in production)

## Files affected
- `frontend/src/pages/app/settings/SecuritySection.tsx` (new)
- `frontend/src/pages/MfaPage.tsx` (new)
- `frontend/src/api/auth.ts` (reauthenticate function)

## Required tests
- TOTP setup and activation flow
- Recovery code generation and viewing
- TOTP disable with reauthentication
- MFA sign-in verification

## Definition of done
- Code committed to `integration/agentgate-dashboard` branch
- Security section accessible from settings
- MFA sign-in flow works end-to-end