# AgentGate — Security Assessment

**Branch:** `integration/agentgate-dashboard`
**Assessor:** Anthony (DevSecOps), with Isaac (backend) for remediation
**Status:** In progress — AGT-007
**References:** OWASP ASVS v4.0, OWASP API Security Top 10 (2023)

---

## 1. Assessment Scope

The integrated AgentGate application backend (Django + allauth headless + domain applications) and frontend (React + Vite), deployed via Docker Compose on a Contabo VPS with Neon PostgreSQL.

**In scope:**
- Authentication and session security
- CSRF and CORS
- MFA and recovery codes
- Password handling
- Cookie configuration
- OAuth (GitHub, Google optional)
- Organization isolation
- Authorization and IDOR/BOLA
- Profile update permissions
- Sensitive data exposure
- Input validation
- Rate limiting
- Security headers
- Secrets management
- Dependency vulnerabilities
- Database migration safety
- Logging and audit trails

**Out of scope:** PayPal sandbox (separate branch), mobile apps, third-party SaaS.

---

## 2. Existing Security Controls (Verified)

| Control | Implementation | Status |
|---|---|---|
| Custom user model | `accounts.User` (UUID pk, AbstractUser) | ✅ |
| Password validators | Django built-in (similarity, length, common, numeric) | ✅ |
| Session cookies | `Secure`, `HttpOnly`, `SameSite=Lax` | ✅ |
| CSRF cookies | `Secure`, `SameSite=Lax`, `HttpOnly=False` (SPA reads token) | ✅ |
| Security headers | HSTS, X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy | ✅ |
| SSL redirect | `SECURE_SSL_REDIRECT = True` (exempts healthz/readyz) | ✅ |
| Proxy SSL header | `SECURE_PROXY_SSL_HEADER` for Caddy | ✅ |
| Rate limiting | DRF throttling (agent 60/min, anon 20/min, demo 60/min) | ✅ |
| Password reset rate limit | 3/h/key, 20/m/ip | ✅ |
| Email verification | Mandatory (allauth) | ✅ |
| MFA | TOTP + recovery codes (allauth MFA) | ✅ |
| MFA encryption | CustomMFAAdapter (Fernet at-rest) — key not configured | ⚠️ |
| Social account tokens | Not stored (`SOCIALACCOUNT_STORE_TOKENS = False`) | ✅ |
| Email-based account linking | Disabled (`SOCIALACCOUNT_EMAIL_AUTHENTICATION` not enabled) | ✅ |
| Domain allowlist | `ACCOUNT_ALLOWED_SIGNUP_DOMAINS` for signup and social login | ✅ |
| Admin path | Customizable via `DJANGO_ADMIN_PATH` | ✅ |
| Audit log | Hash-chained `audit_auditevent` with PostgreSQL triggers | ✅ |
| App role restrictions | `audit_auditevent` SELECT/INSERT only (no UPDATE/DELETE/TRUNCATE) | ✅ |
| Network segmentation | Docker edge/backend networks; Redis and DB internal-only | ✅ |
| Non-root container | `agentgate` system user | ✅ |
| Procrastinate jobs | PostgreSQL-backed (not Redis) | ✅ |

---

## 3. Security Findings

### 3.1 OPEN — MFA_ENCRYPTION_KEY not configured

**Severity:** High
**Component:** Backend (MFA)
**Finding:** `MFA_ENCRYPTION_KEY` environment variable is not set. The `CustomMFAAdapter` fails closed when the key is missing — TOTP enrollment and recovery-code generation are blocked. Django startup check `check_mfa_encryption_key` will raise `SystemExit` when `DEBUG=False`.
**Evidence:** `accounts.W001: MFA_ENCRYPTION_KEY is not configured` (Django system check output).
**Required action:** Generate a Fernet key (`Fernet.generate_key().decode()`) and set `MFA_ENCRYPTION_KEY` in `.env.production`. Never hardcode or commit the key.
**Owner:** Isaac (backend), Anthony (security review)

### 3.2 OPEN — Secrets stored on VPS filesystem

**Severity:** Medium
**Component:** Deployment
**Finding:** `.env.production` containing `DJANGO_SECRET_KEY`, `MFA_ENCRYPTION_KEY`, database credentials, and Redis password is stored on the VPS filesystem with `chmod 600`. No secrets manager is used.
**Evidence:** `.env.production.example` documents the pattern; no secrets manager integration exists.
**Required action:** Evaluate secrets manager (AWS Secrets Manager, HashiCorp Vault, or cloud provider equivalent) for production. For pilot, `chmod 600` + restricted SSH access is acceptable interim measure.
**Owner:** Winstone (DevOps)

