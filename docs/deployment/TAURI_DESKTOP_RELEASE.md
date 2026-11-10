# AgentGate Desktop — Tauri Release

**Branch:** `integration/agentgate-dashboard`
**Tauri version:** 2.12.5
**Frontend:** React 19 + Vite
**App version:** 0.1.0
**Architecture:** x86_64
**Status:** Internal testing build (unsigned); not ready for public distribution

---

## 1. Backend Connectivity

The desktop application connects to a hosted AgentGate backend over HTTPS via an embedded loopback proxy (`tiny_http` + `ureq` with rustls TLS).

| Environment | Backend URL | CSP connect-src |
|---|---|---|
| Development | `http://127.0.0.1:8000` | `http://127.0.0.1:8000 http://localhost:8000` |
| Staging | `https://staging-api.agentgate.example` | Staging origin |
| Production | `https://api.agentgate.example` | Production origin |

**Configuration:** The `AGENTGATE_BACKEND_URL` environment variable is validated at build time by `server.rs`. Policy:
- `https` is allowed for any non-unsafe host (hosted backend).
- `http` is allowed only for loopback hosts.
- No embedded credentials, fragments, or query strings.
- Path must be empty or `/`.

**CSP:** `tauri.conf.json` `connect-src` must be updated per environment before build. No wildcards.

**Authentication:** Session cookies over the loopback proxy. The desktop origin (`tauri://localhost`) is cross-site relative to a remote HTTPS backend, so the same-origin loopback proxy approach is retained — frontend and proxy share `127.0.0.1:<port>`, and the proxy forwards to the HTTPS backend with TLS.

---

## 2. Build Instructions

### 2.1 Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Node.js | 20+ | Frontend build |
| npm | 10+ | Frontend dependency management |
| Rust | 1.90+ | Tauri backend compilation |
| cargo | Bundled with Rust | Rust package manager |

### 2.2 Build for Linux (x86_64)

```bash
cd /home/winst/agent-gate/.kilo/worktrees/integration-agentgate-dashboard/frontend

# Install dependencies (if not already installed)
npm install

# Build frontend (TypeScript + Vite)
npm run build

# Build Tauri application
npm run tauri build
# or: cargo tauri build
```

**Build outputs (Linux x86_64):**
- `src-tauri/target/release/bundle/deb/AgentGate_0.1.0_amd64.deb`
- `src-tauri/target/release/bundle/rpm/AgentGate-0.1.0-1.x86_64.rpm`
- `src-tauri/target/release/bundle/appimage/AgentGate_0.1.0_amd64.AppImage`

### 2.3 Build Configuration

Update `tauri.conf.json` before production build:
- Set `build.frontendDist` to `../dist` (already configured).
- Update CSP `connect-src` to include the production backend URL.
- Set `productName`, `version`, `identifier` as needed.
- Verify icon files exist in `src-tauri/icons/`.

---

## 3. Installation Instructions

### Linux — AppImage (x86_64)
```bash
chmod +x AgentGate_0.1.0_amd64.AppImage
./AgentGate_0.1.0_amd64.AppImage
```
No installation required. User data stored in `~/.config/agentgate`.

### Linux — Debian/Ubuntu (.deb)
```bash
sudo dpkg -i AgentGate_0.1.0_amd64.deb
# or
sudo apt install ./AgentGate_0.1.0_amd64.deb
```

### Linux — Fedora/RHEL (.rpm)
```bash
sudo dnf install AgentGate-0.1.0-1.x86_64.rpm
# or
sudo yum install AgentGate-0.1.0-1.x86_64.rpm
```

**Runtime dependencies (Linux):** WebKitGTK 4.1, GTK 3, glibc, libssl, librsvg2, libxdo, libayatana-appindicator3.

---

## 4. Verification Results

| Check | Status | Notes |
|---|---|---|
| Frontend TypeScript (`tsc --noEmit`) | ✅ Pass | |
| Frontend ESLint | ✅ Pass | |
| Frontend production build (`npm run build`) | ✅ Pass | `dist/` generated |
| Tauri binary launches | ⚠️ Not tested locally | Requires Rust toolchain |
| Connects to deployed backend | ⚠️ Not tested | Requires VPS deployment |
| Login and session behavior | ⚠️ Not tested | Requires running backend |
| Dashboard navigation | ⚠️ Not tested | Requires running backend |
| Logout | ⚠️ Not tested | Requires running backend |
| API error handling | ⚠️ Not tested | Requires running backend |
| No localhost API URL in release | ⚠️ Not verified | CSP only allows configured origins |

---

## 5. Code Signing Status

| Platform | Signing Required | Signing Available | Status |
|---|---|---|---|
| Windows (Authenticode) | Yes | No | Not configured |
| Linux (GPG for .deb/.rpm) | Recommended | No | Not configured |
| macOS (Notarization) | N/A (not supported) | N/A | Future target |

**Verdict:** Unsigned internal-testing build only. Suitable for team testing on trusted machines. Not suitable for public distribution.

**Known limitations:**
- No code signing — users will see security warnings on installation.
- Windows runtime not verified (WebView2 origin + loopback proxy).
- macOS not supported (future target).
- ARM64 builds not available.
- Interactive GUI verification not captured in agent environment.

---

## 6. Update Strategy

- Releases tagged on GitHub (e.g., `v0.1.0`).
- Artifacts attached to GitHub Releases with SHA-256 checksums in release notes.
- No automatic update mechanism implemented yet.
- Users download and install new versions manually.

---

## 7. Release Artifacts (Current)

- `AgentGate_0.1.0_amd64.AppImage` (Linux portable)
- `AgentGate_0.1.0_amd64.deb` (Debian/Ubuntu)
- `AgentGate-0.1.0-1.x86_64.rpm` (Fedora/RHEL)

Version: 0.1.0. Architecture: x86_64. No code signing.