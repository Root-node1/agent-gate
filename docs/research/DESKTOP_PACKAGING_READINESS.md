# AgentGate Desktop — Windows Packaging and Installer Readiness

**Task:** AG-03 — Desktop Packaging and Windows Installer Readiness Audit
**Worktree:** `/home/winst/agent-gate/.kilo/worktrees/intergration`
**Branch:** `intergration`
**HEAD:** `6775c8df38484a748a6b11f346a0b3d428f150e0`
**Audit date:** 2026-11-01
**Mode:** Read-only audit + single report. No builds, no source edits, no commits, no pushes.

> Verified facts are stated as such. Recommendations and untested assumptions are explicitly labeled.

---

## 1. Preflight

| Check | Result |
|---|---|
| `git rev-parse --show-toplevel` | `/home/winst/agent-gate/.kilo/worktrees/intergration` |
| `git branch --show-current` | `intergration` |
| `git rev-parse HEAD` | `6775c8df38484a748a6b11f346a0b3d428f150e0` (matches expected) |
| `git rev-parse origin/intergration` | `6775c8df38484a748a6b11f346a0b3d428f150e0` (in sync) |
| `git status --short --branch` | `## intergration...origin/intergration` + untracked `docs/research/` (AG-01/AG-02 reports) |
| Audit-root dirty files | `package.json`, `package-lock.json` present and untouched |

No material state differences. Proceeded.

---

## 2. Verified Configuration

### 2.1 File locations

| Artifact | Path |
|---|---|
| Tauri config | `frontend/src-tauri/tauri.conf.json` |
| Cargo manifest | `frontend/src-tauri/Cargo.toml` |
| Build script | `frontend/src-tauri/build.rs` |
| Rust entry (binary) | `frontend/src-tauri/src/main.rs` |
| Rust entry (lib) | `frontend/src-tauri/src/lib.rs` |
| Embedded server / proxy | `frontend/src-tauri/src/server.rs` |
| Capabilities | `frontend/src-tauri/capabilities/default.json` |
| Icons | `frontend/src-tauri/icons/` (32x32, 128x128, 128x128@2x, .icns, .ico, plus Windows Square* PNGs) |
| Frontend package | `frontend/package.json` |
| Vite config | `vite.config.ts` (root), `frontend/` (no separate vite config in frontend — root config used) |
| Desktop docs | `docs/desktop/DISTRIBUTION_PLAN.md`, `SYSTEM_REQUIREMENTS.md`, `TAURI_SECURITY_ARCHITECTURE.md` |
| CI workflow | `.github/workflows/ci.yml` (backend + frontend + security-audit; no desktop build) |
| Tauri .gitignore | `frontend/src-tauri/.gitignore` (ignores `/target/`, `/gen/schemas`) |

### 2.2 Tauri version

- **Tauri v2.12.x** (verified):
  - `Cargo.toml`: `tauri = "2.12.5"`, `tauri-build = "2.7.4"`, `tauri-plugin-log = "2"`, `tauri-macros = 2.7.4` (transitive).
  - `frontend/package.json`: `@tauri-apps/cli ^2.12.4`, `@tauri-apps/api ^2.12.4`.
  - Config schema references `@tauri-apps/cli/config.schema.json`.
  - Rust edition 2024, `rust-version = "1.90"`. Cargo 1.99.1 / rustc 1.99.1 verified locally (AG-02).

### 2.3 Application identity

- `productName`: `AgentGate`
- `version`: `0.1.0`
- `identifier`: `com.agentgate.desktop`

### 2.4 Bundle configuration

- `bundle.active`: `true`
- `bundle.targets`: `"all"` → on Windows produces **both** `.msi` (WiX) and `.exe` (NSIS) installers.
- `bundle.icon`: `32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.icns`, `icon.ico` (plus Windows Store Square* PNGs in icons dir).
- `bundle.android`: `debugApplicationIdSuffix: ".debug"` (Android-only, not relevant to Windows).
- **No code signing configured** (no `windows` signing key, no `createUpdaterArtifacts`, no updater plugin).

### 2.5 Build pipeline

- `build.frontendDist`: `../dist` (relative to src-tauri → `frontend/dist`).
- `build.devUrl`: `http://localhost:5173`
- `build.beforeDevCommand`: `npm run dev`
- `build.beforeBuildCommand`: `npm run build` (→ `tsc -b && vite build`).
- `app.windows`: `[]` (window created programmatically in `lib.rs`).
- `app.security.csp`: see §4.1.
- `app.security.freezePrototype`: `true`.

### 2.6 Frontend scripts (package.json)

