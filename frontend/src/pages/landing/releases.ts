/**
 * Release metadata for the Downloads page.
 *
 * IMPORTANT: Only add entries here when real artifacts exist and their
 * checksums have been verified. Never invent versions, dates, or checksums.
 *
 * Artifacts source: desktop-tauri worktree build (Oct 31 2026).
 * No GitHub Release exists yet — these are pre-release build artifacts.
 * Windows (MSI/EXE) and macOS (DMG) have not been built.
 */

export type SignatureStatus = 'unsigned' | 'signed' | 'not-applicable'

export interface ReleaseAsset {
  platform: 'windows' | 'linux-deb' | 'linux-rpm' | 'linux-appimage' | 'macos'
  label: string
  description: string
  installerType: string
  os: string
  arch: string
  version: string
  /** ISO 8601 date — only set when an artifact was verified to exist */
  builtAt: string | null
  /** Bytes — only set when measured from a real artifact */
  fileSize: number | null
  /** SHA-256 — only set when computed from a real artifact */
  sha256: string | null
  /** Download URL — null until a GitHub Release is published */
  downloadUrl: string | null
  status: 'available' | 'coming-soon' | 'pending-release'
  /** Authenticode / notarization / package signature status */
  signatureStatus: SignatureStatus
  releaseNotes: string | null
}

/** Version string for the current desktop release. */
export const CURRENT_VERSION = '0.1.0'

/**
 * Minimum system requirements derived from the actual Tauri config and
 * runtime profile of the application.
 */
export const SYSTEM_REQUIREMENTS = {
  windows: {
    os: 'Windows 10 (1903) or later, 64-bit',
    ram: '4 GB minimum, 8 GB recommended',
    storage: '500 MB available',
    cpu: '64-bit (x86_64)',
    webview: 'WebView2 runtime (bundled with Windows 11; downloadable for Windows 10). Installer can bootstrap WebView2 if missing.',
    network: 'Internet access to reach the AgentGate backend',
    notes: 'Native Windows MSI/NSIS builds are produced via GitHub Actions (windows-latest). Not code-signed. Download links stay inactive until a verified public artifact URL exists.',
  },
  linux: {
    os: 'Ubuntu 20.04 LTS or later (DEB), Fedora 36+ / RHEL 8+ (RPM), any modern distro (AppImage)',
    ram: '4 GB minimum',
    storage: '200 MB available (DEB/RPM) or 100 MB AppImage',
    cpu: '64-bit (x86_64)',
    webview: 'WebKitGTK 4.x — installed automatically on DEB/RPM. AppImage bundles its own libraries.',
    network: 'Internet access to reach the AgentGate backend',
    notes: 'DEB, RPM, and AppImage artifacts verified built on Linux x86_64 (Oct 31 2026).',
  },
  macos: {
    os: 'macOS 10.15 Catalina or later',
    ram: '4 GB minimum',
    storage: '200 MB available',
    cpu: '64-bit (x86_64 or Apple Silicon)',
    webview: 'Built-in WKWebView (no additional runtime needed)',
    network: 'Internet access to reach the AgentGate backend',
    notes: 'Build not yet produced on this platform — pending verification.',
  },
  backend: {
    runtime: 'Hosted separately — the desktop application does NOT include the backend',
    components: 'Django 6, PostgreSQL 17, Redis 7, Procrastinate worker',
    hosting: 'Self-hosted (see deployment guide) or provider-hosted',
    url: 'Configurable — the desktop client connects to any reachable AgentGate backend URL',
  },
} as const

