# AgentGate main user flows

## Application Overview

Focused browser test plan for AgentGate's public entry points, authentication lifecycle, and signed-in dashboard workflows. The landing, downloads, system-requirements, and installation pages were inspected in the running Vite frontend. Dashboard scenarios are grounded in the app's seeded in-memory demo and visible UI. The local backend was not running during exploration; authentication and protected-route scenarios must run with a working backend or controlled auth fixtures. Each test should use a fresh browser context and avoid relying on another test's state. Dashboard demo tests require an authenticated session; demo mutations are in memory and reset on reload.

## Test Scenarios

### 1. Public discovery and desktop onboarding

**Seed:** `N/A — use a fresh browser context`

#### 1.1. Explore the landing page and enter the demo

**File:** `tests/public/landing-navigation.spec.ts`

**Steps:**
  1. Open `/` in a fresh browser context.
    - expect: The AgentGate landing page displays its main headline, a description of the allow/deny/approval outcomes, and the sample-data disclaimer.
  2. Activate the “How it works” and “Features” navigation links.
    - expect: Each link navigates to its matching section on the landing page.
  3. Activate “Explore demo” while signed out.
    - expect: The protected dashboard does not become accessible anonymously; the visitor is redirected to `/login` when the backend reports an anonymous session.
  4. Use the home link to return to `/`.
    - expect: The landing page renders again without a stale protected-route error.

#### 1.2. Navigate desktop download and setup information

**File:** `tests/public/desktop-onboarding.spec.ts`

**Steps:**
  1. Open `/downloads`.
    - expect: The page identifies the desktop client version and states that the backend is a separate component.
  2. Review platform download controls and release status.
    - expect: Unavailable platform links remain disabled or clearly unavailable; Linux artifact and checksum information is shown when present.
  3. Open the system requirements page from the site navigation or onboarding links.
    - expect: Desktop and backend requirements are presented separately, including platform verification status.
  4. Open `/install` and follow its table-of-contents links to a setup step and troubleshooting section.
    - expect: The target sections are reached and the page explains backend configuration, sign-in, MFA, and checksum verification.

### 2. Authentication and session lifecycle

**Seed:** `N/A — fresh account/session per test; backend and email test configuration required where noted`

#### 2.1. Sign in, restore the session, and sign out

**File:** `tests/auth/login-and-logout.spec.ts`

**Steps:**
  1. With a registered, verified test account and anonymous session, open `/login`.
    - expect: Email and password fields and the sign-in action are visible.
  2. Submit valid credentials.
    - expect: The authenticated session is confirmed and the user is redirected to `/app`.
  3. Reload the page, then directly open `/app/settings`.
    - expect: The session is restored from the server and the protected page remains accessible.
  4. Use “Sign out”.
    - expect: The session is cleared and the browser returns to `/login`; reopening `/app` redirects to sign-in.

#### 2.2. Show a recoverable sign-in error for invalid credentials

**File:** `tests/auth/login-validation.spec.ts`

**Steps:**
  1. Open `/login` and submit invalid credentials.
    - expect: An accessible error message is shown, submission becomes available again, and the user stays on the sign-in page.
  2. Correct the credentials and submit again.
    - expect: A successful login proceeds normally, demonstrating recovery from the error state.

#### 2.3. Register an account and complete the required verification flow

**File:** `tests/auth/registration.spec.ts`

**Steps:**
  1. Open `/register` and submit without accepting the terms or with mismatched confirmation passwords.
    - expect: The form prevents submission and identifies the unmet terms/password requirement.
  2. Enter a valid unique email, a server-accepted password, matching confirmation, and accept the terms; submit.
    - expect: The request succeeds and follows the configured backend result: authenticated dashboard, email verification, or MFA.
  3. Complete the returned verification step using the test environment's supported verification mechanism.
    - expect: The account reaches the expected authenticated or verified state; no success is reported when verification has not completed.

#### 2.4. Request a password reset without exposing account existence

**File:** `tests/auth/password-recovery.spec.ts`

**Steps:**
  1. Open `/forgot-password` and submit a valid email address.
    - expect: A confirmation explains that a reset link was sent if an account matches and does not reveal whether the address is registered.
  2. Activate “try again” and submit an invalid email address.
    - expect: The form shows validation feedback and does not send a request.
  3. Open a valid reset link in the configured test email and submit a valid new password.
    - expect: The password reset succeeds and the user can sign in with the new password.

### 3. Authenticated dashboard workflows

**Seed:** `N/A — provision an authenticated test session; reset the in-memory demo before each scenario`

#### 3.1. Redirect unauthenticated visitors from dashboard routes

**File:** `tests/dashboard/protected-routes.spec.ts`

**Steps:**
  1. In an anonymous browser context, open `/app/transactions` directly.
    - expect: The visitor is redirected to `/login` after the session check; protected dashboard content is not displayed.
  2. Open `/login` after the session check.
    - expect: The sign-in form is displayed rather than a session-verification error when the backend is healthy and confirms an anonymous session.

#### 3.2. Simulate allow, deny, and approval decisions

**File:** `tests/dashboard/simulate-decisions.spec.ts`

**Steps:**
  1. Sign in, open `/app/simulate`, and run “A routine payment”.
    - expect: The result is Allow for the routine trusted airport ride and the recent transaction/activity data reflects the request.
  2. Run “Over a hard limit”.
    - expect: The result is Deny because the request exceeds the agent's per-payment cap.
  3. Run “A suspicious invoice”.
    - expect: The result is Needs approval because the request is from untrusted content; a pending approval is created.
  4. Open the new request in its result panel and follow its approval link.
    - expect: The request details and rules/risk signals correspond to the simulated invoice.