| Script | Command |
|---|---|
| `dev` | `vite` |
| `build` | `tsc -b && vite build` |
| `lint` | `eslint .` |
| `tauri` | `tauri` |
| `tauri:dev` | `tauri dev` |
| `tauri:build` | `tauri build` |

**Exact Windows x64 build command:** `npm run tauri:build` (run from `frontend/`), equivalently `npx tauri build`. This invokes `npm run build` first, then `tauri build`. Output (expected, not yet produced): `frontend/src-tauri/target/release/bundle/msi/AgentGate_0.1.0_x64_en-US.msi` and `.../nsis/AgentGate_0.1.0_x64-setup.exe`, plus the binary at `target/release/app.exe`.

### 2.7 Rust / backend launcher

- `main.rs`: `#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]` (no console window in release), calls `app_lib::run()`.
- `lib.rs::run()`: In release, resolves `dist` (frontend build output), starts embedded loopback server (`server::start_server(dist)`) on an ephemeral port (`127.0.0.1:0`), then opens a WebView window pointed at `http://127.0.0.1:<port>`. In debug, uses `http://localhost:5173`.
- `server.rs`: tiny_http-based embedded server. Proxies `/api` and `/v1` to `backend_url()` (default `http://127.0.0.1:8000`, override via `AGENTGATE_BACKEND_URL` env var). Serves static frontend files otherwise. Host header validated (loopback only). Path traversal protection. 10 MiB body limit. Allowed methods: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS.
- `AGENTGATE_BACKEND_URL` is read at runtime via `std::env::var` with no validation (no scheme allowlist, no host allowlist). See §4.3.

### 2.8 Capabilities

`capabilities/default.json`: only `core:default` permission, window `main`. No shell, filesystem, HTTP, or updater permissions. Least privilege. ✅

---

## 3. Answers to the Required Questions

**1. Tauri version:** v2.12.x (2.12.5 Rust crate, 2.12.4 JS packages). Verified via Cargo.toml and package.json.

**2. Windows targets and bundlers:** `bundle.targets: "all"` → on Windows this produces **MSI (WiX)** and **NSIS (.exe)**. No explicit `windows` target override. Architecture: x86_64 (default; no ARM64 configured).

**3. Exact build command:** `npm run tauri:build` from `frontend/` (or `npx tauri build`). Runs `npm run build` (tsc + vite) as `beforeBuildCommand`, then bundles. Must be run on a Windows host (or Windows CI runner) for Windows installers; on Linux produces `.deb`/`.rpm`/`.AppImage`.

**4. Installer formats:** Both `.msi` and `.exe` (NSIS) should be produced (config says "all"). Recommendation: ship MSI as primary for enterprise/managed deployment, NSIS as alternative. (Recommendation, not verified — no Windows build has been run.)

**5. Artifact output paths (expected, not yet produced):**
- `frontend/src-tauri/target/release/bundle/msi/AgentGate_0.1.0_x64_en-US.msi`
- `frontend/src-tauri/target/release/bundle/nsis/AgentGate_0.1.0_x64-setup.exe`
- Binary: `frontend/src-tauri/target/release/app.exe`
- (Linux equivalents already documented: `AgentGate_0.1.0_amd64.deb`, `AgentGate-0.1.0-1.x86_64.rpm`, `AgentGate_0.1.0_amd64.AppImage`)

**6. Windows prerequisites (proposed, not verified on clean image):**
- Windows 10 1903+ or Windows 11, x86_64.
- WebView2 Evergreen runtime (auto-bootstrapped by the Tauri installer if missing).
- Visual C++ Redistributable (WebView2 dependency; usually present).
- Network access to the AgentGate backend (HTTPS recommended; see blocker §4.3).
- ~500 MB free disk, 4 GB RAM minimum (proposed, from SYSTEM_REQUIREMENTS.md).

**7. Backend launch:** The desktop app does **not** bundle or launch Django. It embeds a loopback HTTP server (tiny_http) that proxies `/api` and `/v1` to a backend URL. The Django backend must run separately (local dev on `127.0.0.1:8000`, or a hosted HTTPS backend). This is an intentional decision (DISTRIBUTION_PLAN.md §1, alternatives B/C rejected).

**8. Hosted backend connectivity:** The frontend uses relative paths proxied through the loopback server, so it works with any backend the proxy targets. **However, the embedded proxy uses plain TCP (`TcpStream`) with no TLS.** It cannot connect to an HTTPS backend today. The distribution plan recommends hosted HTTPS, but the implementation only supports HTTP. This is a **blocker** for secure production use (see §6).

