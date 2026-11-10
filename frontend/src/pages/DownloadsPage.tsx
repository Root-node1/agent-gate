import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Download,
  FileCode2,
  Info,
  Package,
  Shield,
  Terminal,
} from 'lucide-react'
import LandingHeader from './landing/LandingHeader'
import LandingFooter from './landing/LandingFooter'
import { CURRENT_VERSION, RELEASE_ASSETS, formatBytes, type ReleaseAsset } from './landing/releases'
import './LandingPage.css'
import './DownloadsPage.css'

const PLATFORM_HEADINGS: Record<string, { title: string; icon: string }> = {
  windows: { title: 'Windows', icon: '⊞' },
  linux: { title: 'Linux', icon: '🐧' },
  macos: { title: 'macOS', icon: '⌘' },
}

function platformGroup(assets: ReleaseAsset[]): Array<{ key: string; title: string; icon: string; items: ReleaseAsset[] }> {
  const groups: Record<string, ReleaseAsset[]> = {}
  for (const a of assets) {
    const g = a.platform.startsWith('linux') ? 'linux' : a.platform
    if (!groups[g]) groups[g] = []
    groups[g].push(a)
  }
  const orderedKeys = ['linux', 'windows', 'macos']
  return orderedKeys
    .filter((k) => groups[k])
    .map((k) => ({
      key: k,
      title: PLATFORM_HEADINGS[k].title,
      icon: PLATFORM_HEADINGS[k].icon,
      items: groups[k],
    }))
}

function StatusBadge({ status }: { status: ReleaseAsset['status'] }) {
  if (status === 'available') {
    return (
      <span className="dl-badge dl-badge-available">
        <CheckCircle2 size={13} aria-hidden="true" />
        Available
      </span>
    )
  }
  if (status === 'pending-release') {
    return (
      <span className="dl-badge dl-badge-pending">
        <Clock size={13} aria-hidden="true" />
        Pending release
      </span>
    )
  }
  return (
    <span className="dl-badge dl-badge-soon">
      <Clock size={13} aria-hidden="true" />
      Coming soon
    </span>
  )
}

function AssetCard({ asset }: { asset: ReleaseAsset }) {
  const canDownload = asset.status === 'available' && asset.downloadUrl !== null
  const hasSha = asset.sha256 !== null
  const hasSize = asset.fileSize !== null

  return (
    <div className="dl-asset">
      <div className="dl-asset-header">
        <div className="dl-asset-title-row">
          <Package size={16} aria-hidden="true" className="dl-asset-icon" />
          <span className="dl-asset-label">{asset.label}</span>
          <StatusBadge status={asset.status} />
        </div>
        <p className="dl-asset-desc">{asset.description}</p>
        <dl className="dl-asset-meta">
          <dt>OS</dt><dd>{asset.os}</dd>
          <dt>Architecture</dt><dd>{asset.arch}</dd>
          <dt>Format</dt><dd>{asset.installerType}</dd>
          {asset.builtAt && <><dt>Built</dt><dd>{asset.builtAt}</dd></>}
          {hasSize && <><dt>Size</dt><dd>{formatBytes(asset.fileSize!)}</dd></>}
          {asset.version && <><dt>Version</dt><dd>{asset.version}</dd></>}
          <dt>Signature</dt>
          <dd>
            {asset.signatureStatus === 'signed'
              ? 'Signed'
              : asset.signatureStatus === 'not-applicable'
                ? 'N/A'
                : 'Unsigned — not an officially verified production release'}
          </dd>
        </dl>
      </div>

      {hasSha && (
        <details className="dl-checksum">
          <summary>
            <Shield size={14} aria-hidden="true" />
            SHA-256 checksum
          </summary>
          <code className="dl-sha">{asset.sha256}</code>
          <p className="dl-sha-instructions">
            Verify on Linux/macOS: <code>sha256sum &lt;file&gt;</code> or <code>shasum -a 256 &lt;file&gt;</code>
          </p>
        </details>
      )}

      {asset.releaseNotes && (
        <p className="dl-release-notes">{asset.releaseNotes}</p>
      )}

      {canDownload ? (
        <a
          href={asset.downloadUrl!}
          className="btn btn-primary dl-btn"
          download
          aria-label={`Download ${asset.label} ${asset.version}`}
        >
          <Download size={16} aria-hidden="true" />
          Download {asset.installerType}
        </a>
      ) : asset.status === 'pending-release' ? (
        <div className="dl-unavailable dl-unavailable-pending">
          <Clock size={15} aria-hidden="true" />
          <span>
            Artifact built — awaiting GitHub Release. Check back soon.
          </span>
        </div>
      ) : (
        <div className="dl-unavailable">
          <Clock size={15} aria-hidden="true" />
          <span>
            Not yet available for this platform. Check back soon.
          </span>
        </div>
      )}
    </div>
  )
}

