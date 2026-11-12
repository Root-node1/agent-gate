/**
 * Property 5: Bug Condition — Global UX Standardization
 *
 * **Validates: Requirements 1.20, 1.21, 1.22, 1.23, 1.24**
 *
 * This is a BUG CONDITION EXPLORATION TEST. It encodes the EXPECTED (fixed)
 * behavior: every dashboard page should use `useApiResource` for data
 * fetching (instead of `useDemoState`) and must handle loading, error, and
 * empty states consistently. Forms must disable the submit button while
 * submitting and show inline field errors. Auth-state transitions must use
 * `authenticationStatus`.
 *
 * EXPECTED OUTCOME ON UNFIXED CODE: Multiple tests FAIL — failures confirm
 * the bugs exist. The current pages use `useDemoState` (a demo-only in-memory
 * store) instead of `useApiResource` (the real API-driven hook), so they do
 * not make real backend calls, cannot show API-driven error states, and do not
 * use the standardized loading/error/empty patterns expected of a production
 * app.
 *
 * After the fix, all assertions should PASS.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

// ── Helper: load a page source file ──────────────────────────────────────────

async function loadPage(relativePath) {
  return readFile(new URL(`../src/${relativePath}`, import.meta.url), 'utf8')
}

// ── Load all dashboard page sources ──────────────────────────────────────────

const [
  agentsPageSrc,
  approvalsPageSrc,
  auditLogPageSrc,
  policiesPageSrc,
  settingsPageSrc,
  simulatePageSrc,
  transactionsPageSrc,
  overviewPageSrc,
  agentDetailPageSrc,
  approvalDetailPageSrc,
  policyEditPageSrc,
  transactionDetailPageSrc,
  testerPageSrc,
  requestsPageSrc,
  requestDetailPageSrc,
] = await Promise.all([
  loadPage('pages/app/AgentsPage.tsx'),
  loadPage('pages/app/ApprovalsPage.tsx'),
  loadPage('pages/app/AuditLogPage.tsx'),
  loadPage('pages/app/PoliciesPage.tsx'),
  loadPage('pages/app/SettingsPage.tsx'),
  loadPage('pages/app/SimulatePage.tsx'),
  loadPage('pages/app/TransactionsPage.tsx'),
  loadPage('pages/app/OverviewPage.tsx'),
  loadPage('pages/app/AgentDetailPage.tsx'),
  loadPage('pages/app/ApprovalDetailPage.tsx'),
  loadPage('pages/app/PolicyEditPage.tsx'),
  loadPage('pages/app/TransactionDetailPage.tsx'),
  loadPage('pages/live/TesterPage.tsx'),
  loadPage('pages/live/RequestsPage.tsx'),
  loadPage('pages/live/RequestDetailPage.tsx'),
])

// ── Load form sources ─────────────────────────────────────────────────────────

const [
  agentsPageForFormSrc,   // RegisterAgentModal is in AgentsPage's agents/ subdir; check AgentsPage itself too
  registerAgentModalSrc,
  policyFormSrc,
  paypalSectionSrc,
  loginPageSrc,
  registerPageSrc,
] = await Promise.all([
  loadPage('pages/app/AgentsPage.tsx'),
  loadPage('pages/app/agents/RegisterAgentModal.tsx'),
  loadPage('pages/app/policies/PolicyForm.tsx'),
  loadPage('pages/app/settings/PaypalSection.tsx'),
  loadPage('pages/auth/LoginPage.tsx'),
  loadPage('pages/auth/RegisterPage.tsx'),
])

// ── Load session sources ──────────────────────────────────────────────────────

const [sessionProviderSrc, sessionGuardsSrc] = await Promise.all([
  loadPage('session/SessionProvider.tsx'),
  loadPage('session/SessionGuards.tsx'),
])

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 1: Dashboard pages — useApiResource vs useDemoState (Req 1.20)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Each dashboard page should use `useApiResource` for real API-driven state
 * management. The current code uses `useDemoState` (a demo-only in-memory
 * store), which is the bug. After the fix, `useApiResource` must be present.
 */