### 3.3 OPEN — No automated backup encryption key management

**Severity:** Medium
**Component:** Backups
**Finding:** Backup encryption key (GPG/age) storage location not decided. If stored alongside backups, encryption provides no additional protection.
**Evidence:** `DATABASE_BACKUP_AND_RECOVERY.md` §2.4 states "Store the encryption key in a secrets manager" but no implementation exists.
**Required action:** Store backup encryption key in a separate secrets manager from backup storage.
**Owner:** Winstone (DevOps)

### 3.4 MONITORED — No dedicated security monitoring

**Severity:** Medium
**Component:** Operations
**Finding:** No intrusion detection, file integrity monitoring, or security alerting configured. Django security logger exists (`agentgate.security`) but no external forwarding.
**Evidence:** `apps/accounts/signals.py` emits MFA security events to `agentgate.security` logger; no external sink configured.
**Required action:** Configure log forwarding to centralized logging; add alerts for repeated auth failures, MFA bypass usage, and admin access.
**Owner:** Winstone (DevOps), Anthony (security review)

### 3.5 MITIGATED — Organization isolation via domain model

**Severity:** N/A (control in place)
**Component:** Authorization
**Finding:** Organization membership (`OrgMembership`) with roles (admin/approver/viewer) provides tenancy boundary. No evidence of IDOR/BOLA vulnerabilities in current code review.
**Evidence:** `accounts.OrgMembership` model with `UniqueConstraint(user, organization)`; domain apps filter by organization where applicable.
**Required action:** Anthony to perform targeted IDOR/BOLA testing on spend request, approval, and agent endpoints.
**Owner:** Anthony (security review)

### 3.6 MITIGATED — MFA bypass code is emergency-only

**Severity:** Low
**Component:** Authentication
**Finding:** `MFA_BYPASS_CODE` configured but used only for emergency access. Not exposed in frontend.
**Evidence:** `.env.production.example` includes `MFA_BYPASS_CODE`; no frontend or API endpoint references it.
**Required action:** Document bypass code usage procedure; rotate after each use.
**Owner:** Anthony (security review)

---

## 4. Vulnerability Register

| ID | Severity | Component | Finding | Status | Owner | Target |
|---|---|---|---|---|---|---|
| VULN-001 | High | MFA | `MFA_ENCRYPTION_KEY` not configured; MFA enrollment blocked | Open | Isaac + Anthony | Before MFA demo |
| VULN-002 | Medium | Secrets | `.env.production` on VPS filesystem; no secrets manager | Open | Winstone | Before production |
| VULN-003 | Medium | Backups | Backup encryption key storage undecided | Open | Winstone | Before backup automation |
| VULN-004 | Medium | Monitoring | No security monitoring or alerting | Open | Winstone + Anthony | Before production |
| VULN-005 | Low | Auth bypass | `MFA_BYPASS_CODE` usage procedure undocumented | Open | Anthony | Before MFA demo |
| VULN-006 | Info | IDOR/BOLA | No confirmed vulnerabilities; targeted testing needed | In progress | Anthony | Before team access |

---

## 5. Remediation Plan

| Priority | Action | Owner | Dependency |
|---|---|---|---|
| P0 | Configure `MFA_ENCRYPTION_KEY` in `.env.production` | Isaac | None |
| P0 | Verify MFA enrollment/login flow end-to-end | Isaac + Del | VULN-001 |
| P1 | Evaluate secrets manager for `.env.production` | Winstone | VPS access |
| P1 | Configure backup encryption key management | Winstone | VULN-003 |
| P1 | Configure security log forwarding and alerting | Winstone + Anthony | VPS access |
| P2 | Perform IDOR/BOLA testing on spend/approval/agent endpoints | Anthony | VULN-006 |
| P2 | Document MFA bypass code procedure | Anthony | VULN-005 |

---

## 6. Items Requiring Approval

1. **Secrets manager selection** — Winstone to recommend; Tech Lead to approve.
2. **RPO/RTO targets** — Proposed 24h/4h; require approval.
3. **MFA bypass code procedure** — Anthony to document; Tech Lead to approve.
4. **Production deployment go/no-go** — After all P0/P1 items complete.