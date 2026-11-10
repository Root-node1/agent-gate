import {
  AlertCircle,
  CheckCircle2,
  HardDrive,
  Info,
  Laptop,
  Monitor,
  Network,
  Server,
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
      value: SYSTEM_REQUIREMENTS.macos.os,
      verified: false,
      note: 'Build not yet produced — pending macOS CI runner',
    },
    { label: 'Processor', value: SYSTEM_REQUIREMENTS.macos.cpu, verified: false },
    { label: 'Memory', value: SYSTEM_REQUIREMENTS.macos.ram, verified: false, note: 'Estimated' },
    { label: 'Storage', value: SYSTEM_REQUIREMENTS.macos.storage, verified: false, note: 'Estimated' },
    { label: 'WebView engine', value: SYSTEM_REQUIREMENTS.macos.webview, verified: true, note: 'WKWebView ships with macOS' },
    { label: 'Network', value: SYSTEM_REQUIREMENTS.macos.network, verified: false },
  ]

  const backendRows: RequirementRow[] = [
    { label: 'Backend type', value: 'Self-hosted or provider-hosted Django service', verified: true },
    { label: 'Web framework', value: 'Django 6 / Django REST Framework', verified: true },
    { label: 'Database', value: 'PostgreSQL 17 (required — PG-specific migrations exist)', verified: true },
    { label: 'Cache / queue broker', value: 'Redis 7', verified: true },
    { label: 'Background worker', value: 'Procrastinate worker (same Docker image, different CMD)', verified: true },
    { label: 'Python', value: 'Python 3.13 or later', verified: true },
    { label: 'Node.js (build only)', value: 'Node.js 22 (for `npm run build`)', verified: true },
    { label: 'Hosting', value: 'Docker + Docker Compose on any Linux host (e.g. Contabo VPS)', verified: true },
    { label: 'Reverse proxy', value: 'Caddy 2 (TLS termination + static file serving)', verified: true },
    { label: 'Public ports', value: '80 (HTTP) and 443 (HTTPS) — Caddy only', verified: true },
    { label: 'Internal services', value: 'PostgreSQL 5432 and Redis 6379 — internal network only, never public', verified: true },
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

        <section className="lp-section lp-section-alt" aria-labelledby="sr-sep-title">
          <div className="lp-container">
            <h2 id="sr-sep-title" className="lp-h2 visually-hidden">Components</h2>
            <div className="sr-sep-row">
              <div className="sr-component-card">
                <Laptop size={24} aria-hidden="true" className="sr-component-icon" />
                <div>
                  <h3 className="lp-h3">AgentGate Desktop Client</h3>
                  <p>
                    A Tauri desktop application (Rust + WebView). Runs on your computer and connects
                    to an AgentGate backend. Installing it does not set up a database, install Python,
                    or configure any server.
                  </p>
                </div>
              </div>
              <div className="sr-sep-divider" aria-hidden="true">+</div>
              <div className="sr-component-card">
                <Server size={24} aria-hidden="true" className="sr-component-icon" />
                <div>
                  <h3 className="lp-h3">AgentGate Backend</h3>
                  <p>
                    A Django service with PostgreSQL, Redis, and a background worker. Deployed via
                    Docker Compose on a Linux server. This is what AI agents connect to and what
                    enforces spending rules.
                  </p>
                </div>
              </div>
            </div>
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
              <div className="sr-availability-badge sr-coming-soon">
                Build not yet produced — coming soon
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

        <section className="lp-section lp-section-alt" aria-labelledby="sr-backend-title">
          <div className="lp-container">
            <div className="sr-section-head">
              <Server size={22} aria-hidden="true" className="sr-section-icon" />
              <h2 id="sr-backend-title" className="lp-h2">Backend Requirements</h2>
            </div>
            <p className="lp-section-lede">
              The backend is hosted separately and is not bundled with the desktop client.
              Requirements are verified from the actual repository configuration, Dockerfile,
              and CI pipeline.
            </p>
            <ReqTable rows={backendRows} />
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
                <li>Production: HTTPS with a valid TLS certificate (Caddy handles provisioning via Let's Encrypt).</li>
                <li>No direct database or Redis connections are made from the desktop client.</li>
                <li>PayPal Sandbox API: required only on the backend server, not the desktop.</li>
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
                    <td>Pending verification</td>
                    <td>Build not yet produced</td>
                  </tr>
                  <tr>
                    <td>macOS DMG</td>
                    <td>Pending verification</td>
                    <td>Build not yet produced</td>
                  </tr>
                  <tr>
                    <td>Backend (database)</td>
                    <td>20–50 MB initial</td>
                    <td>PostgreSQL — grows with audit trail and spend history</td>
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
