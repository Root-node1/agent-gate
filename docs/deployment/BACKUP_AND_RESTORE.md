# AgentGate — Backup and Restore

**Branch:** `integration/agentgate-dashboard`
**Baseline:** `origin/main` at `0f247755589630ea34b7c79785e3f44eca468746`
**Database:** Neon PostgreSQL (external managed service)
**Status:** Documented procedure; automation not yet deployed

---

## 1. Data Inventory

### 1.1 Persistent data (PostgreSQL via Neon)

All application state lives in PostgreSQL. There are no uploaded media files (`MEDIA_ROOT` is not configured; no `FileField`/`ImageField` in models).

Critical tables:
- `accounts.User` — Custom user model (auth, MFA state) — High sensitivity
- `accounts.Organization` — Tenant organizations — Low
- `accounts.OrgMembership` — User–org roles — Medium
- `agents.Agent` / `agents.ApiKey` — Agent definitions, hashed API keys — High
- `spend.SpendRequest` — Spend requests with decisions — High (financial)
- `approvals.Approval` — Approval queue — Medium
- `audit.AuditEvent` — Append-only, hash-chained audit log — High (compliance)
- `procrastinate_jobs` / `procrastinate_events` — Background job queue — Low
- Django built-ins (sessions, auth, admin, sites, cache table) — Medium

### 1.2 Non-database persistent data

| Asset | Location | Backup needed? | Reason |
|---|---|---|---|
| Static files | `staticfiles/` | No | Reproducible from source via `collectstatic` |
| Redis cache | Redis container (AOF enabled) | No | Disposable cache; jobs are in PostgreSQL |
| Container images | Registry | No | Reproducible from Dockerfile |
| `.env.production` | VPS filesystem | **Yes** | Contains secrets — secure off-server backup |
| Caddy certificates | `caddy_data` volume | Optional | Auto-renewed by Let's Encrypt |
| Caddy config | `caddy_config` volume | Optional | Reproducible |

---

## 2. Backup Strategy

### 2.1 Neon Managed Backups

Neon provides managed storage-level backups and point-in-time recovery (PITR). Retention depends on the Neon plan. **Verify against the actual Neon plan before relying on managed backups alone.**

AgentGate maintains **independent** `pg_dump` backups stored off-server as an additional layer.

### 2.2 Independent Logical Backups (AgentGate-maintained)

**Frequency:** Daily (proposed)
**Format:** Custom format (`--format=custom`) for selective restore
**Scope:** Full database dump (all tables including Procrastinate and audit)
**Tool:** `pg_dump` from a PostgreSQL 17-compatible client
**Connection:** Direct Neon URL (not transaction pooler) for consistent snapshot

**Command:**
```bash
pg_dump "$DATABASE_URL" --format=custom --file=agentgate-$(date +%F).dump
```

### 2.3 Dump Integrity Verification

1. **File size check:** Compare against previous dumps; alert on significant size drops.
2. **Checksum:** Generate `sha256sum` of the dump file and store alongside it.
3. **Restore test:** Restore into a temporary database and run Django checks (see §4).

### 2.4 Encryption

Encrypt dumps before off-server storage:

```bash
# Symmetric encryption (age)
age -r age1publickey... agentgate-$(date +%F).dump > agentgate-$(date +%F).dump.age

# Or symmetric GPG
gpg --symmetric --cipher-algo AES256 agentgate-$(date +%F).dump
```

- Store the encryption key in a secrets manager, NOT alongside the backups.
- Never store unencrypted dumps off-server.

### 2.5 Access Control

- Backup credentials (Neon connection URL) stored in a secrets manager.
- Backup storage with IAM policies restricting access to backup operators only.
- No backup credentials in the application repository or image.
- Rotate backup credentials periodically.

### 2.6 Retention Policy (Proposed — Requires Approval)

| Backup Type | Frequency | Retention | Storage |
|---|---|---|---|
| Neon managed (PITR) | Continuous | Plan-dependent | Neon |
| Logical dump (full) | Daily | 30 days | Off-server encrypted |
| Logical dump (weekly) | Weekly | 90 days | Off-server encrypted |
| Logical dump (monthly) | Monthly | 12 months | Off-server encrypted (cold storage) |
| Pre-migration dump | Before each migration | 30 days | Off-server encrypted |

