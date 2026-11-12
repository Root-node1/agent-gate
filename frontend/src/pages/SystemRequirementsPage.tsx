import {
  AlertCircle,
  CheckCircle2,
  HardDrive,
  Info,
  Monitor,
  Network,
} from 'lucide-react'
import { Link } from 'react-router'
import LandingHeader from './landing/LandingHeader'
import LandingFooter from './landing/LandingFooter'
import { SYSTEM_REQUIREMENTS } from './landing/releases'
import './LandingPage.css'
import './SystemRequirementsPage.css'

interface RequirementRow {
  label: string
  value: string
  verified: boolean
  note?: string
}

function ReqTable({ rows }: { rows: RequirementRow[] }) {
  return (
    <table className="sr-table">
      <thead>
        <tr>
          <th scope="col">Requirement</th>
          <th scope="col">Specification</th>
          <th scope="col" className="sr-status-col">Verified</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <td className="sr-label">{row.label}</td>
            <td>
              {row.value}
              {row.note && <span className="sr-note">{row.note}</span>}
            </td>
            <td className="sr-status-col">
              {row.verified ? (
                <CheckCircle2 size={16} aria-label="Verified" className="sr-verified" />
              ) : (
                <AlertCircle size={16} aria-label="Pending verification" className="sr-pending" />
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function SystemRequirementsPage() {
  const linuxRows: RequirementRow[] = [
    {
      label: 'Operating system',
      value: SYSTEM_REQUIREMENTS.linux.os,
      verified: true,
      note: 'DEB, RPM, AppImage artifacts built and verified on this platform',
    },
    { label: 'Processor', value: SYSTEM_REQUIREMENTS.linux.cpu, verified: true },
    { label: 'Memory', value: SYSTEM_REQUIREMENTS.linux.ram, verified: false, note: 'Estimated from Tauri runtime profile' },
    { label: 'Storage', value: SYSTEM_REQUIREMENTS.linux.storage, verified: true, note: 'DEB/RPM ≈ 3.4 MB; AppImage ≈ 83 MB' },
    { label: 'WebView engine', value: SYSTEM_REQUIREMENTS.linux.webview, verified: true },
    { label: 'Network', value: SYSTEM_REQUIREMENTS.linux.network, verified: true },
  ]

  const windowsRows: RequirementRow[] = [
    {
      label: 'Operating system',
      value: SYSTEM_REQUIREMENTS.windows.os,
      verified: false,
      note: 'Build not yet produced — pending Windows CI runner',
    },
    { label: 'Processor', value: SYSTEM_REQUIREMENTS.windows.cpu, verified: false },
    { label: 'Memory', value: SYSTEM_REQUIREMENTS.windows.ram, verified: false, note: 'Estimated' },
    { label: 'Storage', value: SYSTEM_REQUIREMENTS.windows.storage, verified: false, note: 'Estimated' },
    { label: 'WebView engine', value: SYSTEM_REQUIREMENTS.windows.webview, verified: false, note: 'WebView2 ships with Windows 11; downloadable for Windows 10' },
    { label: 'Network', value: SYSTEM_REQUIREMENTS.windows.network, verified: false },
  ]

  const macosRows: RequirementRow[] = [
    {
      label: 'Operating system',
      value: 'macOS 10.15 Catalina or later',
      verified: false,
      note: 'Build not yet produced — pending macOS CI runner',
    },
    { label: 'Processor', value: '64-bit (x86_64 or Apple Silicon)', verified: false },
    { label: 'Memory', value: '4 GB minimum', verified: false, note: 'Estimated' },
    { label: 'Storage', value: '200 MB available', verified: false, note: 'Estimated' },
    { label: 'WebView engine', value: 'Built-in WKWebView (no additional runtime needed)', verified: true, note: 'WKWebView ships with macOS' },
    { label: 'Network', value: 'Internet access to reach the AgentGate backend', verified: false },
  ]

  return (
    <div className="lp">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <LandingHeader />
      <main id="main">
        <section className="lp-section lp-hero lp-hero-sm" aria-labelledby="sr-title">
          <div className="lp-container">
            <p className="lp-kicker">System requirements</p>
            <h1 id="sr-title" className="lp-h1">
              What you need to run AgentGate
            </h1>
            <p className="lp-lede">
              AgentGate has two separate components: the desktop client and the backend service.
              They have different requirements and are installed independently.
            </p>
          </div>
        </section>

        <section className="lp-section" aria-labelledby="sr-desktop-title">
          <div className="lp-container">
            <div className="sr-section-head">
              <Monitor size={22} aria-hidden="true" className="sr-section-icon" />
              <h2 id="sr-desktop-title" className="lp-h2">Desktop Client Requirements</h2>
            </div>

            <div className="sr-verification-key">
              <CheckCircle2 size={14} aria-hidden="true" className="sr-verified" />
              <span>Requirement verified from actual build artifacts and runtime</span>
              <AlertCircle size={14} aria-hidden="true" className="sr-pending" />
              <span>Pending verification — estimated from Tauri documentation</span>
            </div>

            <div className="sr-platform-block" id="sr-linux">
              <h3 className="sr-platform-title">🐧 Linux</h3>
              <div className="sr-availability-badge sr-available">
                Artifacts built and verified (Oct 31 2026)
              </div>
              <ReqTable rows={linuxRows} />
            </div>

            <div className="sr-platform-block" id="sr-windows">
              <h3 className="sr-platform-title">⊞ Windows</h3>
              <div className="sr-availability-badge sr-available">
                Artifacts built and verified (Nov 10 2026) — awaiting GitHub Release
              </div>
              <ReqTable rows={windowsRows} />
            </div>

            <div className="sr-platform-block" id="sr-macos">
              <h3 className="sr-platform-title">⌘ macOS</h3>
              <div className="sr-availability-badge sr-coming-soon">
                Build not yet produced — coming soon
              </div>
              <ReqTable rows={macosRows} />
            </div>

            <div className="sr-notice">
              <Info size={16} aria-hidden="true" />
              <p>
                Windows and macOS builds have not yet been produced. Requirements for those platforms
                are based on Tauri v2 documentation and standard deployment assumptions, not from a
                tested artifact.
              </p>
            </div>
          </div>
        </section>

        <section className="lp-section" aria-labelledby="sr-network-title">
          <div className="lp-container sr-network-section">
            <Network size={22} aria-hidden="true" className="sr-section-icon" />
            <div>
              <h2 id="sr-network-title" className="lp-h2">Network Requirements</h2>
              <ul className="sr-network-list">
                <li>The desktop client must be able to reach the backend over HTTP or HTTPS.</li>
                <li>Default backend URL: configurable. Development default: <code>http://localhost:8000</code>.</li>
                <li>No direct database connections are made from the desktop client.</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="lp-section lp-section-alt" aria-labelledby="sr-storage-title">
          <div className="lp-container sr-network-section">
            <HardDrive size={22} aria-hidden="true" className="sr-section-icon" />
            <div>
              <h2 id="sr-storage-title" className="lp-h2">Storage Requirements</h2>
              <table className="sr-table">
                <thead>
                  <tr>
                    <th scope="col">Component</th>
                    <th scope="col">Size</th>
                    <th scope="col">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Linux DEB installer</td>
                    <td>3.4 MB</td>
                    <td>Verified from artifact</td>
                  </tr>
                  <tr>
                    <td>Linux RPM installer</td>
                    <td>3.4 MB</td>
                    <td>Verified from artifact</td>
                  </tr>
                  <tr>
                    <td>Linux AppImage</td>
                    <td>83 MB</td>
                    <td>Portable — no installation required; bundles WebKit libraries</td>
                  </tr>
                  <tr>
                    <td>Windows MSI/EXE</td>
                    <td>MSI: 4.3 MB / EXE: 3.0 MB</td>
                    <td>Verified from artifact (Nov 2026)</td>
                  </tr>
                  <tr>
                    <td>macOS DMG</td>
                    <td>Pending verification</td>
                    <td>Build not yet produced</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <div className="lp-cta">
          <div className="lp-container lp-cta-inner">
            <div>
              <h2 className="lp-h2">Ready to install?</h2>
              <p>Get the desktop client and follow the installation guide.</p>
            </div>
            <div className="lp-cta-actions">
              <Link to="/downloads" className="btn lp-btn-lg lp-btn-invert">
                Downloads
              </Link>
              <Link to="/install" className="btn lp-btn-lg lp-btn-outline-invert">
                Installation guide
              </Link>
            </div>
          </div>
        </div>
      </main>
      <LandingFooter />
    </div>
  )
}