**9. AGENTGATE_BACKEND_URL handling:**
- Read at runtime in `server.rs::backend_url()` via `std::env::var("AGENTGATE_BACKEND_URL")`, defaulting to `http://127.0.0.1:8000`.
- **No validation**: no scheme allowlist, no host allowlist, no SSRF guard. A malicious or misconfigured value would redirect all proxied traffic (including credentials/cookies) to an attacker-controlled endpoint.
- The value is a build/deploy-time environment variable, not user input, but it is not validated. **Security gap.**
- The CSP `connect-src` in `tauri.conf.json` is hardcoded to `http://127.0.0.1:8000 http://localhost:8000` and must be updated per environment before build (distribution plan §1). No wildcards.

**10. Auth/CSRF/CORS/cookie compatibility:**
- Dashboard auth: Django session cookies + allauth Headless, `SameSite=Lax`, `HttpOnly`. Frontend uses `credentials: "include"` and CSRF token via `X-CSRFToken`. This works because the frontend and proxy share `127.0.0.1:<port>` (same origin), and the proxy forwards to the backend.
- For a hosted HTTPS backend, the proxy must forward with TLS (not implemented) and `CSRF_TRUSTED_ORIGINS` must include the desktop origin. `SameSite=Lax` cookies work cross-origin only if same-site; the loopback-proxy approach retains same-origin between frontend and proxy. Documented limitation.
- Agent (machine) auth: `Authorization: Bearer <agent key>` — unaffected by desktop packaging.
- MFA: backend-enforced; desktop must not cache MFA state. `MFA_TRUST_ENABLED = False`.
- No JWT/OAuth/native credential storage introduced. ✅

**11. Code signing:** Not configured. No Authenticode certificate, no signing identity in `tauri.conf.json`, no updater. Users should expect **Windows SmartScreen "Unknown publisher" warnings** and possible browser/Defender download warnings. MSI may trigger "Windows protected your PC" prompts. **Blocker for public distribution.**

**12. GitHub Actions Windows builds:** No release workflow exists (only `ci.yml` covering backend/frontend/security-audit). Feasible to add a `windows-latest` runner job using `tauri-action` (or manual `npm run tauri:build` with Rust + Node setup), producing MSI/NSIS and attaching to a GitHub Release on tag. Not configured today. (Recommendation only — not implemented in this audit.)

**13. Runtime/install tests still required:**
- WebView2 origin (`tauri://localhost` / `https://tauri.localhost`) vs loopback proxy behavior on Windows.
- Cookie/CSRF flow through the proxy to a backend (local and hosted).
- MSI install/uninstall, upgrade via major upgrade, per-user vs per-machine.
- NSIS installer behavior.
- SmartScreen warning UX.
- Auto-start / sidecar lifecycle (no sidecar is used; backend is external).
- GUI visual verification (no screenshot tooling in agent env; marked partially verified).
- Backend TLS in proxy (if hosted HTTPS is the target).

---

## 4. Security Review

### 4.1 CSP (verified from tauri.conf.json)

```
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;
font-src 'self' data:;
connect-src 'self' http://127.0.0.1:8000 http://localhost:8000;
object-src 'none';
base-uri 'self';
frame-ancestors 'none'
```

- `freezePrototype: true`. ✅
- Scripts are strict (`'self'` only). ✅
- `unsafe-inline` styles required by Vite/React (documented). ✅
- `connect-src` restricted to local backend (no wildcards). ✅
- Hosted HTTPS origin must be added explicitly before a hosted-backend build. Do not use wildcards. (Recommendation.)

### 4.2 Secrets bundled

- No API secrets, PayPal credentials, access tokens, MFA keys, or webhook secrets are bundled in the frontend or Rust code. ✅ Verified by grep (only dev URL in `settingsData.ts`).
- No live PayPal environment configured (frontend has no PayPal code; payments live only in `feat/paypal-sandbox`). ✅
- No development backend exposed publicly — embedded server binds `127.0.0.1:0` (loopback only). ✅

### 4.3 AGENTGATE_BACKEND_URL validation gap

`backend_url()` reads the env var with no validation. A misconfigured value redirects all proxied traffic (including session cookies and agent keys) to an arbitrary endpoint. **Security gap — must be fixed before supporting hosted backends** (add scheme allowlist: HTTPS only in production; host allowlist).

### 4.4 Least privilege

- Capabilities: only `core:default`. No shell, fs, HTTP, or updater permissions. ✅
- No deep-link handler registered. ✅
- No updater plugin. ✅

### 4.5 Traceability

- Version `0.1.0` is hardcoded in `tauri.conf.json`. Source commit is not embedded. Recommendation: inject the git commit SHA at build time (e.g., via `TAURI_CONF` override or env) for artifact traceability. Not implemented.

