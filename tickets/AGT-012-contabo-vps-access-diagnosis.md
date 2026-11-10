# AGT-012: Contabo VPS Access Diagnosis

**Ticket ID:** AGT-012
**Title:** Diagnose SSH timeout to Contabo VPS and establish access requirements
**Objective:** Diagnose the SSH connection timeout to `vps.zindika.app` and determine exact steps to establish access.
**Priority:** High (blocks all deployment work)
**Status:** In Progress
**Assigned owner:** Winstone

## Context
The VPS `vps.zindika.app` (194.163.174.37) resolves via DNS and responds to ping, but SSH port 22 is unreachable (connection timed out). The SSH config (`~/.ssh/config`) defines `Host contabo` → `vps.zindika.app`, User `winstone`, port 22, IdentityFile `~/.ssh/contabo_ed25519`.

## Scope
- Verify local SSH configuration (`ssh -G contabo`)
- Verify key file existence and permissions
- Verify configured SSH port
- Test TCP connectivity to the configured port (`nc -vz -w 5 vps.zindika.app 22`)
- Test bounded SSH connection (`ssh -o BatchMode=yes -o ConnectTimeout=10 contabo echo`)
- Capture sanitized SSH diagnostic output (no private key contents)
- Determine whether the problem is local, network/firewall-related, or server-side
- Produce exact steps for resolving the blocker

## Acceptance Criteria
- SSH config verified and documented
- Key file permissions verified (600)
- TCP connectivity test result documented
- SSH diagnostic output captured (sanitized)
- Root cause identified: local, network/firewall, or server-side
- Exact resolution steps documented (e.g., correct port, Contabo control panel firewall rule, SSH service status)

## Dependencies
None

## Files/modules
- `~/.ssh/config`
- `~/.ssh/contabo_ed25519` (private key — never print contents)
- `~/.ssh/contabo_ed25519.pub`

## Testing
- `ssh -G contabo` — verify config resolution
- `ls -la ~/.ssh/contabo_ed25519` — verify key exists with 600 perms
- `nc -vz -w 5 vps.zindika.app 22` — test TCP port 22
- `ssh -o BatchMode=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 contabo echo` — bounded SSH test

## Definition of Done
- Root cause of SSH timeout identified
- Exact steps for user to resolve (via Contabo control panel or server console) documented
- Ticket status updated to Done or Blocked with clear next action

## Notes
- Do not perform broad port scans
- Do not modify firewall rules or SSH configuration remotely without authorization
- Do not print private key contents or passphrases
- If port 22 is unreachable, user must check Contabo customer control panel firewall settings or use server console