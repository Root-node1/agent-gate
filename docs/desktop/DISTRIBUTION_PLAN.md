# AgentGate Desktop — Distribution Plan

Status: proposal. No artifacts are published. No fake links.

## 1. Backend connectivity (recommended)

**Recommended: Hosted AgentGate backend over HTTPS.**

- The desktop application connects to a hosted AgentGate API (HTTPS) rather than a local Django instance.
- The embedded loopback server proxies `/api` and `/v1` to the configured backend URL (`AGENTGATE_BACKEND_URL` env var at build time; default `http://127.0.0.1:8000` for development).
- Django remains the sole authorization authority; organization scoping, MFA, CSRF/session security, idempotency, and financial safeguards remain backend-enforced.
- Webhook processing stays backend-only.

Alternatives considered:
- (B) Locally installed backend service: high maintenance, version skew, support burden. Rejected for initial release.
- (C) Backend bundled with desktop: large bundle, update complexity, local data security concerns. Rejected for initial release.

### Authentication implications

- Development: session cookies over HTTP localhost (current, validated).
- Production (hosted HTTPS backend): requires TLS in the embedded proxy (HTTPS now supported via rustls; HTTP retained for loopback dev). CSRF_TRUSTED_ORIGINS must include the desktop origin. `SameSite=Lax` cookies work cross-origin only if same-site; with a remote HTTPS backend, the desktop origin (`tauri://localhost`) is cross-site, so the same-origin loopback proxy approach must be retained (frontend and proxy share `127.0.0.1:<port>`), and the proxy forwards to the HTTPS backend with TLS.
- No JWT/OAuth/native credential storage introduced.

### Environment configuration

| Environment | Backend URL | CSP connect-src |
|---|---|---|
| Development | `http://127.0.0.1:8000` | `http://127.0.0.1:8000 http://localhost:8000` |
| Staging | `https://staging-api.agentgate.example` | staging origin |
| Production | `https://api.agentgate.example` | production origin |

CSP `connect-src` in `tauri.conf.json` must be updated per environment before build. Do not use wildcards.

## 2. Initial release targets

### Windows
- Architecture: x86_64.
- Installer: MSI (recommended) or EXE (NSIS). MSI preferred for enterprise/managed deployment.
- WebView2: Evergreen runtime; installer bootstraps if missing.
- Installation: per-user or per-machine; upgrade via MSI major upgrade.
- Uninstall: removes app + (optionally) user data; leaves no orphaned listeners (sidecar lifecycle).
- Code signing: required (Authenticode). Not yet obtained.
- Origin/loopback: WebView2 origin `https://tauri.localhost`; loopback proxy must serve frontend over HTTP on `127.0.0.1` (cross-origin vs WebView2 origin). **Limitation:** needs validation on Windows.

### Linux
- AppImage (x86_64): portable, no install required.
- Debian/Ubuntu `.deb`: apt-based install/upgrade.
- Fedora/RHEL `.rpm`: dnf/yum-based install/upgrade.
- Runtime deps: WebKitGTK 4.1, GTK 3, glibc, libssl, librsvg2, libxdo, libayatana-appindicator3.
- Desktop integration: `.desktop` file + icons (already bundled).
- Uninstall: package manager removes files; user data in `~/.config/agentgate` (optional cleanup).

macOS: future target only. Not supported in initial release.

## 3. System requirements

See `docs/desktop/SYSTEM_REQUIREMENTS.md`.

## 4. Download page structure (proposed)

- Page title: "Download AgentGate Desktop"
- Sections:
  1. Windows: download link (MSI), version, architecture (x86_64), file size, SHA-256, install instructions, WebView2 note.
  2. Linux — AppImage: download link, version, architecture, file size, SHA-256, instructions (chmod +x, run).
  3. Linux — Debian/Ubuntu (.deb): download link, version, architecture, file size, SHA-256, instructions (dpkg -i / apt).
  4. Linux — Fedora/RHEL (.rpm): download link, version, architecture, file size, SHA-256, instructions (dnf install).
  5. Minimum system requirements (from SYSTEM_REQUIREMENTS.md).
  6. Release notes link.
  7. Known limitations.
- Artifacts attached to GitHub Releases (tagged version), with checksums in release notes.
- No fake links or unpublished artifacts.

## 5. Release artifacts (current build outputs)

- `AgentGate_0.1.0_amd64.deb`
- `AgentGate-0.1.0-1.x86_64.rpm`
- `AgentGate_0.1.0_amd64.AppImage`

Version: 0.1.0. Architecture: x86_64. No code signing yet.

## 6. Linux request-body timeout (TAURI-10 Phase 5)

- The embedded proxy reads the request body in a loop with a 10 MiB size limit but no explicit per-read timeout (the underlying TCP stream has no read timeout on the client side; upstream has 30s).
- Risk: a malicious local process could send a slow body and hold the server thread (single-threaded server → DoS).
- Assessment: a bounded timeout is safe for normal API requests (small JSON). However, implementing a thread-based timeout on `tiny_http`'s reader is complex and risks breaking legitimate uploads.
- Decision: **not implemented** in this milestone. Documented as a known limitation. Proposed secure alternative: migrate the embedded server to an async runtime (tokio + axum/hyper) with per-connection timeouts, or handle each request in a separate thread with a watchdog timer.
- Size limit (10 MiB) remains in place.

## 7. GUI verification evidence

- Released binary launched under WSLg; server bound ephemeral port.
- Weston compositor log: window registered (appId `app`, windowId `0x4e`).
- Full 7-step auth flow against loopback origin: all pass.
- Visual pixel confirmation not captured (no screenshot tool in agent environment). Marked partially verified.

## 8. Remaining blockers for public download

- Code signing (Windows Authenticode, Linux GPG for packages).
- Windows runtime verification (WebView2 origin + loopback proxy).
- macOS support (future).
- ARM64 builds.
- Backend TLS support in embedded proxy: IMPLEMENTED (AG-04, ureq + rustls). Remaining: Windows runtime verification of HTTPS + cookies.
- Interactive GUI verification.
- CSRF_TRUSTED_ORIGINS configuration for desktop origin in production backend.
- Release notes and changelog.
- Security review sign-off.

## 9. Distinction

- **Linux integration readiness:** GO (automated checks pass, auth flow passes, lifecycle clean).
- **Public download readiness:** NO-GO (unsigned, unverified on clean OS images, no code signing, GUI partially verified).
- **Cross-platform production readiness:** NO-GO (Windows/macOS unverified).
