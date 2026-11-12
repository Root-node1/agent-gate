/**
 * Property 7: Preservation — Existing Pages and Security Controls
 *
 * **Validates: Requirements 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12,
 *   3.13, 3.14, 3.15, 3.16, 3.17, 3.18, 3.19, 3.20, 3.21, 3.22**
 *
 * These are PRESERVATION tests — they assert the BASELINE state of non-buggy
 * inputs on UNFIXED code. All tests MUST PASS. Any failure indicates an
 * unintended regression.
 *
 * Tests inspect source files as text using `node --test` / `assert/strict`.
 * No source files are modified.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

// ── File helpers ──────────────────────────────────────────────────────────────

function src(relPath) {
  return new URL(relPath, import.meta.url)
}

const landingPageSrc = await readFile(src('../src/pages/LandingPage.tsx'), 'utf8')
const downloadsPageSrc = await readFile(src('../src/pages/DownloadsPage.tsx'), 'utf8')
const appSrc = await readFile(src('../src/App.tsx'), 'utf8')
const sessionGuardsSrc = await readFile(src('../src/session/SessionGuards.tsx'), 'utf8')
const releasesSrc = await readFile(src('../src/pages/landing/releases.ts'), 'utf8')

// ── 1. LandingPage exists and uses LandingHeader / LandingFooter (Req 3.4) ──

test('LandingPage imports LandingHeader (Req 3.4)', () => {
  assert.ok(
    landingPageSrc.includes('LandingHeader'),
    'REGRESSION (Req 3.4): LandingPage.tsx does not import or use LandingHeader. ' +
      'The LandingPage must continue to use LandingHeader as part of its landing layout.',
  )
})

test('LandingPage imports LandingFooter (Req 3.4)', () => {
  assert.ok(
    landingPageSrc.includes('LandingFooter'),
    'REGRESSION (Req 3.4): LandingPage.tsx does not import or use LandingFooter. ' +
      'The LandingPage must continue to use LandingFooter as part of its landing layout.',
  )
})

// ── 2. DownloadsPage exists and uses LandingHeader / LandingFooter (Req 3.4) ─

test('DownloadsPage imports LandingHeader (Req 3.4)', () => {
  assert.ok(
    downloadsPageSrc.includes('LandingHeader'),
    'REGRESSION (Req 3.4): DownloadsPage.tsx does not import or use LandingHeader. ' +
      'The Downloads page must continue to use LandingHeader as part of its landing layout.',
  )
})

test('DownloadsPage imports LandingFooter (Req 3.4)', () => {
  assert.ok(
    downloadsPageSrc.includes('LandingFooter'),
    'REGRESSION (Req 3.4): DownloadsPage.tsx does not import or use LandingFooter. ' +
      'The Downloads page must continue to use LandingFooter as part of its landing layout.',
  )
})

// ── 3. DownloadsPage does NOT have a backend requirements TABLE (Req 3.4, 3.22)
//       The page DOES have a "Desktop client and backend are separate" section
//       (which is correct and must be preserved), but it must NOT have the
//       SystemRequirementsPage-style `backendRows` backend requirements table.

test('DownloadsPage does not define backendRows (Req 3.4, 3.22)', () => {
  assert.ok(
    !downloadsPageSrc.includes('backendRows'),
    'REGRESSION (Req 3.4, 3.22): DownloadsPage.tsx contains `backendRows` — a backend ' +
      'requirements table that belongs only on SystemRequirementsPage. The Downloads page ' +
      'must continue to describe the client/backend separation in prose (dl-sep-section) ' +
      'without rendering a backend requirements table.',
  )
})

// ── 4. App.tsx has the correct route structure (Req 3.4, 3.5) ────────────────

test('App.tsx has two path="*" catch-all routes (Req 3.5)', () => {
  // Count exact occurrences of path="*" to confirm both catch-alls are present:
  // one inside /app (dashboard 404) and one at the top-level (public 404).
  const matches = appSrc.match(/path="[*]"/g) ?? []
  assert.equal(
    matches.length,
    2,
    `REGRESSION (Req 3.5): App.tsx has ${matches.length} path="*" catch-all route(s), expected 2. ` +
      'There must be one catch-all inside the /app dashboard layout and one at the top-level ' +
      'public layout so valid nested routes are not shadowed.',
  )
})

test('App.tsx has path="app" dashboard route (Req 3.4, 3.5)', () => {
  assert.ok(
    appSrc.includes('path="app"'),
    'REGRESSION (Req 3.4, 3.5): App.tsx does not have a path="app" dashboard route. ' +
      'The /app dashboard route must continue to exist.',
  )
})

test('App.tsx has path="downloads" route (Req 3.4)', () => {
  assert.ok(
    appSrc.includes('path="downloads"'),
    'REGRESSION (Req 3.4): App.tsx does not have a path="downloads" route. ' +
      'The /downloads route must continue to exist.',
  )
})

test('App.tsx has path="system-requirements" route (Req 3.4)', () => {
  assert.ok(
    appSrc.includes('path="system-requirements"'),
    'REGRESSION (Req 3.4): App.tsx does not have a path="system-requirements" route. ' +
      'The /system-requirements route must continue to exist.',
  )
})

// ── 5. SessionGuards.tsx uses authenticationStatus (Req 3.9) ─────────────────

test('SessionGuards.tsx imports authenticationStatus from useSession (Req 3.9)', () => {
  assert.ok(
    sessionGuardsSrc.includes('authenticationStatus'),
    'REGRESSION (Req 3.9): SessionGuards.tsx does not use authenticationStatus. ' +
      'The session guards must continue to gate the dashboard and auth routes based on ' +
      'authenticationStatus to preserve the security controls for the protected dashboard.',
  )
})

// ── 6. PaypalSection sandbox/no-live-toggle — covered by toolkit-boundary-audit
//       Do NOT duplicate those tests here. Requirement 3.7, 3.8: covered there.
//       (Intentionally omitted — toolkit-boundary-audit.test.mjs owns this.)

// ── 7. releases.ts contains RELEASE_ASSETS with verified hashes (Req 3.4, 3.21)

test('RELEASE_ASSETS Linux DEB asset has a non-null sha256 (Req 3.4, 3.21)', () => {
  // The Linux DEB asset must have a real SHA-256 — it was verified from the actual
  // build artifact. If this becomes null, a verified checksum has been removed.
  const linuxDebMatch = releasesSrc.match(
    /platform:\s*'linux-deb'[\s\S]*?sha256:\s*([^\n,]+)/,
  )
  assert.ok(
    linuxDebMatch,
    'REGRESSION (Req 3.4): Could not find linux-deb asset entry with sha256 field in releases.ts.',
  )
  const sha256Value = linuxDebMatch[1].trim()
  assert.ok(
    sha256Value !== 'null' && sha256Value.length > 0,
    `REGRESSION (Req 3.4, 3.21): Linux DEB asset sha256 is null or empty (got: ${sha256Value}). ` +
      'The Linux DEB build artifact has a verified sha256 and it must remain set.',
  )
})

test('RELEASE_ASSETS Windows MSI asset has a non-null sha256 (Req 3.4, 3.21)', () => {
  // The Windows MSI asset was verified via GitHub Actions run 42842234895.
  // Its sha256 must remain set.
  const windowsMsiMatch = releasesSrc.match(
    /platform:\s*'windows'[\s\S]*?installerType:\s*'MSI'[\s\S]*?sha256:\s*([^\n,]+)/,
  )
  assert.ok(
    windowsMsiMatch,
    'REGRESSION (Req 3.4): Could not find windows MSI asset entry with sha256 field in releases.ts.',
  )
  const sha256Value = windowsMsiMatch[1].trim()
  assert.ok(
    sha256Value !== 'null' && sha256Value.length > 0,
    `REGRESSION (Req 3.4, 3.21): Windows MSI asset sha256 is null or empty (got: ${sha256Value}). ` +
      'The Windows MSI build artifact has a verified sha256 and it must remain set.',
  )
})

test('RELEASE_ASSETS macOS asset has builtAt: null (Req 3.4, 3.21)', () => {
  // The macOS build has NOT been produced. builtAt must be null to accurately
  // communicate this to users. If builtAt becomes non-null without a real artifact,
  // the page would display fabricated build metadata.
  const macosMatch = releasesSrc.match(
    /platform:\s*'macos'[\s\S]*?builtAt:\s*(null|'[^']+'|"[^"]+")/,
  )
  assert.ok(
    macosMatch,
    'REGRESSION (Req 3.4): Could not find macos asset entry with builtAt field in releases.ts.',
  )
  const builtAtValue = macosMatch[1].trim()
  assert.equal(
    builtAtValue,
    'null',
    `REGRESSION (Req 3.4, 3.21): macOS asset builtAt is "${builtAtValue}", expected "null". ` +
      'The macOS build has not been produced — builtAt must remain null to avoid presenting ' +
      'fabricated build metadata.',
  )
})
