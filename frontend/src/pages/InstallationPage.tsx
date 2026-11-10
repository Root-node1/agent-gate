import {
  AlertCircle,
  ArrowRight,
  Download,
  Info,
  RefreshCw,
  Terminal,
  Trash2,
} from 'lucide-react'
import { Link } from 'react-router'
import LandingHeader from './landing/LandingHeader'
import LandingFooter from './landing/LandingFooter'
import './LandingPage.css'
import './InstallationPage.css'

interface StepProps {
  number: number
  title: string
  children: React.ReactNode
}

function Step({ number, title, children }: StepProps) {
  return (
    <div className="inst-step" id={`step-${number}`}>
      <div className="inst-step-num" aria-hidden="true">{number}</div>
      <div className="inst-step-body">
        <h3 className="inst-step-title">{title}</h3>
        {children}
      </div>
    </div>
  )
}

interface ErrorCaseProps {
  error: string
  fix: string
}

function ErrorCase({ error, fix }: ErrorCaseProps) {
  return (
    <div className="inst-error-case">
      <div className="inst-error-label">
        <AlertCircle size={14} aria-hidden="true" />
        {error}
      </div>
      <div className="inst-error-fix">{fix}</div>
    </div>
  )
}

export default function InstallationPage() {
  return (
    <div className="lp">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <LandingHeader />
      <main id="main">
        <section className="lp-section lp-hero lp-hero-sm" aria-labelledby="inst-title">
          <div className="lp-container">
            <p className="lp-kicker">Installation</p>
            <h1 id="inst-title" className="lp-h1">
              Installing AgentGate Desktop
            </h1>
            <p className="lp-lede">
              The desktop client connects to a separately hosted AgentGate backend. It does not
              install a database, Python, Redis, or any server component. You need a reachable
              AgentGate backend before the desktop client can be used.
            </p>
            <nav className="inst-toc" aria-label="On this page">
              <p className="inst-toc-title">On this page</p>
              <ol className="inst-toc-list">
                <li><a href="#step-1">Check system requirements</a></li>
                <li><a href="#step-2">Download the installer</a></li>
                <li><a href="#step-3">Verify the checksum</a></li>
                <li><a href="#step-4">Install</a></li>
                <li><a href="#step-5">Launch AgentGate</a></li>
                <li><a href="#step-6">Configure the backend URL</a></li>
                <li><a href="#step-7">Sign in</a></li>
                <li><a href="#step-8">Complete MFA</a></li>
                <li><a href="#step-9">Verify the connection</a></li>
                <li><a href="#troubleshooting">Troubleshooting</a></li>
                <li><a href="#updates">Updating</a></li>
                <li><a href="#uninstall">Uninstalling</a></li>
              </ol>
            </nav>
          </div>
        </section>

        <section className="lp-section lp-section-alt" aria-labelledby="inst-prereq-title">
          <div className="lp-container">
            <div className="inst-notice">
              <Info size={18} aria-hidden="true" />
              <div>
                <strong>Backend required separately.</strong>{' '}
                The desktop client wraps the AgentGate web interface. To use it, you must have
                an AgentGate backend deployed and reachable. See the{' '}
                <a href="https://github.com/Root-node1/agent-gate">deployment guide</a> for
                backend setup. If you are exploring the demo, the backend at{' '}
                <code>http://localhost:8000</code> works when started with <code>./run.sh</code>.
              </div>
            </div>
          </div>
        </section>

        <section className="lp-section" aria-labelledby="inst-steps-title">
          <div className="lp-container inst-steps-container">
            <h2 id="inst-steps-title" className="lp-h2">Installation steps</h2>

            <Step number={1} title="Check system requirements">
              <p>Confirm your system meets the requirements before downloading.</p>
              <ul className="inst-list">
                <li>
                  <strong>Linux (verified):</strong> Ubuntu 20.04+ / Debian 11+ (DEB), Fedora 36+ / RHEL 8+ (RPM),
                  or any modern Linux with glibc 2.17+ (AppImage). 64-bit x86_64 required.
                </li>
                <li>
                  <strong>Windows:</strong> Windows 10 (1903) or later, 64-bit.
                  WebView2 runtime required (bundled with Windows 11; the MSI/NSIS installer can
                  bootstrap it on Windows 10). Public download links activate only after a verified
                  release artifact URL is published.
                </li>
                <li>
                  <strong>macOS (not yet available):</strong> macOS 10.15 Catalina or later.
                  WKWebView ships with macOS — no extra runtime needed.
                </li>
              </ul>
              <Link to="/system-requirements" className="inst-link">
                Full system requirements
                <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </Step>

            <Step number={2} title="Download the installer">
              <p>
                Go to the <Link to="/downloads">Downloads page</Link> and select the package for
                your platform.
              </p>
              <div className="inst-platform-choices">
                <div className="inst-platform-choice">
                  <strong>Linux (DEB)</strong>
                  <code>AgentGate_0.1.0_amd64.deb</code>
                  <span className="inst-tag inst-tag-ready">Artifact available</span>
                </div>
                <div className="inst-platform-choice">
                  <strong>Linux (RPM)</strong>
                  <code>AgentGate-0.1.0-1.x86_64.rpm</code>
                  <span className="inst-tag inst-tag-ready">Artifact available</span>
                </div>
                <div className="inst-platform-choice">
                  <strong>Linux (AppImage)</strong>
                  <code>AgentGate_0.1.0_amd64.AppImage</code>
                  <span className="inst-tag inst-tag-ready">Artifact available</span>
                </div>
                <div className="inst-platform-choice inst-platform-choice-disabled">
                  <strong>Windows MSI / EXE</strong>
                  <span>CI builds MSI + NSIS; public URL not published yet</span>
                  <span className="inst-tag">Coming soon</span>
                </div>
                <div className="inst-platform-choice inst-platform-choice-disabled">
                  <strong>macOS</strong>
                  <span>Build not yet available</span>
                  <span className="inst-tag">Coming soon</span>
                </div>
              </div>
              <div className="inst-notice inst-notice-sm">
                <AlertCircle size={15} aria-hidden="true" />
                <span>
                  Download links are enabled only when a GitHub Release is published. Until then,
                  the artifacts are available in the <code>desktop-tauri</code> branch build output.
                </span>
              </div>
            </Step>

            <Step number={3} title="Verify the checksum">
              <p>
                Always verify the SHA-256 checksum before installing. The correct checksums are
                shown on the <Link to="/downloads">Downloads page</Link>.
              </p>
              <div className="inst-code-block">
                <p className="inst-code-label">Linux / macOS</p>
                <pre><code>sha256sum AgentGate_0.1.0_amd64.deb
# Compare to: be8b308e02828f14c3b04953b7407874d2eeaf14d238cabc24957e303ba9e600

sha256sum AgentGate_0.1.0_amd64.AppImage
# Compare to: 3c316d8c1fb767dfb1eb94490fa091fe4d71d4f2305c70264fbc7e159dabe293

sha256sum AgentGate-0.1.0-1.x86_64.rpm
# Compare to: 7ac82e33302b64be1b57c8271436fc89fa383eecc89fae8ac0aff0cb9773aaba</code></pre>
              </div>
              <div className="inst-notice inst-notice-sm inst-notice-warn">
                <AlertCircle size={15} aria-hidden="true" />
                <span>
                  Do not install if the checksum does not match. Contact the maintainer.
                </span>
              </div>
            </Step>

            <Step number={4} title="Install the application">
              <div className="inst-platform-tabs">
                <div className="inst-platform-section">
                  <h4 className="inst-platform-heading">Linux — DEB (Ubuntu / Debian)</h4>
                  <div className="inst-code-block">
                    <pre><code>sudo dpkg -i AgentGate_0.1.0_amd64.deb
# or
sudo apt install ./AgentGate_0.1.0_amd64.deb</code></pre>
                  </div>
                </div>
                <div className="inst-platform-section">
                  <h4 className="inst-platform-heading">Linux — RPM (Fedora / RHEL)</h4>
                  <div className="inst-code-block">
                    <pre><code>sudo rpm -i AgentGate-0.1.0-1.x86_64.rpm
# or
sudo dnf install ./AgentGate-0.1.0-1.x86_64.rpm</code></pre>
                  </div>
                </div>
                <div className="inst-platform-section">
                  <h4 className="inst-platform-heading">Linux — AppImage (any distro)</h4>
                  <div className="inst-code-block">
                    <pre><code>chmod +x AgentGate_0.1.0_amd64.AppImage
./AgentGate_0.1.0_amd64.AppImage</code></pre>
                  </div>
                  <p className="inst-note">
                    The AppImage is portable — no installation required. Move it anywhere and run it directly.
                    Optional: use <a href="https://appimagekit.github.io/appimaged/" target="_blank" rel="noreferrer">appimaged</a> to integrate it into the app menu.
                  </p>
                </div>
                <div className="inst-platform-section">
                  <h4 className="inst-platform-heading">Windows — MSI or NSIS EXE</h4>
                  <p className="inst-note">
                    After a verified public artifact is published, run the downloaded MSI or
                    NSIS <code>-setup.exe</code> and follow the wizard. The currentUser NSIS
                    installer does not require administrator rights. If Windows Defender SmartScreen
                    blocks the installer (unsigned binary), click &quot;More info&quot; then
                    &quot;Run anyway&quot; — or wait for a signed release. Do not treat unsigned
                    CI artifacts as production releases.
                  </p>
                </div>
                <div className="inst-platform-section inst-platform-section-disabled">
                  <h4 className="inst-platform-heading">macOS — not yet available</h4>
                  <p className="inst-note">
                    When a macOS installer is released, open the DMG and drag AgentGate to
                    Applications. Because the binary may not be notarized in the initial release,
                    you may need to right-click → Open on first launch.
                  </p>
                </div>
              </div>
            </Step>

            <Step number={5} title="Launch AgentGate">
              <p>
                Find <strong>AgentGate</strong> in your application launcher (Linux), Start menu
                (Windows), or Applications folder (macOS), or run it from the terminal. The
                DEB/RPM and Windows installers add a launcher entry automatically.
              </p>
              <div className="inst-code-block">
                <pre><code># Linux — if installed via DEB or RPM
agentgate

# Linux — AppImage
./AgentGate_0.1.0_amd64.AppImage

# Windows — Start menu → AgentGate
# or run AgentGate.exe from the install directory</code></pre>
              </div>
            </Step>

            <Step number={6} title="Configure the backend URL">
              <p>
                On first launch, AgentGate connects to <code>http://127.0.0.1:8000</code> (the
                local development default). To point it at a hosted backend, open{' '}
                <strong>Settings → Connection</strong> and enter the backend URL, then use
                <strong> Test connection</strong>.
              </p>
              <p>
                For a production deployment, the URL is <code>https://your-domain.com</code>.
                For a local development setup, it is <code>http://127.0.0.1:8000</code>.
                You can also set <code>AGENTGATE_BACKEND_URL</code> in the process environment;
                that override locks the Settings field until the variable is removed.
              </p>
              <div className="inst-notice inst-notice-sm">
                <Info size={15} aria-hidden="true" />
                <span>
                  The backend URL is stored in local desktop configuration
                  (<code>%APPDATA%\AgentGate</code> on Windows, <code>~/.config/agentgate</code> on
                  Linux). It is not a credential.
                </span>
              </div>
            </Step>

            <Step number={7} title="Sign in">
              <p>
                Use your AgentGate account email and password on the sign-in screen. If you do not
                have an account, register at the backend URL's <code>/register</code> path, or ask
                your administrator to create one.
              </p>
              <p>
                For a local demo setup, register a new account via the sign-in screen. Email
                verification codes appear in the backend terminal (console email backend in
                development).
              </p>
            </Step>

            <Step number={8} title="Complete MFA (if enabled)">
              <p>
                If your account has TOTP MFA enabled, you will be prompted for a 6-digit code from
                your authenticator app after entering your password.
              </p>
              <p>
                If you do not have access to your authenticator, use a recovery code. Recovery codes
                are available in <strong>Settings → Security</strong> before MFA is enabled, or
                from your administrator.
              </p>
            </Step>

            <Step number={9} title="Verify the connection">
              <p>
                After signing in, the dashboard overview should load. If the backend is running and
                has data, you will see the agent list, approval queue, and audit log. If this is a
                fresh backend, the lists will be empty — this is expected.
              </p>
              <p>
                To verify the backend connection from the terminal:
              </p>
              <div className="inst-code-block">
                <pre><code>curl http://localhost:8000/healthz
# Expected: {`{"status":"ok"}`}

curl http://localhost:8000/readyz
# Expected: {`{"status":"ok"}`}</code></pre>
              </div>
            </Step>
          </div>
        </section>

        <section className="lp-section lp-section-alt" aria-labelledby="troubleshooting">
          <div className="lp-container">
            <div className="sr-section-head">
              <Terminal size={22} aria-hidden="true" className="sr-section-icon" />
              <h2 id="troubleshooting" className="lp-h2">Troubleshooting</h2>
            </div>
            <div className="inst-errors">
              <ErrorCase
                error="Backend unreachable / 'Cannot reach the backend'"
                fix="Confirm the backend is running. Check that the URL in Settings exactly matches the backend host and port. For HTTPS, confirm the TLS certificate is valid."
              />
              <ErrorCase
                error="HTTPS certificate error / TLS handshake failed"
                fix="The backend certificate must be trusted by your OS. For self-signed certs, add the CA to your system trust store. Never disable certificate verification."
              />
              <ErrorCase
                error="Wrong credentials / 401 on sign-in"
                fix="Verify the email and password. If you forgot the password, use the 'Forgot password' link to request a reset email. For a local dev backend, the reset email appears in the terminal."
              />
              <ErrorCase
                error="MFA code rejected"
                fix="Ensure your device clock is synchronized (TOTP is time-based). Use a recovery code if you no longer have access to the authenticator app."
              />
              <ErrorCase
                error="Session expired / redirected to sign-in"
                fix="Sessions expire after a period of inactivity. Sign in again. If the problem recurs immediately, check that cookies are enabled in the application."
              />
              <ErrorCase
                error="WebKitGTK not found (Linux DEB/RPM)"
                fix="Install WebKitGTK: `sudo apt install libwebkit2gtk-4.0-37` (Ubuntu/Debian) or `sudo dnf install webkit2gtk4.0` (Fedora). The AppImage bundles its own WebKit and does not require this."
              />
              <ErrorCase
                error="AppImage: fuse not available"
                fix="Run with `--appimage-extract-and-run` flag, or install FUSE: `sudo apt install libfuse2`."
              />
              <ErrorCase
                error="Blank white screen on launch"
                fix="The desktop client serves its own packaged frontend over a local loopback server and proxies API calls to the configured backend. Confirm Settings → Connection points at a reachable backend, then retry. If the window stays blank, restart the app and check that no other process is interfering with loopback networking."
              />
              <ErrorCase
                error="Windows SmartScreen / unknown publisher"
                fix="v0.1.0 installers are unsigned. Use More info → Run anyway only for artifacts whose SHA-256 matches the official checksum, or wait for a signed release."
              />
            </div>
          </div>
        </section>

        <section className="lp-section" aria-labelledby="updates">
          <div className="lp-container">
            <div className="sr-section-head">
              <RefreshCw size={22} aria-hidden="true" className="sr-section-icon" />
              <h2 id="updates" className="lp-h2">Updating</h2>
            </div>
            <p>
              AgentGate v0.1.0 does not include an automatic update mechanism. To update:
            </p>
            <ol className="inst-ordered-list">
              <li>Download the new version from the <Link to="/downloads">Downloads page</Link>.</li>
              <li>Verify its SHA-256 checksum.</li>
              <li>Install it using the same method as the initial installation. On Linux DEB/RPM, the package manager will upgrade in place.</li>
              <li>Restart the application.</li>
            </ol>
            <div className="inst-notice inst-notice-sm">
              <Info size={15} aria-hidden="true" />
              <span>
                Automatic update support via Tauri's updater plugin is on the roadmap for a future release.
              </span>
            </div>
          </div>
        </section>

        <section className="lp-section lp-section-alt" aria-labelledby="uninstall">
          <div className="lp-container">
            <div className="sr-section-head">
              <Trash2 size={22} aria-hidden="true" className="sr-section-icon" />
              <h2 id="uninstall" className="lp-h2">Uninstalling</h2>
            </div>
            <div className="inst-platform-tabs">
              <div className="inst-platform-section">
                <h4 className="inst-platform-heading">Linux — DEB</h4>
                <div className="inst-code-block">
                  <pre><code>sudo apt remove agentgate
# or
sudo dpkg -r agentgate</code></pre>
                </div>
              </div>
              <div className="inst-platform-section">
                <h4 className="inst-platform-heading">Linux — RPM</h4>
                <div className="inst-code-block">
                  <pre><code>sudo dnf remove AgentGate
# or
sudo rpm -e AgentGate</code></pre>
                </div>
              </div>
              <div className="inst-platform-section">
                <h4 className="inst-platform-heading">Linux — AppImage</h4>
                <div className="inst-code-block">
                  <pre><code>rm AgentGate_0.1.0_amd64.AppImage</code></pre>
                </div>
              </div>
              <div className="inst-platform-section">
                <h4 className="inst-platform-heading">Windows</h4>
                <div className="inst-code-block">
                  <pre><code># Settings → Apps → Installed apps → AgentGate → Uninstall
# or use the uninstaller from the Start menu entry</code></pre>
                </div>
                <p className="inst-note">
                  Uninstall removes the application binaries. It does <strong>not</strong> silently
                  delete local desktop configuration under <code>%APPDATA%\AgentGate</code>
                  (including the saved backend URL). Remove that folder manually if you want a
                  clean slate. Reinstalling keeps the previous connection setting.
                </p>
              </div>
            </div>
            <p className="inst-note">
              Uninstalling the desktop client does not affect the backend, database, or any stored
              server-side data. The backend runs independently and must be managed separately.
            </p>
          </div>
        </section>

        <div className="lp-cta">
          <div className="lp-container lp-cta-inner">
            <div>
              <h2 className="lp-h2">Ready to download?</h2>
              <p>Get the installer for your platform.</p>
            </div>
            <div className="lp-cta-actions">
              <Link to="/downloads" className="btn lp-btn-lg lp-btn-invert">
                <Download size={18} aria-hidden="true" />
                Downloads
              </Link>
              <Link to="/system-requirements" className="btn lp-btn-lg lp-btn-outline-invert">
                System requirements
              </Link>
            </div>
          </div>
        </div>
      </main>
      <LandingFooter />
    </div>
  )
}
