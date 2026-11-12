/**
 * Property 4: Bug Condition — 404 Not Found Page Minimal and Off-Brand
 *
 * **Validates: Requirements 1.16, 1.17, 1.18, 1.19**
 *
 * This is a BUG CONDITION EXPLORATION TEST. It encodes the EXPECTED (fixed)
 * behavior: the 404 Not Found page should provide a polished, AgentGate-branded
 * experience using the landing-page layout with header and footer, the heading
 * "404 — Page not found", multiple recovery actions (homepage, dashboard if
 * authenticated, go back), and auth-awareness to distinguish dashboard 404s
 * from public 404s.
 *
 * EXPECTED OUTCOME ON UNFIXED CODE: Test FAILS — failure confirms the bug
 * exists. The current NotFoundPage.tsx uses a generic EmptyState component,
 * does not import LandingHeader or LandingFooter, shows only "Page not found"
 * (not "404 — Page not found"), offers only a single "/app" link, and does
 * not call useSession for auth-awareness. App.tsx has two catch-all path="*"
 * routes (one inside the /app layout, one at the top level) both pointing to
 * the same context-blind NotFoundPage.
 *
 * After the fix, all assertions should PASS.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

// ── Load sources ──────────────────────────────────────────────────────────

const pageSource = await readFile(
  new URL('../src/pages/NotFoundPage.tsx', import.meta.url),
  'utf8',
)

const appSource = await readFile(
  new URL('../src/App.tsx', import.meta.url),
  'utf8',
)

// ── Requirement 1.16 / 1.17: not using branded landing layout ─────────────

test('page imports EmptyState (bug: should use branded layout instead) (Req 1.16, 1.17)', () => {
  assert.ok(
    !pageSource.includes("import EmptyState"),
    "BUG: NotFoundPage imports EmptyState — the 404 page should use the AgentGate-branded landing-page layout (LandingHeader + LandingFooter) instead of the generic EmptyState component",
  )
})

test('page does not import LandingHeader (bug: not using landing layout) (Req 1.17)', () => {
  assert.ok(
    pageSource.includes('LandingHeader'),
    "BUG: NotFoundPage does not import LandingHeader — the 404 experience must match the product's visual identity using the landing-page layout structure with header and footer",
  )
})

test('page does not import LandingFooter (bug: not using landing layout) (Req 1.17)', () => {
  assert.ok(
    pageSource.includes('LandingFooter'),
    "BUG: NotFoundPage does not import LandingFooter — the 404 experience must match the product's visual identity using the landing-page layout structure with header and footer",
  )
})

// ── Requirement 1.17: missing branded heading ──────────────────────────────

test('heading text is "Page not found" not "404 — Page not found" (bug: missing branded heading) (Req 1.17)', () => {
  assert.ok(
    !pageSource.includes('"Page not found"') && !pageSource.includes("'Page not found'"),
    'BUG: NotFoundPage uses heading "Page not found" — the fixed page must display "404 — Page not found" as the heading to conform to the AgentGate-branded 404 experience',
  )
  assert.ok(
    pageSource.includes('404'),
    'BUG: NotFoundPage heading does not include "404" — the branded heading must be "404 — Page not found"',
  )
})

// ── Requirement 1.18: missing homepage and go-back actions ────────────────

test('page offers only the single action linking to /app (bug: missing homepage, go-back actions) (Req 1.18)', () => {
  // The fix must offer at minimum: homepage ("/"), dashboard ("/app" if
  // authenticated), and a go-back action. Count distinct Link/anchor targets.
  const homepageLinkPresent =
    pageSource.includes('to="/"') ||
    pageSource.includes("to='/'") ||
    pageSource.includes('href="/"') ||
    pageSource.includes("href='/'")

  assert.ok(
    homepageLinkPresent,
    'BUG: NotFoundPage does not offer a link to the homepage ("/") — the 404 page must provide at minimum a homepage link, a dashboard link (if authenticated), and a go-back action',
  )
})

test('page does not include a go-back action (Req 1.18)', () => {
  const hasGoBack =
    pageSource.includes('history.back') ||
    pageSource.includes('useNavigate') ||
    pageSource.includes('window.history') ||
    pageSource.includes('goBack') ||
    pageSource.includes('go(-1)')

  assert.ok(
    hasGoBack,
    "BUG: NotFoundPage does not include a 'go back' action (history.back / useNavigate go(-1)) — the 404 page must offer a 'go back' recovery option",
  )
})

// ── Requirement 1.19: not auth-aware ──────────────────────────────────────

test('page does not call useSession (bug: not auth-aware) (Req 1.19)', () => {
  assert.ok(
    pageSource.includes('useSession'),
    "BUG: NotFoundPage does not call useSession — the page must distinguish between an authenticated dashboard 404 (show dashboard link) and a public 404, so it must import and use useSession",
  )
})

// ── Requirement 1.19: App.tsx context-blindness verification ──────────────

test('App.tsx has two catch-all path="*" routes (confirms context-blindness bug) (Req 1.19)', () => {
  // Both the /app protected layout and the top-level public layout use the
  // same context-blind NotFoundPage. This confirms the bug is context-blindness
  // in the page component itself, not a missing or mis-placed route.
  const catchAllMatches = [...appSource.matchAll(/path="\*"/g)]
  assert.equal(
    catchAllMatches.length,
    2,
    `Expected exactly 2 catch-all path="*" routes in App.tsx (one inside /app layout, one at top-level public layout), found ${catchAllMatches.length}`,
  )
})

test('both catch-all routes in App.tsx point to NotFoundPage (confirms same component used in both contexts) (Req 1.19)', () => {
  // Confirm that the context-blindness is in the page component: both routes
  // use the same NotFoundPage regardless of auth context.
  const notFoundPageRoutes = [
    ...appSource.matchAll(/path="\*"[^>]*NotFoundPage|NotFoundPage[^>]*path="\*"/g),
  ]

  // Use a broader check: both occurrences of path="*" must be followed by
  // a reference to NotFoundPage in the same Route element.
  const routePattern = /path="\*" lazy=\{page\(\(\) => import\('\.\/pages\/NotFoundPage'\)\)\}/g
  const matches = [...appSource.matchAll(routePattern)]

  assert.equal(
    matches.length,
    2,
    `Expected exactly 2 catch-all routes pointing to NotFoundPage in App.tsx (one inside /app layout, one at top-level), found ${matches.length}. Bug is context-blindness in the page, not incorrect route placement.`,
  )
})
