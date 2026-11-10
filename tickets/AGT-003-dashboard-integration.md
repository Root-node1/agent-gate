# AGT-003: Dashboard Integration

**Ticket ID:** AGT-003
**Title:** Integrate Delarum's dashboard frontend pages
**Objective:** Add Delarum's auth and dashboard UI pages to our frontend, adapted to our backend contract.
**Status:** Done
**Assigned owner:** Del (designer frontend)

## Context
Delarum's `origin/feat/dashboard` branch adds LoginPage, RegisterPage, MfaPage, VerifyEmailPage, AuthProviders, AuthShell, AuthFields, AuthPages.css, and SecuritySection. Our frontend has no auth pages (only ForgotPasswordPage, ResetPasswordPage at `/pages/auth/`).

## Scope
- Add LoginPage (email/password + OAuth + remember me)
- Add RegisterPage (full_name, email, organization, password, terms)
- Add MfaPage (TOTP 6-digit + recovery codes)
- Add VerifyEmailPage (code entry, resend, change email)
- Add AuthProviders (Google/GitHub OAuth buttons)
- Add AuthShell (shared auth page layout)
- Add AuthFields (PasswordField, PasswordGuidance, SixDigitCodeInput)
- Add AuthPages.css (shared auth styles)
- Add SecuritySection to settings (TOTP setup, recovery codes)
- Add Security tab to settings navigation
- Add auth routes to App.tsx with ProtectedAppLayout

## Acceptance Criteria
- Login page renders with email/password form and OAuth buttons
- Register page collects full_name, email, organization, password
- MFA page supports TOTP code and recovery code
- Verify email page supports code entry and resend
- Security section in settings manages TOTP and recovery codes
- Protected routes redirect unauthenticated users to /login
- Session restored from backend on app mount
- Frontend TypeScript, lint, and production build pass

## Dependencies
- AGT-002 (auth contract alignment)

## Files affected
- `frontend/src/App.tsx`
- `frontend/src/api/auth.ts`
- `frontend/src/session/context.ts`
- `frontend/src/session/SessionProvider.tsx`
- `frontend/src/pages/LoginPage.tsx` (new)
- `frontend/src/pages/RegisterPage.tsx` (new)
- `frontend/src/pages/MfaPage.tsx` (new)
- `frontend/src/pages/VerifyEmailPage.tsx` (new)
- `frontend/src/pages/AuthFields.tsx` (new)
- `frontend/src/pages/AuthProviders.tsx` (new)
- `frontend/src/pages/AuthShell.tsx` (new)
- `frontend/src/pages/AuthPages.css` (new)
- `frontend/src/pages/app/settings/SecuritySection.tsx` (new)
- `frontend/src/pages/app/settings/settingsData.ts`
- `frontend/src/pages/app/SettingsPage.tsx`

## Required tests
- Frontend production build passes
- Frontend lint passes
- TypeScript type check passes

## Definition of done
- Code committed to `integration/agentgate-dashboard` branch
- All pages render without errors
- Auth flow: login → session → dashboard → profile → logout works end-to-end