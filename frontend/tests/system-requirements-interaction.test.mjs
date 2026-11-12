/**
 * Property 3: Bug Condition — System Requirements Accessible Interactions
 *
 * **Validates: Requirements 1.11, 1.12, 1.13, 1.14, 1.15**
 *
 * This is a BUG CONDITION EXPLORATION TEST. It encodes the EXPECTED (fixed)
 * behavior: the System Requirements page should provide consistent hover and
 * focus-visible visual feedback, make all important content accessible
 * without hover (always-visible or tap/focus-revealed), and suppress
 * animations when prefers-reduced-motion is enabled.
 *
 * EXPECTED OUTCOME ON UNFIXED CODE: Test FAILS — failure confirms the bug
 * exists. The current SystemRequirementsPage.css defines `tr:hover td` with a
 * background change but no matching `:focus-visible` rule, declares no
 * `transition` properties (so hover feedback is missing/inconsistent), and
 * has no `@media (prefers-reduced-motion: reduce)` block.
 *
 * After the fix, all assertions should PASS.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

// ── Load sources ──────────────────────────────────────────────────────────

const cssSource = await readFile(
  new URL('../src/pages/SystemRequirementsPage.css', import.meta.url),
  'utf8',
)

const tsxSource = await readFile(
  new URL('../src/pages/SystemRequirementsPage.tsx', import.meta.url),
  'utf8',
)

// ── CSS parsing helpers ───────────────────────────────────────────────────

/**
 * Extract rule blocks (selector + body) from CSS, recursively descending
 * into @media blocks so nested rules are captured at the top level. Each
 * comma-separated selector is split into its own entry.
 */
function extractRuleBlocks(css) {
  const cleaned = css.replace(/\/\*[\s\S]*?\*\//g, '').trim()
  const rules = []
  let i = 0
  const n = cleaned.length
  while (i < n) {
    while (i < n && /\s/.test(cleaned[i])) i++
    if (i >= n) break
    const selStart = i
    while (i < n && cleaned[i] !== '{') i++
    if (i >= n) break
    const selector = cleaned.slice(selStart, i).trim()
    i++ // consume '{'
    const bodyStart = i
    let depth = 1
    while (i < n && depth > 0) {
      if (cleaned[i] === '{') depth++
      else if (cleaned[i] === '}') depth--
      i++
    }
    const body = cleaned.slice(bodyStart, i - 1)
    if (selector.startsWith('@')) {
      // Recurse into at-rule (e.g. @media) bodies
      rules.push(...extractRuleBlocks(body))
    } else {
      for (const sel of selector.split(',')) {
        const trimmed = sel.trim()
        if (trimmed) rules.push({ selector: trimmed, body })
      }
    }
  }
  return rules
}

const rules = extractRuleBlocks(cssSource)
const selectors = rules.map((r) => r.selector)
const hoverSelectors = selectors.filter((s) => s.includes(':hover'))
const focusVisibleSelectors = selectors.filter((s) => s.includes(':focus-visible'))

// ── Requirement 1.12: focus-visible equivalent to hover ───────────────────

test('every :hover rule has a matching :focus-visible rule (Req 1.12)', () => {
  assert.ok(
    hoverSelectors.length > 0,
    'Expected at least one :hover rule to exist for comparison',
  )
  for (const hoverSel of hoverSelectors) {
    // Derive the focus-visible counterpart by swapping :hover -> :focus-visible.
    const focusCounterpart = hoverSel.replace(':hover', ':focus-visible')
    assert.ok(
      selectors.includes(focusCounterpart),
      `BUG: ":hover" rule "${hoverSel}" has no matching ":focus-visible" counterpart "${focusCounterpart}" — keyboard focus must give visual feedback equivalent to hover`,
    )
  }
})

test('CSS defines at least one :focus-visible rule (Req 1.12)', () => {
  assert.ok(
    focusVisibleSelectors.length > 0,
    'BUG: SystemRequirementsPage.css defines no :focus-visible styles on any interactive element — keyboard users get no visual focus indicators',
  )
})

// ── Requirement 1.14: prefers-reduced-motion ──────────────────────────────

test('CSS includes a prefers-reduced-motion media query (Req 1.14)', () => {
  assert.ok(
    cssSource.includes('prefers-reduced-motion'),
    'BUG: SystemRequirementsPage.css has no @media (prefers-reduced-motion: reduce) block — transition animations are not suppressed for users who prefer reduced motion',
  )
})

// ── Requirement 1.13 / 1.15: no hover-only content ────────────────────────

test('no content is hidden and revealed only on hover (Req 1.13, 1.15)', () => {
  // A hover-only reveal pattern: an element hidden via display:none in one
  // rule and revealed (display set to a visible value) only in a :hover rule.
  // This withholds content from touch-device and keyboard users.
  const hiddenRules = rules.filter((r) => /display:\s*none/.test(r.body))
  const hoverRevealRules = rules.filter(
    (r) =>
      r.selector.includes(':hover') &&
      /display:\s*(block|flex|inline|grid|contents|inherit|initial)/.test(r.body),
  )
  const hoverOnlyContent = hiddenRules.length > 0 && hoverRevealRules.length > 0

  assert.ok(
    !hoverOnlyContent,
    `BUG: CSS contains a hover-only content reveal pattern (display:none hidden rule(s): ${hiddenRules
      .map((r) => r.selector)
      .join(', ')} revealed on :hover via ${hoverRevealRules
      .map((r) => r.selector)
      .join(', ')}) — content is inaccessible to touch-device and keyboard users`,
  )
})

test('TSX does not use hover-state-driven conditional rendering (Req 1.13, 1.15)', () => {
  // Hover-state-driven rendering (onMouseEnter/onMouseLeave toggling content)
  // makes content hover-only and inaccessible to touch/keyboard users.
  const hasHoverHandler =
    /onMouse(Enter|Leave|Over|Out|Move)/.test(tsxSource) ||
    /\bhover\b/i.test(tsxSource.replace(/className|sr-note|sr-[\w-]+/g, ''))
  assert.ok(
    !hasHoverHandler,
    'BUG: SystemRequirementsPage.tsx uses hover-state-driven rendering (onMouseEnter/onMouseLeave/hover state) — content may be inaccessible without a mouse',
  )
})

// ── Requirement 1.11: consistent transition properties ────────────────────

test('CSS declares transition properties for interactive hover feedback (Req 1.11)', () => {
  assert.ok(
    cssSource.includes('transition'),
    'BUG: SystemRequirementsPage.css declares no transition properties — hover feedback (border, shadow, icon transitions) is missing or inconsistent across interactive elements (cards, table rows)',
  )
})

test('interactive elements have transition properties (Req 1.11)', () => {
  // Interactive elements that receive hover feedback (cards, table rows) should
  // declare transition properties so the feedback is smooth and consistent.
  const interactiveSelectors = ['.sr-component-card', '.sr-table tr']
  const selectorBodies = new Map(rules.map((r) => [r.selector, r.body]))
  const missing = []
  for (const sel of interactiveSelectors) {
    const body = selectorBodies.get(sel)
    if (!body || !/transition\s*:/.test(body)) {
      missing.push(sel)
    }
  }
  assert.equal(
    missing.length,
    0,
    `BUG: interactive elements lack transition properties: ${missing.join(', ')} — hover feedback (border/shadow/icon transitions) is missing or inconsistent`,
  )
})
