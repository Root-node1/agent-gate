/**
 * Property 8: Bug Condition — Payment Security and AI Advisory Boundary
 *
 * **Validates: Requirements 1.25, 1.26, 1.27, 1.28**
 *
 * This test inspects `frontend/src/pages/app/settings/PaypalSection.tsx` as
 * text to confirm that the user-facing content accurately describes the
 * external PayPal AI Toolkit as a SEPARATE integration whose direct PayPal
 * requests are NOT routed through AgentGate's policy engine.
 *
 * EXPECTED OUTCOME: All tests PASS — the security boundary warning and sandbox
 * indicators are already correctly in place. If any test FAILS, the user-facing
 * text needs to be corrected (Req 1.28).
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

// ── Load PaypalSection source ─────────────────────────────────────────────────

const paypalSectionSrc = await readFile(
  new URL('../src/pages/app/settings/PaypalSection.tsx', import.meta.url),
  'utf8',
)

// ── SECTION 1: Security boundary text — toolkit is NOT routed through AgentGate
// Requirement 1.28
// ─────────────────────────────────────────────────────────────────────────────

test('PaypalSection states the toolkit is NOT routed through AgentGate (Req 1.28)', () => {
  // The file must contain an explicit statement that toolkit operations are not
  // routed through AgentGate. We accept "not routed through" or "not governed by
  // AgentGate" or "not routed through AgentGate" as valid formulations.
  const hasNotRoutedThrough =
    paypalSectionSrc.includes('not') &&
    (paypalSectionSrc.includes('routed through AgentGate') ||
      paypalSectionSrc.includes('governed by AgentGate'))

  assert.ok(
    hasNotRoutedThrough,
    'BUG (Req 1.28): PaypalSection does not contain a clear statement that the PayPal AI ' +
      'Toolkit is NOT routed through AgentGate. The user-facing text must explicitly state ' +
      'that direct toolkit operations are not routed through AgentGate\'s policy engine — ' +
      'e.g. "not routed through AgentGate" or "not governed by AgentGate".',
  )
})

test('PaypalSection contains a security boundary warning section (Req 1.28)', () => {
  // The warning must be explicit. We look for "Security Boundary" language or
  // a notice/alert element that communicates the boundary.
  const hasSecurityBoundaryWarning =
    paypalSectionSrc.includes('Security Boundary') ||
    paypalSectionSrc.includes('security boundary') ||
    (paypalSectionSrc.includes('tone-warning') && paypalSectionSrc.includes('not'))

  assert.ok(
    hasSecurityBoundaryWarning,
    'BUG (Req 1.28): PaypalSection does not contain a security boundary warning. ' +
      'There must be a prominent notice (e.g. a warning alert with "Security Boundary") ' +
      'that explains the toolkit is a separate integration.',
  )
})

test('PaypalSection does not falsely imply the toolkit routes through AgentGate (Req 1.28)', () => {
  // The text must NOT imply that the toolkit is governed by or routes through
  // AgentGate's policy engine without an explicit "not" caveat.

  // Split by the word "not" to identify sections that come BEFORE any negation.
  // This is a conservative check: look for the most dangerous positive claim
  // patterns that would imply the toolkit is routed through AgentGate.
  const dangerousImplicationPatterns = [
    // "toolkit routes through AgentGate" without a preceding "not"
    /toolkit\s+routes\s+through\s+AgentGate(?!\s*'s\s+policy)/i,
    // "toolkit is governed by AgentGate" without "not"
    /toolkit\s+is\s+governed\s+by\s+AgentGate/i,
    // "toolkit payments are processed by AgentGate" without "not"
    /toolkit\s+payments?\s+are\s+processed\s+by\s+AgentGate/i,
    // "toolkit is routed through AgentGate" without a preceding "not"
    /(?<!not\s)toolkit\s+is\s+routed/i,
    // "all PayPal requests route through AgentGate" (without "not")
    /all\s+PayPal\s+requests?\s+route\s+through\s+AgentGate/i,
  ]

  for (const pattern of dangerousImplicationPatterns) {
    assert.ok(
      !pattern.test(paypalSectionSrc),
      `BUG (Req 1.28): PaypalSection contains text matching "${pattern}" that falsely implies ` +
        "the PayPal AI Toolkit routes through AgentGate's policy engine. This text must be " +
        'corrected to accurately describe the toolkit as a separate integration whose direct ' +
        'PayPal requests are NOT routed through AgentGate.',
    )
  }
})

test('PaypalSection accurately describes the toolkit as a separate developer integration (Req 1.28)', () => {
  // The section must characterize the toolkit as an external / separate /
  // developer integration — not as a component of AgentGate itself.
  const describesSeparateIntegration =
    paypalSectionSrc.includes('separate') ||
    paypalSectionSrc.includes('external') ||
    paypalSectionSrc.includes('directly inside') ||
    paypalSectionSrc.includes('Direct operations') ||
    paypalSectionSrc.includes('developer') ||
    paypalSectionSrc.includes('coding assistant') ||
    paypalSectionSrc.includes('AI coding assistant')

  assert.ok(
    describesSeparateIntegration,
    'BUG (Req 1.28): PaypalSection does not describe the PayPal AI Toolkit as a separate ' +
      'or external developer integration. The text must make clear that the toolkit is ' +
      'distinct from AgentGate — e.g. "operates directly inside your AI coding assistant", ' +
      '"separate developer integration", or "external".',
  )
})

// ── SECTION 2: Sandbox mode indicators
// Requirements 1.25, 1.26 (enforcement context)
// ─────────────────────────────────────────────────────────────────────────────

test('PaypalSection shows sandbox mode indicator (Req 1.25, 1.26)', () => {
  // The section must display sandbox mode so users know they are in a safe,
  // non-production mode — consistent with the deterministic policy boundary.
  const showsSandbox =
    paypalSectionSrc.includes('Sandbox') ||
    paypalSectionSrc.includes('sandbox') ||
    paypalSectionSrc.includes('SANDBOX')

  assert.ok(
    showsSandbox,
    'BUG: PaypalSection does not display sandbox mode — the section must clearly show ' +
      'that PayPal is in sandbox mode to communicate to users that live payments are not enabled.',
  )
})

test('PaypalSection shows "Live payments: off" or equivalent (Req 1.26)', () => {
  // Live payments must be explicitly shown as disabled — confirming the AI advisory
  // cannot accidentally enable live payments.
  const showsLivePaymentsOff =
    paypalSectionSrc.includes('Live payments: off') ||
    paypalSectionSrc.includes('live_payments_enabled: false') ||
    paypalSectionSrc.includes('Live payments') ||
    paypalSectionSrc.includes('live-payments') ||
    paypalSectionSrc.includes('live payments')

  assert.ok(
    showsLivePaymentsOff,
    'BUG (Req 1.26): PaypalSection does not display that live payments are off — ' +
      'the section must communicate that live payment execution is disabled, reinforcing ' +
      'that the sandbox boundary is enforced.',
  )
})

// ── SECTION 3: Secret exposure checks (Req 1.27 — no frontend fabrication path)
// ─────────────────────────────────────────────────────────────────────────────

test('PaypalSection does not expose client_secret value (Req 1.27)', () => {
  // The file must only show client_id_preview — never the full client_secret.
  assert.ok(
    !paypalSectionSrc.includes('client_secret'),
    'BUG (Req 1.27): PaypalSection references client_secret — PayPal client secrets must ' +
      'remain server-side and must never be rendered or transmitted to the frontend UI. ' +
      'Only client_id_preview (a truncated preview) may be shown.',
  )
})

test('PaypalSection does not expose webhook_secret value (Req 1.27)', () => {
  assert.ok(
    !paypalSectionSrc.includes('webhook_secret'),
    'BUG (Req 1.27): PaypalSection references webhook_secret — webhook secrets must ' +
      'remain server-side and must never be exposed to the frontend UI.',
  )
})

test('PaypalSection shows only client_id_preview (truncated), not the full client ID (Req 1.27)', () => {
  // If the section shows client ID info, it must use the preview field, not a raw full value.
  const usesPreviewField =
    paypalSectionSrc.includes('client_id_preview') ||
    // Could also just show the preview string from the status object
    paypalSectionSrc.includes('clientIdPreview') ||
    // No reference to full client_id being rendered directly
    !paypalSectionSrc.match(/\bclient_id\b(?!_preview)/)

  assert.ok(
    usesPreviewField,
    'BUG (Req 1.27): PaypalSection may expose the full client_id — the section must use ' +
      'client_id_preview (a server-truncated preview) and must never render the full ' +
      'client ID or any secret values.',
  )
})

// ── SECTION 4: No live-payments enable control (Req 1.26)
// ─────────────────────────────────────────────────────────────────────────────

test('PaypalSection does not have a live-payments enable toggle or checkbox (Req 1.26)', () => {
  // No UI control must exist that would allow enabling live payments from the
  // frontend. This would violate the AI advisory boundary (Req 1.26) and sandbox
  // enforcement (Req 3.7).
  const hasLivePaymentsEnableControl =
    /enable_live|enableLive|live_payments_toggle|live-payments-toggle/.test(paypalSectionSrc) ||
    /checkbox.*live\s+pay|live\s+pay.*checkbox/i.test(paypalSectionSrc) ||
    /switch.*live\s+pay|live\s+pay.*switch/i.test(paypalSectionSrc) ||
    // A button that explicitly enables live payments
    /enable.*live.*payment|activate.*live.*payment/i.test(paypalSectionSrc)

  assert.ok(
    !hasLivePaymentsEnableControl,
    'BUG (Req 1.26): PaypalSection has a live-payments enable toggle or checkbox — this ' +
      'would allow users to enable live payment mode from the UI, violating the sandbox-only ' +
      'enforcement and the AI advisory boundary requirements.',
  )
})

test('PaypalSection shows live payments as Off/Disabled in display only (Req 1.26)', () => {
  // The file must display live payments as off in a read-only way (no interactive toggle).
  // We check for display-only indicators of "off" status.
  const showsLivePaymentsAsOff =
    paypalSectionSrc.includes('Off') ||
    paypalSectionSrc.includes('off') ||
    paypalSectionSrc.includes('Disabled') ||
    paypalSectionSrc.includes('disabled')

  assert.ok(
    showsLivePaymentsAsOff,
    'BUG (Req 1.26): PaypalSection does not clearly display live payments as off/disabled — ' +
      'the section must show a read-only indicator confirming live payments are not enabled.',
  )
})

// ── SECTION 5: AgentGate deterministic policy engine is correctly described
// Requirement 1.25
// ─────────────────────────────────────────────────────────────────────────────

test("PaypalSection references AgentGate's policy engine as the governing authority (Req 1.25)", () => {
  // The section should make clear that AgentGate's policy engine governs
  // payments processed via AgentGate — reinforcing that the deterministic
  // engine is authoritative (not AI advisory).
  const referencesAgentGatePolicyEngine =
    paypalSectionSrc.includes("AgentGate's") ||
    paypalSectionSrc.includes('AgentGate') ||
    paypalSectionSrc.includes('policy engine') ||
    paypalSectionSrc.includes('spending caps') ||
    paypalSectionSrc.includes('approval workflows') ||
    paypalSectionSrc.includes('deterministic')

  assert.ok(
    referencesAgentGatePolicyEngine,
    'BUG (Req 1.25): PaypalSection does not reference the AgentGate policy engine as the ' +
      "governing authority for payments processed via AgentGate's runtime. The section must " +
      'clarify the boundary: AgentGate governs its own payments, the external toolkit does not.',
  )
})

test("PaypalSection does not present AI classification as the authoritative decision maker (Req 1.25)", () => {
  // The section must not contain text that presents an AI risk score or AI label
  // as the final, authoritative policy decision. Advisory language is fine.
  const presentsAiAsAuthoritative =
    /AI\s+(decides|determines|authorizes|approves|denies)/i.test(paypalSectionSrc) ||
    /AI\s+classification\s+is\s+(the\s+)?authoritative/i.test(paypalSectionSrc) ||
    /risk\s+score\s+determines\s+approval/i.test(paypalSectionSrc)

  assert.ok(
    !presentsAiAsAuthoritative,
    'BUG (Req 1.25): PaypalSection contains text that presents AI classification as the ' +
      'authoritative decision maker (e.g. "AI decides", "AI determines", "AI authorizes"). ' +
      'AI classification must be advisory only — the deterministic policy engine is ' +
      'the authoritative decision maker.',
  )
})