export default function DownloadsPage() {
  const groups = platformGroup(RELEASE_ASSETS)

  return (
    <div className="lp">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <LandingHeader />
      <main id="main">
        <section className="lp-section lp-hero lp-hero-sm" aria-labelledby="dl-title">
          <div className="lp-container">
            <p className="lp-kicker">Downloads</p>
            <h1 id="dl-title" className="lp-h1">
              AgentGate Desktop Client v{CURRENT_VERSION}
            </h1>
            <p className="lp-lede">
              The AgentGate desktop client connects to a separately hosted AgentGate backend.
              Installing this application does not install the backend, the database, or any worker.
            </p>
          </div>
        </section>

        <section className="lp-section" aria-labelledby="dl-notice-title">
          <div className="lp-container">
            <div className="dl-notice">
              <Info size={18} aria-hidden="true" />
              <div>
                <h2 id="dl-notice-title" className="dl-notice-title">Pre-release status</h2>
                <p>
                  Linux builds (DEB, RPM, AppImage) have been produced and their checksums verified.
                  A GitHub Release has not yet been published — download links will be enabled when
                  the release is tagged and published. Windows MSI/NSIS installers are built by the
                  Desktop Windows GitHub Actions workflow; macOS builds are not yet available.
                  Public Windows download buttons stay disabled until a verified public artifact URL exists.
                </p>
                <p>
                  Code-signing for Windows and macOS is not yet configured.
                  Do not distribute unsigned builds as production releases.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="lp-section lp-section-alt" aria-labelledby="dl-platforms-title">
          <div className="lp-container">
            <h2 id="dl-platforms-title" className="lp-h2 visually-hidden">Platform downloads</h2>
            {groups.map((group) => (
              <div key={group.key} className="dl-group" aria-labelledby={`dl-${group.key}-title`}>
                <h3 id={`dl-${group.key}-title`} className="dl-group-title">
                  <span aria-hidden="true">{group.icon}</span>
                  {group.title}
                </h3>
                <div className="dl-assets">
                  {group.items.map((asset) => (
                    <AssetCard key={`${asset.platform}-${asset.installerType}`} asset={asset} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="lp-section" aria-labelledby="dl-sep-title">
          <div className="lp-container dl-sep-section">
            <h2 id="dl-sep-title" className="lp-h2">Desktop client and backend are separate</h2>
            <div className="dl-sep-grid">
              <div className="dl-sep-card">
                <Terminal size={22} aria-hidden="true" className="dl-sep-icon" />
                <h3 className="lp-h3">AgentGate Desktop</h3>
                <p>
                  A Tauri-based desktop application that lets you manage agents, review approvals,
                  inspect the audit log, and run policy simulations. It connects to your
                  AgentGate backend over HTTP(S).
                </p>
                <ul className="dl-sep-list">
                  <li>Requires a reachable AgentGate backend URL</li>
                  <li>Wraps the same React SPA as the web interface</li>
                  <li>Built with Tauri v2 (Rust + WebView)</li>
                </ul>
              </div>
              <div className="dl-sep-card">
                <FileCode2 size={22} aria-hidden="true" className="dl-sep-icon" />
                <h3 className="lp-h3">AgentGate Backend</h3>
                <p>
                  A separately hosted service: Django 6, PostgreSQL 17, Redis 7, and a Procrastinate
                  background worker. It is deployed via Docker Compose on a Contabo VPS or any host
                  that supports Docker.
                </p>
                <ul className="dl-sep-list">
                  <li>Not included in the desktop installer</li>
                  <li>Requires PostgreSQL 17 and Redis 7</li>
                  <li>See the deployment guide for setup instructions</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="lp-section lp-section-alt" aria-labelledby="dl-verification-title">
          <div className="lp-container">
            <h2 id="dl-verification-title" className="lp-h2">Verifying downloads</h2>
            <p className="lp-section-lede">
              Always verify the SHA-256 checksum of a downloaded file against the value shown above.
            </p>
            <div className="dl-verify-grid">
              <div>
                <h3 className="lp-h4">Linux / macOS</h3>
                <pre className="dl-code">sha256sum AgentGate_0.1.0_amd64.deb
shasum -a 256 AgentGate_0.1.0_amd64.AppImage</pre>
              </div>
              <div>
                <h3 className="lp-h4">Windows</h3>
                <pre className="dl-code">Get-FileHash AgentGate_0.1.0_x64.msi -Algorithm SHA256</pre>
              </div>
            </div>
            <div className="dl-notice dl-notice-warn">
              <AlertCircle size={18} aria-hidden="true" />
              <div>
                <strong>Not code-signed.</strong> Windows and macOS installers for AgentGate v0.1.0
                are not code-signed with a commercial certificate. Your operating system may display a
                security warning. Only download from the official GitHub Releases page.
                Code-signing is on the roadmap for the first production release.
              </div>
            </div>
          </div>
        </section>
      </main>
      <LandingFooter />
    </div>
  )
}