export const RELEASE_ASSETS: ReleaseAsset[] = [
  // ── Windows ────────────────────────────────────────────────────────────────
  {
    platform: 'windows',
    label: 'Windows Installer (MSI)',
    description: 'Standard Windows Installer package (WiX). Built on windows-latest via GitHub Actions.',
    installerType: 'MSI',
    os: 'Windows 10 (1903) or later',
    arch: 'x86_64',
    version: CURRENT_VERSION,
    builtAt: '2026-11-10',
    fileSize: 4_464_640,
    sha256: '127abbf53089f4be582a332f9d8197a8f61a379bb17d301ee3e2f3b44141057e',
    downloadUrl: null,
    status: 'pending-release',
    signatureStatus: 'unsigned',
    releaseNotes: 'Verified Windows build artifact (GitHub Actions run 42842234895). Not yet published as a public download.',
  },
  {
    platform: 'windows',
    label: 'Windows Installer (EXE)',
    description: 'NSIS setup executable. Built on windows-latest via GitHub Actions.',
    installerType: 'EXE',
    os: 'Windows 10 (1903) or later',
    arch: 'x86_64',
    version: CURRENT_VERSION,
    builtAt: '2026-11-10',
    fileSize: 3_196_260,
    sha256: '23a1de291436c27209d81a9c4527e3bfe76939c4f6fcdf5ab387195653e4a85a',
    downloadUrl: null,
    status: 'pending-release',
    signatureStatus: 'unsigned',
    releaseNotes: 'Verified Windows build artifact (GitHub Actions run 42842234895). Not yet published as a public download.',
  },
  // ── Linux ──────────────────────────────────────────────────────────────────
  {
    platform: 'linux-deb',
    label: 'Linux DEB package',
    description: 'Debian / Ubuntu package — installs via dpkg or apt',
    installerType: 'DEB',
    os: 'Ubuntu 20.04+ / Debian 11+',
    arch: 'amd64 (x86_64)',
    version: CURRENT_VERSION,
    builtAt: '2026-10-31',
    fileSize: 3_564_544,     // measured: 3.4 MB
    sha256: 'be8b308e02828f14c3b04953b7407874d2eeaf14d238cabc24957e303ba9e600',
    downloadUrl: null, // No GitHub Release yet
    status: 'pending-release',
    signatureStatus: 'unsigned',
    releaseNotes: 'Initial desktop client release. Connects to a separately hosted AgentGate backend.',
  },
  {
    platform: 'linux-rpm',
    label: 'Linux RPM package',
    description: 'Fedora / RHEL / openSUSE package — installs via rpm or dnf',
    installerType: 'RPM',
    os: 'Fedora 36+ / RHEL 8+ / openSUSE Leap 15+',
    arch: 'x86_64',
    version: CURRENT_VERSION,
    builtAt: '2026-10-31',
    fileSize: 3_563_520,     // measured: 3.4 MB
    sha256: '7ac82e33302b64be1b57c8271436fc89fa383eecc89fae8ac0aff0cb9773aaba',
    downloadUrl: null,
    status: 'pending-release',
    signatureStatus: 'unsigned',
    releaseNotes: 'Initial desktop client release. Connects to a separately hosted AgentGate backend.',
  },
  {
    platform: 'linux-appimage',
    label: 'Linux AppImage',
    description: 'Portable executable — no installation required, runs on any modern Linux',
    installerType: 'AppImage',
    os: 'Any Linux x86_64 (glibc 2.17+)',
    arch: 'amd64 (x86_64)',
    version: CURRENT_VERSION,
    builtAt: '2026-10-31',
    fileSize: 86_900_736,    // measured: 83 MB
    sha256: '3c316d8c1fb767dfb1eb94490fa091fe4d71d4f2305c70264fbc7e159dabe293',
    downloadUrl: null,
    status: 'pending-release',
    signatureStatus: 'unsigned',
    releaseNotes: 'Initial desktop client release. Connects to a separately hosted AgentGate backend.',
  },
  // ── macOS ──────────────────────────────────────────────────────────────────
  {
    platform: 'macos',
    label: 'macOS Installer',
    description: 'Universal binary for macOS (Intel and Apple Silicon)',
    installerType: 'DMG',
    os: 'macOS 10.15 Catalina or later',
    arch: 'x86_64 + Apple Silicon',
    version: CURRENT_VERSION,
    builtAt: null,
    fileSize: null,
    sha256: null,
    downloadUrl: null,
    status: 'coming-soon',
    signatureStatus: 'unsigned',
    releaseNotes: null,
  },
]

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