### 4.6 Known limitations (from docs)

- Embedded proxy is HTTP-only (no TLS) — blocks secure hosted-backend use.
- Request-body read loop has no per-read timeout (10 MiB cap only) — slow-body DoS risk on the single-threaded server (documented as accepted limitation, TAURI-10 Phase 5).
- GUI visual verification partially verified (no screenshot tooling in agent env).

---

## 5. Windows Installer GO / NO-GO Decision

**Decision: NO-GO for public Windows distribution.** GO for internal/developer testing only.

**Blockers (must resolve before public release):**

1. **No Windows build has been produced or tested** — no installer exists; WebView2 origin + loopback proxy behavior on Windows is unverified.
2. **No code signing** — SmartScreen warnings will block/break user trust; Authenticode certificate required.
3. **Embedded proxy is HTTP-only** — cannot securely reach a hosted HTTPS backend; either add TLS to the proxy or document local-backend-only mode.
4. **AGENTGATE_BACKEND_URL is unvalidated** — SSRF/misconfiguration risk.
5. **No GitHub Actions release workflow** — no automated Windows build/sign/publish pipeline.
6. **CSP connect-src hardcoded to localhost** — must be updated per environment before a hosted-backend build; no automation.
7. **CSRF_TRUSTED_ORIGINS** must include desktop origins before release.
8. **GUI visual verification** incomplete.

**What is ready:**
- Rust compiles, clippy clean, 11/11 unit tests pass, frontend builds and lints.
- CSP is strict; capabilities are minimal; no secrets bundled; loopback-only listener.
- Auth contract (session cookies + CSRF) is documented as compatible via the loopback proxy.

---

## 6. Recommended Manual Test Plan (teammate, Windows x64)

1. Install Rust toolchain (stable ≥ 1.90) and Node 22+ on a Windows 10/11 x64 machine.
2. Clone repo, `cd frontend`, `npm install`.
3. Set `AGENTGATE_BACKEND_URL=http://127.0.0.1:8000` (dev) in the shell before build.
4. Run `npm run tauri:build`. Confirm MSI and NSIS artifacts appear under `frontend/src-tauri/target/release/bundle/`.
5. Install the MSI. Confirm no missing WebView2 (installer bootstraps if needed). Confirm uninstall removes the app.
6. Launch the app. Confirm the window opens (no console window) and the frontend loads.
7. Start a local Django backend on `127.0.0.1:8000`. Confirm the embedded proxy forwards `/api` and `/v1` and the dashboard loads.
8. Log in via allauth Headless. Confirm session cookie is set and CSRF flow works. Confirm MFA enrollment prompt for privileged roles.
9. Submit a spend request with an agent key. Confirm decision + idempotency.
10. Verify CSP in the packaged build (DevTools console — no violations for normal flows).
11. Inspect `%APPDATA%` / install dir for leaked secrets or logs.
12. Record SmartScreen warning UX and any installer prompts.

---

## 7. Recommended Next Task

**AG-04 — Add Windows TLS support to the embedded proxy and validate hosted-backend connectivity** (or a dedicated "Windows build + smoke test" task) before any public release. Secondary: provision Authenticode signing and a `tauri-action`-based release workflow.

---

## 8. Commands Used (read-only)

```
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short --branch
git rev-parse origin/intergration
git worktree list --porcelain
cat frontend/src-tauri/tauri.conf.json
cat frontend/src-tauri/Cargo.toml
cat frontend/src-tauri/build.rs
cat frontend/src-tauri/src/main.rs
cat frontend/src-tauri/src/lib.rs
cat frontend/src-tauri/src/server.rs
cat frontend/src-tauri/capabilities/default.json
cat frontend/package.json
cat vite.config.ts
cat frontend/index.html
cat frontend/src-tauri/.gitignore
cat docs/desktop/DISTRIBUTION_PLAN.md
cat docs/desktop/SYSTEM_REQUIREMENTS.md
sed -n '1,120p' docs/desktop/TAURI_SECURITY_ARCHITECTURE.md
ls .github/workflows/
grep -rn "AGENTGATE_BACKEND_URL\|backendUrl\|BACKEND_URL" frontend/ docs/
grep -rni "sign\|certificate\|updater\|createUpdaterArtifacts" frontend/src-tauri/ .github/
python3 -c "import json; ..." (tauri.conf parse)
```

No builds, installs, source edits, commits, pushes, or DB operations were performed.

---

**STOP. Awaiting Tech Lead review.**
filePath">
/home/winst/agent-gate/.kilo/worktrees/intergration/docs/research/DESKTOP_PACKAGING_READINESS.md