#### 3.3. Review and decide a pending approval

**File:** `tests/dashboard/approval-lifecycle.spec.ts`

**Steps:**
  1. Start from a fresh demo state and create a pending approval by running “A suspicious invoice” in the simulator.
    - expect: The request appears in the pending approval queue and is identified as high risk.
  2. Open its approval details and inspect the amount, merchant, purpose, instruction source, flagged rules, and risk signals.
    - expect: The details match the simulated request and the page presents the reviewer decision controls.
  3. Deny the request and navigate back to the approvals list.
    - expect: The request leaves the pending queue, appears in the denied tab, and the final outcome is reflected in the transaction/audit history.

#### 3.4. Register an agent and update its spending policy

**File:** `tests/dashboard/agents-and-policies.spec.ts`

**Steps:**
  1. Open `/app/agents`, choose “Register agent”, and submit a valid unique lowercase name and optional description.
    - expect: The new agent appears in the list with active status and a default policy.
  2. Inspect the success dialog and close it after recording the generated API key.
    - expect: The raw key is revealed at creation and is not required to remain visible after dismissal.
  3. Open the new agent's policy, change a spending limit, and save.
    - expect: The saved policy displays the updated limit and remains updated while navigating within the current demo session.
  4. Search for the new agent by name, then search for a non-matching term and clear the search.
    - expect: Search filters the list, the no-results state appears for a non-match, and clearing restores the agent list.

#### 3.5. Trace a simulated decision and reset the demo

**File:** `tests/dashboard/transactions-audit-reset.spec.ts`

**Steps:**
  1. From a fresh demo, run an allowed scenario and open the resulting transaction from the result panel or transactions list.
    - expect: The transaction detail displays the decision, request context, and associated timeline.
  2. Open the audit log and locate the events associated with the same request.
    - expect: The audit log shows the request and decision events for the simulated transaction.
  3. Choose “Reset demo”, then cancel the confirmation dialog.
    - expect: The dialog closes and the existing demo data remains unchanged.
  4. Choose “Reset demo” again and confirm.
    - expect: A success notification is shown and sample agents, policies, approvals, transactions, and audit data return to their seed state.

#### 3.6. Navigate the dashboard at a mobile viewport

**File:** `tests/dashboard/mobile-navigation.spec.ts`

**Steps:**
  1. At a mobile viewport, open an authenticated dashboard route.
    - expect: The page fits the viewport and provides an accessible “Open menu” control.
  2. Open the menu, select “Approvals”, and close or dismiss the menu.
    - expect: The approvals route loads and the mobile navigation closes.
  3. Use the skip-to-content link and keyboard navigation on the page.
    - expect: Keyboard users can move to the main content and interactive controls remain operable.

## Release integration gates

The current dashboard workflows use an in-memory demo store. Passing browser tests against that store verifies demo behavior only; it does not establish that agents, policies, approvals, spend decisions, or audit events persist through the backend. Do not mark AgentGate release-ready based only on these demo scenarios or page-render assertions.

Close these gaps in order, and retain the test output and environment/build identifiers as release evidence:

1. **Establish a repeatable test environment.** Start the frontend and backend against a disposable database, confirm health/readiness endpoints, and provide isolated test users and organizations. Add test helpers that create and clean up records without depending on seeded demo state. Do not commit credentials.
2. **Verify authentication and access control against the backend.** Exercise registration/verification as configured, login, reload-based session restoration, logout, and anonymous protected-route redirects using the real session cookie and API. Include the service-unavailable state as a distinct failure case. Gate completion on this before dashboard integration.
3. **Verify payment decisions and human approvals end to end.** Submit requests through the real spend API and assert server-side allow/deny/approval outcomes, including a policy-based DENY. Approve and deny pending requests through the backend, check authorization and stale/duplicate decision handling, and confirm the resulting payment state. The browser simulator is not evidence for these backend guarantees.
4. **Verify persistent agent and policy management.** Create an agent, securely capture its one-time API key in test-only handling, update policy limits and merchant rules, then read them back from the backend. Submit requests proving that the saved policy controls the decision. Verify organization scoping and role restrictions.
5. **Verify audit integrity and cross-screen consistency.** Assert backend audit events for request, decision, approval, policy change, and payment outcomes; run the audit-chain verifier and a tamper-detection test. Confirm the UI presents the corresponding backend records. Client-side demo events and CSV rendering alone do not prove an immutable audit trail.
6. **Complete configured account-security flows.** With test email delivery and MFA encryption configured, verify email registration/verification and password reset through delivered links/codes; exercise TOTP, recovery-code one-time use, and invalid/expired code behavior. Keep OAuth and PayPal sandbox coverage separate unless enabled for the release.
7. **Verify responsive and public onboarding behavior.** Run the mobile dashboard navigation and keyboard/accessibility checks at representative viewports. Test public downloads, disabled/unavailable artifacts, checksums, system requirements, and installation links against the actual published-release state.
8. **Run and record the complete gate.** Execute relevant Playwright tests and focused backend suites in CI, attach the reports, and record any skips or external-service limitations. A flow is verified only when its required action was performed and its outcome was recorded; otherwise mark it blocked or unverified.
