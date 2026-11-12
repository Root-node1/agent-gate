/**
 * Property 2: Bug Condition — System Requirements Desktop-Only Content
 *
 * **Validates: Requirements 1.7, 1.8, 1.9, 1.10**
 *
 * This is a BUG CONDITION EXPLORATION TEST. It encodes the EXPECTED (fixed)
 * behavior: the System Requirements page should display ONLY desktop-client
 * operating system requirements derived exclusively from verified sources
 * (Tauri config, build artifacts, CI workflows), with no backend
 * infrastructure tables, no component-separation section, and no fabricated
 * platform details.
 *
 * EXPECTED OUTCOME ON UNFIXED CODE: Test FAILS — failure confirms the bug
 * exists. The page currently renders backend architecture content (backendRows,
 * sr-sep-row dual cards, Caddy/Let's Encrypt/PostgreSQL/Redis) and lists
 * unverified macOS platform details without a build artifact.
 *
 * After the fix, all assertions should PASS.
 */

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { loadTypeScriptModule } from './helpers/load-typescript.mjs'

// ── Load sources ──────────────────────────────────────────────────────────

// SystemRequirementsPage.tsx imports lucide-react, react-router, CSS, and
// landing components that cannot resolve in a node --test environment, so we
// inspect the component source as text for static structural analysis.
const pageSource = await readFile(
  new URL('../src/pages/SystemRequirementsPage.tsx', import.meta.url),
  'utf8',
)

// releases.ts has no external imports and can be loaded as a module.
const { module: releases } = await loadTypeScriptModule(
  '../../src/pages/landing/releases.ts',
)

// Tauri config is the authoritative source for desktop platform support.
const tauriConfig = JSON.parse(
  await readFile(
    new URL('../src-tauri/tauri.conf.json', import.meta.url),
    'utf8',
  ),
)

// ── Requirement 1.7: No backend architecture content ──────────────────────

test('page does not define a backendRows array (Req 1.7)', () => {
  assert.ok(
    !pageSource.includes('backendRows'),
    'BUG: SystemRequirementsPage defines backendRows array — the page should NOT include backend requirements (PostgreSQL, Redis, Docker Compose, Caddy) on a desktop-client-only page',
  )
})

test('SYSTEM_REQUIREMENTS does not include a backend entry (Req 1.7)', () => {
  assert.ok(
    !('backend' in releases.SYSTEM_REQUIREMENTS),
    `BUG: SYSTEM_REQUIREMENTS includes a "backend" entry (${JSON.stringify(releases.SYSTEM_REQUIREMENTS.backend)}) — the requirements object must be scoped to desktop client platforms only`,
  )
})

// ── Requirement 1.8: No component-separation section ──────────────────────

test('page does not render the component-separation section (Req 1.8)', () => {
  assert.ok(
    !pageSource.includes('sr-sep-row'),
    'BUG: SystemRequirementsPage renders sr-sep-row — the Desktop Client + Backend dual-card section must be removed',
  )
  assert.ok(
    !pageSource.includes('sr-sep-divider'),
    'BUG: SystemRequirementsPage renders sr-sep-divider — the "+" divider between component cards must be removed',
  )
  assert.ok(
    !pageSource.includes('sr-component-card'),
    'BUG: SystemRequirementsPage renders sr-component-card — the backend architecture card must be removed',
  )
})

// ── Requirement 1.9: No backend Network/Storage entries ───────────────────

test('page does not include backend Network Requirements entries (Req 1.9)', () => {
  assert.ok(
    !pageSource.includes('Caddy'),
    'BUG: SystemRequirementsPage includes "Caddy" (backend reverse proxy) in Network Requirements — irrelevant to desktop client compatibility',
  )
  assert.ok(
    !pageSource.includes("Let's Encrypt"),
    'BUG: SystemRequirementsPage includes "Let\'s Encrypt" (backend TLS provisioning) in Network Requirements — irrelevant to desktop client compatibility',
  )
  assert.ok(
    !pageSource.includes('HTTPS with a valid TLS certificate'),
    'BUG: SystemRequirementsPage includes production HTTPS certificate guidance — a backend deployment concern, not a desktop client requirement',
  )
  assert.ok(
    !pageSource.includes('PayPal Sandbox API'),
    'BUG: SystemRequirementsPage includes "PayPal Sandbox API" — a backend-only requirement, not a desktop client requirement',
  )
})

test('page does not include backend Storage Requirements entries (Req 1.9)', () => {
  assert.ok(
    !pageSource.includes('Backend (database)'),
    'BUG: SystemRequirementsPage includes "Backend (database)" storage entry — PostgreSQL database size is a backend deployment concern',
  )
  assert.ok(
    !pageSource.includes('PostgreSQL'),
    'BUG: SystemRequirementsPage includes "PostgreSQL" in Storage Requirements — backend database, not desktop client storage',
  )
  assert.ok(
    !pageSource.includes('Redis'),
    'BUG: SystemRequirementsPage includes "Redis" in Storage Requirements — backend cache/queue broker, not desktop client storage',
  )
})

// ── Requirement 1.10: Platform info from verified sources only ─────────────

test('platform entries are backed by verified build artifacts (Req 1.10)', () => {
  // Each platform listed in SYSTEM_REQUIREMENTS must derive its OS, CPU,
  // and architecture claims from verified sources: Tauri config targets,
  // Rust target config, build workflows, or existing build artifacts.
  //
  // A platform with a specific OS version claim but no build artifact
  // (builtAt === null) is presenting an unverified detail.

  const tauriTargets = tauriConfig.bundle.targets // "all" or a list
  const tauriSupportsAll = tauriTargets === 'all'

  // Build a set of platforms that have verified build artifacts
  // (builtAt is not null and status is not 'coming-soon')
  const verifiedPlatforms = new Set()
  for (const asset of releases.RELEASE_ASSETS) {
    if (asset.builtAt !== null && asset.status !== 'coming-soon') {
      if (asset.platform === 'windows') verifiedPlatforms.add('windows')
      else if (asset.platform.startsWith('linux-')) verifiedPlatforms.add('linux')
      else if (asset.platform === 'macos') verifiedPlatforms.add('macos')
    }
  }

  const platformKeys = Object.keys(releases.SYSTEM_REQUIREMENTS).filter(
    (key) => key !== 'backend',
  )

  for (const platform of platformKeys) {
    const entry = releases.SYSTEM_REQUIREMENTS[platform]

    // Platform must be supported by Tauri config
    const tauriSupported =
      tauriSupportsAll ||
      (Array.isArray(tauriTargets) && tauriTargets.includes(platform))
    assert.ok(
      tauriSupported,
      `Platform "${platform}" is not supported by Tauri config (targets=${JSON.stringify(tauriTargets)}) — only Tauri-configured platforms should appear`,
    )

    // If the platform has a specific OS version claim, it must have a
    // verified build artifact to back that claim
    if (entry && entry.os) {
      const hasArtifact = verifiedPlatforms.has(platform)
      assert.ok(
        hasArtifact,
        `Platform "${platform}" claims OS "${entry.os}" but has NO verified build artifact (builtAt is null, status is 'coming-soon'). Platform support information must be derived exclusively from verified sources — a specific OS version claim without a build artifact is unverified/fabricated.`,
      )
    }
  }
})