**Recovery Objectives (Proposed):**
- **RPO:** 24 hours (daily backups)
- **RTO:** 4 hours (provisioning, restore, verification, switch)

---

## 3. Restore Strategy

### 3.1 Core Principle

**Never overwrite an existing database during a test restore.** Always restore into a separate, temporary database.

### 3.2 Full Database Recovery Procedure

1. **Provision a temporary database** (Neon branch or local PostgreSQL 17 instance):
   ```bash
   # Neon: create a branch from the latest restore point (Neon dashboard)
   # Local: createdb agentgate_restore_test
   ```

2. **Restore the dump:**
   ```bash
   pg_restore --dbname="$RESTORE_URL" --clean --if-exists agentgate-YYYY-MM-DD.dump
   ```

3. **Verify schema and migration state:**
   ```bash
   DJANGO_SETTINGS_MODULE=config.settings.prod DATABASE_URL="$RESTORE_URL" \
     python manage.py showmigrations
   DJANGO_SETTINGS_MODULE=config.settings.prod DATABASE_URL="$RESTORE_URL" \
     python manage.py migrate --check
   ```

4. **Verify important records (counts only, not values):**
   ```sql
   SELECT count(*) FROM accounts_user;
   SELECT count(*) FROM accounts_organization;
   SELECT count(*) FROM spend_spendrequest;
   SELECT count(*) FROM audit_auditevent;
   SELECT count(*) FROM procrastinate_jobs;
   ```

5. **Verify audit-chain integrity:**
   ```bash
   DJANGO_SETTINGS_MODULE=config.settings.prod DATABASE_URL="$RESTORE_URL" \
     python manage.py verify_audit
   ```

6. **Verify authentication records (presence only, no secrets):**
   - Confirm `accounts_user` has expected rows.
   - Confirm `agents_apikey` has expected prefixes (do NOT print key hashes).
   - Confirm MFA-related fields are populated where expected.

7. **Verify Procrastinate tables:**
   ```sql
   SELECT count(*) FROM procrastinate_jobs;
   SELECT count(*) FROM procrastinate_workers;
   ```

8. **Run Django checks:**
   ```bash
   DJANGO_SETTINGS_MODULE=config.settings.prod DATABASE_URL="$RESTORE_URL" \
     REDIS_URL="redis://localhost:6379/0" MFA_ENCRYPTION_KEY="..." \
     python manage.py check --deploy
   ```

9. **Run relevant tests against the restored database:**
   ```bash
   TEST_DATABASE_URL="$RESTORE_URL" python manage.py test
   ```

10. **Switch connectivity only after approval:**
    - Update `DATABASE_URL` in `.env.production` to point to the restored database.
    - Restart web and worker containers.
    - Verify `/readyz` returns 200.
    - Monitor logs for errors.

### 3.3 Recovery Scenarios

| Scenario | Procedure |
|---|---|
| Full database recovery | Restore from latest dump into a new database; verify; switch `DATABASE_URL`. |
| Accidental record deletion | Restore into temporary database; extract deleted rows; re-insert manually (with approval). Never bulk-overwrite. |
| Uploaded files recovery | N/A — no media uploads exist. Static files are reproducible. |
| Compromised VPS | 1. Rotate all secrets. 2. Provision new VPS. 3. Restore DB from off-server backup. 4. Redeploy from Git (verified commit). 5. Revoke all API keys. 6. Audit `verify_audit` for tampering. |

---

## 4. Backup Automation (Not Yet Implemented)

**Status:** Not yet automated. Manual procedure documented above.

**Recommended implementation:** Cron job or systemd timer on the VPS that:
1. Runs `pg_dump` daily
2. Encrypts the dump
3. Transfers to off-server storage
4. Logs success/failure
5. Alerts on failure

**Open items:**
- Backup storage location (S3, off-server disk, etc.)
- Encryption key management (secrets manager selection)
- Monitoring tooling (cron + script vs. dedicated backup service)
- RPO/RTO targets (require approval)

---

## 5. Verification Status

- ✅ Backup procedure documented
- ❌ Backups not yet executed
- ❌ Restore test not yet performed
- ❌ Automation not yet deployed
- ❌ Off-server storage not configured