const DASHBOARD_PAGES = [
  { name: 'AgentsPage', src: agentsPageSrc },
  { name: 'ApprovalsPage', src: approvalsPageSrc },
  { name: 'AuditLogPage', src: auditLogPageSrc },
  { name: 'PoliciesPage', src: policiesPageSrc },
  { name: 'SettingsPage', src: settingsPageSrc },
  { name: 'SimulatePage', src: simulatePageSrc },
  { name: 'TransactionsPage', src: transactionsPageSrc },
  { name: 'OverviewPage', src: overviewPageSrc },
  { name: 'AgentDetailPage', src: agentDetailPageSrc },
  { name: 'ApprovalDetailPage', src: approvalDetailPageSrc },
  { name: 'PolicyEditPage', src: policyEditPageSrc },
  { name: 'TransactionDetailPage', src: transactionDetailPageSrc },
  { name: 'TesterPage', src: testerPageSrc },
  { name: 'RequestsPage', src: requestsPageSrc },
  { name: 'RequestDetailPage', src: requestDetailPageSrc },
]

for (const { name, src } of DASHBOARD_PAGES) {
  test(`${name} uses useApiResource (bug: currently uses useDemoState or no API hook) (Req 1.20)`, () => {
    assert.ok(
      src.includes('useApiResource'),
      `BUG: ${name} does not use useApiResource — the page must use the shared useApiResource hook for API-driven data fetching instead of the demo-only useDemoState or useSimulatedLoad patterns. After the fix, every dashboard page must call useApiResource to fetch its data from the real backend.`,
    )
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 2: Dashboard pages — loading state (Req 1.20)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Loading state patterns. After the fix, pages should use `isLoading` (from
 * useApiResource) rather than the demo's `useSimulatedLoad`. We also accept
 * SkeletonRows, aria-busy, and similar patterns as evidence of a loading state.
 */

const PAGES_WITH_LOADING_STATE = [
  { name: 'AgentsPage', src: agentsPageSrc },
  { name: 'ApprovalsPage', src: approvalsPageSrc },
  { name: 'AuditLogPage', src: auditLogPageSrc },
  { name: 'PoliciesPage', src: policiesPageSrc },
  { name: 'SettingsPage', src: settingsPageSrc },
  { name: 'TransactionsPage', src: transactionsPageSrc },
  { name: 'OverviewPage', src: overviewPageSrc },
  { name: 'AgentDetailPage', src: agentDetailPageSrc },
  { name: 'ApprovalDetailPage', src: approvalDetailPageSrc },
  { name: 'PolicyEditPage', src: policyEditPageSrc },
]

for (const { name, src } of PAGES_WITH_LOADING_STATE) {
  test(`${name} renders a loading state (Req 1.20)`, () => {
    const hasLoadingState =
      src.includes('SkeletonRows') ||
      src.includes('isLoading') ||
      src.includes('aria-busy') ||
      src.includes('useSimulatedLoad') ||
      src.includes('Loading') ||
      src.includes('skeleton')

    assert.ok(
      hasLoadingState,
      `BUG: ${name} does not render a loading state (SkeletonRows, isLoading, aria-busy, etc.) — every API-driven dashboard page must show a loading indicator while data is being fetched.`,
    )
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 3: Dashboard pages — error state (Req 1.20)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Error state patterns. After the fix, pages must render an error state when
 * the API call fails. Currently, demo pages do not use real API error handling.
 * Pages using useApiResource will have an `error` or `ApiError` or catch block.
 *
 * Pages that only use useDemoState (never make API calls) will FAIL this check
 * — confirming the bug.
 */

const PAGES_REQUIRING_ERROR_STATE = [
  { name: 'AgentsPage', src: agentsPageSrc },
  { name: 'ApprovalsPage', src: approvalsPageSrc },
  { name: 'AuditLogPage', src: auditLogPageSrc },
  { name: 'PoliciesPage', src: policiesPageSrc },
  { name: 'TransactionsPage', src: transactionsPageSrc },
  { name: 'OverviewPage', src: overviewPageSrc },
  { name: 'AgentDetailPage', src: agentDetailPageSrc },
  { name: 'ApprovalDetailPage', src: approvalDetailPageSrc },
  { name: 'PolicyEditPage', src: policyEditPageSrc },
  { name: 'TransactionDetailPage', src: transactionDetailPageSrc },
  { name: 'RequestDetailPage', src: requestDetailPageSrc },
]

for (const { name, src } of PAGES_REQUIRING_ERROR_STATE) {
  test(`${name} renders an error state (Req 1.20)`, () => {
    const hasErrorState =
      // useApiResource surfaces `error` from the hook
      /\berror\b.*ApiError|\bApiError\b|isError|catch\s*\(|\.catch\(|error\s*&&|error\s*\?/.test(src) ||
      src.includes('ApiError') ||
      // form-error or alert role indicating an error presentation
      src.includes('form-error') ||
      src.includes('role="alert"') ||
      // general error variable used in JSX
      (src.includes('error') && src.includes('role="alert"'))

    assert.ok(
      hasErrorState,
      `BUG: ${name} does not render an error state (ApiError, error boundary, role="alert", catch block, etc.) — every API-driven dashboard page must handle API errors and display a meaningful error message to the user.`,
    )
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 4: Dashboard pages — empty state (Req 1.20)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Empty state patterns. Pages must render an empty state when the result set
 * is empty. This checks for EmptyState component, "No results", length === 0,
 * or similar patterns.
 */

const PAGES_REQUIRING_EMPTY_STATE = [
  { name: 'AgentsPage', src: agentsPageSrc },
  { name: 'ApprovalsPage', src: approvalsPageSrc },
  { name: 'AuditLogPage', src: auditLogPageSrc },
  { name: 'PoliciesPage', src: policiesPageSrc },
  { name: 'TransactionsPage', src: transactionsPageSrc },
  { name: 'OverviewPage', src: overviewPageSrc },
  { name: 'AgentDetailPage', src: agentDetailPageSrc },
  { name: 'ApprovalDetailPage', src: approvalDetailPageSrc },
  { name: 'PolicyEditPage', src: policyEditPageSrc },
  { name: 'TransactionDetailPage', src: transactionDetailPageSrc },
]

for (const { name, src } of PAGES_REQUIRING_EMPTY_STATE) {
  test(`${name} renders an empty state (Req 1.20)`, () => {
    const hasEmptyState =
      src.includes('EmptyState') ||
      src.includes('empty') ||
      src.includes('No results') ||
      src.includes('length === 0') ||
      src.includes('.length === 0') ||
      src.includes("length === 0") ||
      /No\s+\w+\s+yet|Nothing\s+here|No\s+\w+\s+found|empty/.test(src)

    assert.ok(
      hasEmptyState,
      `BUG: ${name} does not render an empty state (EmptyState, "No results", empty check, etc.) — every list page must show an empty state when the API returns zero results.`,
    )
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 5: Pages that use useDemoState — confirms the bug (Req 1.20)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * This section explicitly asserts that the pages do NOT use the demo-only
 * useDemoState. The fixed pages should use real API hooks instead.
 * These tests will FAIL on unfixed code and PASS once the pages are refactored.
 */

const PAGES_USING_DEMO_STATE = [
  { name: 'AgentsPage', src: agentsPageSrc },
  { name: 'ApprovalsPage', src: approvalsPageSrc },
  { name: 'AuditLogPage', src: auditLogPageSrc },
  { name: 'PoliciesPage', src: policiesPageSrc },
  { name: 'SettingsPage', src: settingsPageSrc },
  { name: 'SimulatePage', src: simulatePageSrc },
  { name: 'TransactionsPage', src: transactionsPageSrc },
  { name: 'OverviewPage', src: overviewPageSrc },
  { name: 'AgentDetailPage', src: agentDetailPageSrc },
  { name: 'ApprovalDetailPage', src: approvalDetailPageSrc },
  { name: 'PolicyEditPage', src: policyEditPageSrc },
  { name: 'TransactionDetailPage', src: transactionDetailPageSrc },
]

for (const { name, src } of PAGES_USING_DEMO_STATE) {
  test(`${name} does not import useDemoState (bug: should use API hooks, not demo store) (Req 1.20)`, () => {
    assert.ok(
      !src.includes('useDemoState'),
      `BUG: ${name} imports useDemoState — the page must be refactored to use real API hooks (useApiResource) instead of the demo-only in-memory store. useDemoState is incompatible with production API-driven data fetching.`,
    )
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 6: Pages that use useSimulatedLoad — confirms the bug (Req 1.20)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * useSimulatedLoad is a demo-only hook that fakes a loading delay. After the
 * fix, loading state must come from useApiResource's isLoading flag, not a
 * simulated timer. These tests will FAIL on unfixed code.
 */

const PAGES_USING_SIMULATED_LOAD = [
  { name: 'AgentsPage', src: agentsPageSrc },
  { name: 'ApprovalsPage', src: approvalsPageSrc },
  { name: 'AuditLogPage', src: auditLogPageSrc },
  { name: 'PoliciesPage', src: policiesPageSrc },
  { name: 'SettingsPage', src: settingsPageSrc },
  { name: 'TransactionsPage', src: transactionsPageSrc },
  { name: 'OverviewPage', src: overviewPageSrc },
  { name: 'AgentDetailPage', src: agentDetailPageSrc },
  { name: 'ApprovalDetailPage', src: approvalDetailPageSrc },
  { name: 'PolicyEditPage', src: policyEditPageSrc },
]

for (const { name, src } of PAGES_USING_SIMULATED_LOAD) {
  test(`${name} does not use useSimulatedLoad (bug: loading must come from useApiResource, not a timer) (Req 1.20)`, () => {
    assert.ok(
      !src.includes('useSimulatedLoad'),
      `BUG: ${name} uses useSimulatedLoad (a demo-only hook) instead of the real isLoading state from useApiResource. Loading state must be driven by the actual API call status, not a simulated delay timer.`,
    )
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 7: Form validation — submit button disabled while submitting (Req 1.21)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Each form must disable the submit button while submission is in progress.
 * We check for `isSubmitting`, `submitting`, `disabled={...}`, or `pending`.
 */

test('RegisterAgentModal submit button is disabled while submitting (Req 1.21)', () => {
  // RegisterAgentModal uses a separate submit button in the Modal footer,
  // but it does not have an isSubmitting/disabled state — it relies on
  // synchronous demo store operations (no async API call, no isSubmitting state).
  const hasSubmitDisable =
    registerAgentModalSrc.includes('isSubmitting') ||
    registerAgentModalSrc.includes('disabled={submitting') ||
    registerAgentModalSrc.includes('disabled={isSubmitting') ||
    registerAgentModalSrc.includes('disabled={pending')

  assert.ok(
    hasSubmitDisable,
    'BUG: RegisterAgentModal submit button is not disabled while submitting — the form must disable the submit button when an async API call is in progress (isSubmitting, disabled={submitting}, etc.) to prevent double-submission.',
  )
})

test('PolicyForm submit button is disabled while submitting (Req 1.21)', () => {
  // PolicyForm has disabled={!dirty} on its save button — this prevents saving
  // when there are no changes, but NOT when an async API save is in progress.
  // After the fix, the button must also be disabled while the save API call runs.
  const hasSubmitDisable =
    policyFormSrc.includes('isSubmitting') ||
    policyFormSrc.includes('disabled={submitting') ||
    policyFormSrc.includes('disabled={isSubmitting') ||
    policyFormSrc.includes('disabled={saving') ||
    policyFormSrc.includes('disabled={pending')

  assert.ok(
    hasSubmitDisable,
    'BUG: PolicyForm save button is not disabled while an async API save is in progress — the form must disable the submit button when isSubmitting/saving is true, not just when the form is clean.',
  )
})

test('PaypalSection probe button is disabled while probing (Req 1.21)', () => {
  // PaypalSection does disable the probe button while isProbing — this test
  // should PASS on current code, confirming the probe button pattern is correct.
  const hasDisabledWhileSubmitting =
    paypalSectionSrc.includes('disabled={isProbing}') ||
    paypalSectionSrc.includes('disabled={isSubmitting') ||
    paypalSectionSrc.includes('disabled={submitting')

  assert.ok(
    hasDisabledWhileSubmitting,
    'BUG: PaypalSection probe/save button is not disabled while the async operation is in progress — the button must be disabled while isProbing/isSubmitting is true.',
  )
})

test('LoginPage submit button is disabled while submitting (Req 1.21)', () => {
  // LoginPage uses `disabled={submitting}` — this test should PASS,
  // confirming the auth form pattern is already correct.
  const hasDisabledWhileSubmitting =
    loginPageSrc.includes('disabled={submitting}') ||
    loginPageSrc.includes('disabled={isSubmitting}') ||
    loginPageSrc.includes('disabled={pending}')

  assert.ok(
    hasDisabledWhileSubmitting,
    'BUG: LoginPage submit button is not disabled while submitting — auth forms must disable the submit button during async operations to prevent double-submission.',
  )
})

test('RegisterPage submit button is disabled while submitting (Req 1.21)', () => {
  // RegisterPage uses `disabled={submitting}` — this test should PASS,
  // confirming the auth form pattern is already correct.
  const hasDisabledWhileSubmitting =
    registerPageSrc.includes('disabled={submitting}') ||
    registerPageSrc.includes('disabled={isSubmitting}') ||
    registerPageSrc.includes('disabled={pending}')

  assert.ok(
    hasDisabledWhileSubmitting,
    'BUG: RegisterPage submit button is not disabled while submitting — auth forms must disable the submit button during async operations to prevent double-submission.',
  )
})

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 8: Form validation — inline field errors (Req 1.21)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Each form must show inline field errors. We check for fieldErrors, field-error,
 * ApiError, errors object, or similar patterns.
 */

test('RegisterAgentModal shows inline field errors (Req 1.21)', () => {
  const hasInlineErrors =
    registerAgentModalSrc.includes('field-error') ||
    registerAgentModalSrc.includes('fieldErrors') ||
    registerAgentModalSrc.includes('ApiError') ||
    registerAgentModalSrc.includes('nameError') ||
    registerAgentModalSrc.includes('formError')

  assert.ok(
    hasInlineErrors,
    'BUG: RegisterAgentModal does not show inline field errors — forms must render per-field error messages when validation fails (field-error class, fieldErrors from ApiError, etc.).',
  )
})

test('PolicyForm shows inline field errors (Req 1.21)', () => {
  const hasInlineErrors =
    policyFormSrc.includes('field-error') ||
    policyFormSrc.includes('fieldErrors') ||
    policyFormSrc.includes('ApiError') ||
    policyFormSrc.includes('errors') ||
    policyFormSrc.includes('saveError')

  assert.ok(
    hasInlineErrors,
    'BUG: PolicyForm does not show inline field errors — forms must render per-field error messages when validation fails.',
  )
})

test('PolicyForm shows API-level field errors from ApiError.fieldErrors (Req 1.21)', () => {
  // After the fix, PolicyForm must use ApiError.fieldErrors from the real API
  // response to show server-side validation errors inline.
  const hasApiFieldErrors =
    policyFormSrc.includes('ApiError') ||
    policyFormSrc.includes('fieldErrors') ||
    policyFormSrc.includes('error.details')

  assert.ok(
    hasApiFieldErrors,
    'BUG: PolicyForm does not use ApiError.fieldErrors for server-side validation errors — the form must parse the API error envelope and display per-field errors returned by the backend.',
  )
})

test('LoginPage shows inline error message on failure (Req 1.21)', () => {
  // LoginPage already has: {error ? <p className="auth-error" role="alert">...} 
  // This test should PASS on current code.
  const hasInlineError =
    loginPageSrc.includes('auth-error') ||
    loginPageSrc.includes('field-error') ||
    loginPageSrc.includes('role="alert"')

  assert.ok(
    hasInlineError,
    'BUG: LoginPage does not show inline error messages — auth forms must display error messages inline near the form when login fails.',
  )
})

test('RegisterPage shows inline error message on failure (Req 1.21)', () => {
  // RegisterPage already has: {error ? <p className="auth-error" role="alert">...}
  // This test should PASS on current code.
  const hasInlineError =
    registerPageSrc.includes('auth-error') ||
    registerPageSrc.includes('field-error') ||
    registerPageSrc.includes('role="alert"')

  assert.ok(
    hasInlineError,
    'BUG: RegisterPage does not show inline error messages — auth forms must display error messages inline near the form when registration fails.',
  )
})

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 9: PayPal security — no live payments, no secret exposure (Req 1.22)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * PaypalSection must NOT expose secrets and must enforce sandbox-only mode.
 * These assertions check that the component does not render client secrets or
 * webhook secrets and explicitly shows sandbox mode.
 */

test('PaypalSection does not render client_secret in the UI (Req 1.22)', () => {
  assert.ok(
    !paypalSectionSrc.includes('client_secret'),
    'BUG: PaypalSection renders client_secret — PayPal client secrets must never be exposed to the frontend UI. Only the client_id_preview (truncated) may be shown.',
  )
})

test('PaypalSection does not render webhook_secret in the UI (Req 1.22)', () => {
  assert.ok(
    !paypalSectionSrc.includes('webhook_secret'),
    'BUG: PaypalSection renders webhook_secret — PayPal webhook secrets must never be exposed to the frontend UI.',
  )
})

test('PaypalSection shows sandbox-only mode and does not enable live payments (Req 1.22)', () => {
  // The section must display sandbox mode and must not have UI controls to
  // enable live payments.
  const showsSandbox =
    paypalSectionSrc.includes('sandbox') ||
    paypalSectionSrc.includes('Sandbox') ||
    paypalSectionSrc.includes('SANDBOX')

  assert.ok(
    showsSandbox,
    'BUG: PaypalSection does not display sandbox mode — the PayPal settings section must clearly indicate sandbox-only operation and must not provide controls to enable live payment mode.',
  )
})

test('PaypalSection does not expose a live-payments toggle or enable-live-payments control (Req 1.22)', () => {
  const hasLivePaymentsToggle =
    paypalSectionSrc.includes('enable_live') ||
    paypalSectionSrc.includes('enableLive') ||
    paypalSectionSrc.includes('live_payments_toggle') ||
    paypalSectionSrc.includes('live-payments-toggle') ||
    // A toggle/checkbox specifically to turn live payments on
    /checkbox.*live|live.*checkbox|switch.*live|live.*switch/.test(paypalSectionSrc)

  assert.ok(
    !hasLivePaymentsToggle,
    'BUG: PaypalSection has a live-payments toggle/checkbox — this would allow enabling live payments from the UI, violating the sandbox-only enforcement requirement.',
  )
})

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 10: Auth-state transitions — authenticationStatus (Req 1.23)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * SessionProvider.tsx and SessionGuards.tsx must exist and must use
 * authenticationStatus for consistent auth-state transitions.
 */

test('SessionProvider.tsx exists and exports a SessionProvider component (Req 1.23)', () => {
  assert.ok(
    sessionProviderSrc.length > 0,
    'BUG: SessionProvider.tsx does not exist or is empty — the auth session provider must exist to manage authentication state transitions.',
  )
  assert.ok(
    sessionProviderSrc.includes('SessionProvider') || sessionProviderSrc.includes('export default'),
    'BUG: SessionProvider.tsx does not export a SessionProvider component.',
  )
})

test('SessionGuards.tsx exists and exports ProtectedDashboard and PublicAuthentication (Req 1.23)', () => {
  assert.ok(
    sessionGuardsSrc.length > 0,
    'BUG: SessionGuards.tsx does not exist or is empty — the session guards must exist to protect dashboard routes.',
  )
  assert.ok(
    sessionGuardsSrc.includes('ProtectedDashboard'),
    'BUG: SessionGuards.tsx does not export ProtectedDashboard — the protected dashboard guard must exist to enforce authentication.',
  )
  assert.ok(
    sessionGuardsSrc.includes('PublicAuthentication'),
    'BUG: SessionGuards.tsx does not export PublicAuthentication — the public authentication guard must exist to redirect authenticated users.',
  )
})

test('SessionProvider uses authenticationStatus (Req 1.23)', () => {
  assert.ok(
    sessionProviderSrc.includes('authenticationStatus'),
    'BUG: SessionProvider does not use authenticationStatus — the session provider must track authentication status (loading, authenticated, unauthenticated, pending, error) consistently across all auth-state transitions.',
  )
})

test('SessionGuards uses authenticationStatus for auth-state routing (Req 1.23)', () => {
  assert.ok(
    sessionGuardsSrc.includes('authenticationStatus'),
    'BUG: SessionGuards does not use authenticationStatus — the session guards must check authenticationStatus to handle auth-state transitions consistently (loading, error, pending, authenticated, unauthenticated).',
  )
})

test('SessionGuards handles all required auth states: loading, error, pending, authenticated (Req 1.23)', () => {
  assert.ok(
    sessionGuardsSrc.includes("'loading'") || sessionGuardsSrc.includes('"loading"'),
    'BUG: SessionGuards does not handle the "loading" auth state — guards must show a loading indicator while session is being verified.',
  )
  assert.ok(
    sessionGuardsSrc.includes("'error'") || sessionGuardsSrc.includes('"error"'),
    'BUG: SessionGuards does not handle the "error" auth state — guards must show an error page when session verification fails.',
  )
  assert.ok(
    sessionGuardsSrc.includes("'authenticated'") || sessionGuardsSrc.includes('"authenticated"'),
    'BUG: SessionGuards does not handle the "authenticated" state — guards must redirect authenticated users away from public auth pages.',
  )
  assert.ok(
    sessionGuardsSrc.includes("'pending'") || sessionGuardsSrc.includes('"pending"'),
    'BUG: SessionGuards does not handle the "pending" auth state — guards must handle pending flows (MFA, email verification) consistently.',
  )
})

test('SessionProvider handles session expiry via SESSION_EXPIRED_EVENT (Req 1.23)', () => {
  assert.ok(
    sessionProviderSrc.includes('SESSION_EXPIRED_EVENT'),
    'BUG: SessionProvider does not handle SESSION_EXPIRED_EVENT — when a session expires mid-session, the provider must listen for the expiry event and refresh/reset the auth state uniformly across the app.',
  )
})

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 11: live/RequestDetailPage already uses real API (baseline, Req 1.20)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * RequestDetailPage already uses a real API call (getSpendRequest from
 * spendRequests.ts) and handles error state inline. This confirms the live/
 * pages are further along than the demo dashboard pages — but still must use
 * useApiResource consistently.
 */

test('RequestDetailPage uses a real API call (not useDemoState) (Req 1.20)', () => {
  assert.ok(
    !requestDetailPageSrc.includes('useDemoState'),
    'RequestDetailPage incorrectly uses useDemoState — this live page must use real API calls.',
  )
})

test('RequestDetailPage renders an error state for API failures (Req 1.20)', () => {
  const hasErrorState =
    requestDetailPageSrc.includes('ApiError') ||
    requestDetailPageSrc.includes('form-error') ||
    requestDetailPageSrc.includes('role="alert"') ||
    requestDetailPageSrc.includes('error')

  assert.ok(
    hasErrorState,
    'BUG: RequestDetailPage does not render an error state — the page must handle API errors and display them to the user.',
  )
})

test('TesterPage uses real API (not useDemoState) for submitting spend requests (Req 1.20)', () => {
  assert.ok(
    !testerPageSrc.includes('useDemoState'),
    'BUG: TesterPage uses useDemoState — this live API tester must use real API calls, not the demo store.',
  )
})

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 12: Responsive layout — no hardcoded pixel widths blocking responsiveness (Req 1.24)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Pages must not use hardcoded pixel widths that override responsive layout.
 * We check that pages do not use inline style="width: NNpx" or similar
 * patterns that would break responsive layouts on mobile/tablet.
 *
 * Note: This is a conservative check — it looks for the most egregious cases
 * of hardcoded pixel widths in JSX inline styles.
 */

for (const { name, src } of DASHBOARD_PAGES) {
  test(`${name} does not use hardcoded pixel widths in inline styles (Req 1.24)`, () => {
    // Detect inline style={{ width: 'NNNpx' }} patterns that would break responsiveness
    const hasHardcodedPixelWidth = /style=\{\{[^}]*width:\s*['"]?\d{3,}px/.test(src)

    assert.ok(
      !hasHardcodedPixelWidth,
      `BUG: ${name} uses hardcoded pixel width in an inline style — this can break responsive layouts on tablet/mobile viewports. Use CSS classes with responsive breakpoints instead.`,
    )
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 13: SimulatePage — demo-only, but form validation must be consistent
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * SimulatePage is intentionally demo-only (no backend call), but its inline
 * form validation pattern must still be consistent with the rest of the app.
 * It should disable the submit button while checking and show inline errors.
 */

test('SimulatePage disables the submit button while checking (Req 1.21)', () => {
  const hasDisabledWhileChecking =
    simulatePageSrc.includes('disabled={checking}') ||
    simulatePageSrc.includes('disabled={submitting') ||
    simulatePageSrc.includes('disabled={isSubmitting')

  assert.ok(
    hasDisabledWhileChecking,
    'BUG: SimulatePage does not disable the submit button while the check is in progress — forms must disable the submit/run button while async processing is occurring.',
  )
})

test('SimulatePage shows inline field errors (Req 1.21)', () => {
  const hasInlineErrors =
    simulatePageSrc.includes('field-error') ||
    simulatePageSrc.includes('fieldErrors') ||
    simulatePageSrc.includes('errors.')

  assert.ok(
    hasInlineErrors,
    'BUG: SimulatePage does not show inline field errors — forms must display per-field validation errors inline.',
  )
})
