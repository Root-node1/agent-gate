# AgentGate Desktop — Proposed System Requirements

Status: proposed targets for review. Requirements are labeled **Verified**, **Proposed**, or **Not yet tested**.

## Windows (x86_64)

| Requirement | Minimum | Recommended | Status |
|---|---|---|---|
| OS | Windows 10 1903+ / Windows 11 | Windows 11 | Proposed |
| Architecture | x86_64 | x86_64 | Proposed |
| RAM | 4 GB | 8 GB | Proposed |
| Storage | 500 MB free | 1 GB free | Proposed |
| Display | 1280 x 720 | 1920 x 1080 | Proposed |
| WebView2 | Evergreen runtime (auto-installed by installer) | Latest | Proposed |
| Network | HTTPS access to hosted AgentGate backend | Same | Proposed |

## Linux (x86_64)

| Requirement | Minimum | Recommended | Status |
|---|---|---|---|
| OS | Ubuntu 22.04+ / Debian 12+ / Fedora 39+ | Ubuntu 24.04 LTS | Proposed |
| Architecture | x86_64 | x86_64 | Proposed |
| RAM | 4 GB | 8 GB | Proposed |
| Storage | 500 MB free | 1 GB free | Proposed |
| Display | 1280 x 720 | 1920 x 1080 | Proposed |
| WebKitGTK | 4.1 (libwebkit2gtk-4.1) | Latest | Proposed (verified installed locally: 2.52.6) |
| GTK | GTK 3 (libgtk-3) | Latest | Proposed |
| Runtime libs | glibc, libssl, librsvg2, libxdo, libayatana-appindicator3 | Same | Proposed |
| Network | HTTPS access to hosted AgentGate backend | Same | Proposed |

## Verified (local development environment)

- WebKitGTK 4.1: 2.52.6 (verified, TAURI-02)
- GTK 3: 3.24.52 (verified)
- Node.js: v22.23.4 (verified)
- Rust: 1.99.1 stable (verified)
- WSLg GUI: available (verified, window registered in compositor)

## Not yet tested

- Windows WebView2 runtime behavior.
- macOS (not supported in initial release).
- ARM64 architectures.
- Actual installer/uninstaller behavior on clean OS images.
- Offline operation (backend is remote; internet required).
