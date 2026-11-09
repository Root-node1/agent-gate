# AGT-016: Tauri Desktop Distribution

**Ticket ID:** AGT-016
**Title:** Complete internal-testing Tauri desktop release
**Objective:** Validate existing `.deb` and `.rpm` artifacts, investigate AppImage packaging, and document internal-testing desktop release.
**Priority:** High (presentation deadline)
**Status:** Not started
**Assigned owner:** Del, with Winstone handling release/infrastructure

## Context
Tauri desktop build succeeded producing `.deb` (4.5MB) and `.rpm` (4.5MB) artifacts. AppDir generated but standalone AppImage not yet packaged. Build is unsigned — internal testing only.

## Scope
- Validate existing `.deb` and `.rpm` artifacts
- Investigate AppImage packaging and complete if feasible
- Configure correct remote backend URL (not localhost)
- Verify no development localhost endpoint embedded in release build
- Verify desktop application launches
- Test authentication (login, session restoration)
- Test dashboard navigation
- Test logout
- Document installation instructions
- Clearly disclose signing limitations

## Acceptance Criteria
- Existing `.deb` and `.rpm` validated as real packages
- AppImage packaging investigated and completed if feasible
- Correct remote backend URL configured (from `AGENTGATE_BACKEND_URL`)
- No `http://127.0.0.1:8000` or `http://localhost:8000` embedded in release build CSP
- Desktop application launches
- Authentication tested against deployed backend
- Dashboard tested
- Logout tested
- Installation instructions documented
- Signing limitations clearly disclosed

## Dependencies
- AGT-013 (deployed backend needed for connectivity testing)

## Files/modules
- `frontend/src-tauri/tauri.conf.json` (CSP connect-src)
- `frontend/src-tauri/src/server.rs` (backend URL validation)
- `frontend/src/api/auth.ts` (API client)
- `docs/deployment/TAURI_DESKTOP_RELEASE.md`

## Testing
- `file AgentGate_0.1.0_amd64.deb` — valid Debian package
- `file AgentGate-0.1.0-1.x86_64.rpm` — valid RPM
- Desktop app launches without errors
- Login succeeds against deployed backend
- Session restoration works
- Dashboard navigation works
- Logout works
- No hardcoded localhost API URL in release build

## Definition of Done
- Artifacts validated and documented
- Internal-testing build ready (unsigned)
- Signing limitations disclosed
- Backend connectivity verified

## Notes
- Do not claim signed production-ready installer if code signing not configured
- If signing unavailable, prepare unsigned internal-testing build and document limitations
- macOS not supported (future target)
- ARM64 builds not available