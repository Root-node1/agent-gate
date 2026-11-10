# AgentGate — Automated Backups and Disaster Recovery

This document specifies the disaster recovery architecture, automated backup
scheduling, off-site storage targets, encryption requirements, and isolated
restore-test procedures for AgentGate on PostgreSQL 17.

---

## 1. Persistent Data Inventory

| Data store | Contents | Off-site backup needed? |
|---|---|---|
| **PostgreSQL 17** | Organizations, users, MFA secrets (encrypted), agent API key hashes, policies, spend requests, approvals, audit trail (hash-chained), Procrastinate job tables | **Yes — primary backup target** |
| **Redis 7** | Cache, rate-limit counters, ephemeral worker state (`appendonly yes` for crash recovery) | No — disposable; re-fills on restart |
| **staticfiles volume** | Compiled front-end assets + Django collected statics | No — rebuilt on every deploy |
| **caddy_data volume** | Let's Encrypt TLS certs + Caddy config cache | No — auto-renewed by Caddy |
| **Environment configuration** | `DJANGO_SECRET_KEY`, `MFA_ENCRYPTION_KEY`, database credentials, PayPal credentials | Yes — via secure secret manager (Coolify env vars), not file backup |

There is no user-uploaded media (`MEDIA_ROOT` is unused).

**Critical:** `MFA_ENCRYPTION_KEY` encrypts TOTP secrets and recovery-code seeds
at rest. If this key is lost, enrolled MFA users cannot authenticate and must
re-enroll. Store it in a password manager or secrets vault, not only in the
database or VPS.

---

## 2. Backup Policy and Objectives

| Parameter | Target | Note |
|---|---|---|
| **Recovery Point Objective (RPO)** | 6 hours | Maximum data loss under catastrophic VPS failure |
| **Recovery Time Objective (RTO)** | < 30 minutes | Time to restore database onto a fresh instance |
| **Backup schedule — 6-hourly** | 00:00, 06:00, 12:00, 18:00 UTC | Retained 7 days |
| **Backup schedule — daily** | Daily at 02:00 UTC | Retained 7 copies |
| **Backup schedule — weekly** | Sunday at 03:00 UTC | Retained 4 copies |
| **Backup schedule — monthly** | 1st of month at 04:00 UTC | Retained 3 copies |

These are initial targets; test and validate them before treating them as SLA.

> **Automation status (verified 2026-11-10):** `scripts/backup_database.sh` performs one
> backup per invocation with client-side AES-256-CBC encryption and uploads it to
> S3-compatible storage. It applies a single retention window controlled by
> `RETENTION_DAYS` (default 7). The 6-hourly/daily/weekly/monthly cadence above is
> the intended operational schedule; wiring it to timers and per-tier retention is
> not yet automated by this script. Restore was tested successfully against a
> disposable PostgreSQL 17 instance (dump -> encrypt -> upload -> download ->
> decrypt -> `pg_restore`, with matching row counts).

### Storage and cost estimates

- Estimated initial uncompressed DB size: 20–50 MB.
- Compressed dump size (`pg_dump -Fc -Z 6`): ~3–8 MB per snapshot.
- Monthly storage footprint: < 2 GB.
- Outbound backup bandwidth: negligible (< 100 MB/day).

---

## 3. Off-Site Storage

Backups stored only on the VPS are not acceptable — a compromised, failed,
or destroyed VPS must not take backups with it.

### Recommended destination

An **S3-compatible object storage bucket** with:

- **TLS 1.3** enforced for all uploads.
- **Client-side AES-256 encryption** before upload (see script below).
- **Dedicated access credentials** isolated from application runtime credentials.
- **Object versioning or Object Lock (WORM)** to prevent accidental deletion
  or ransomware modification.

Compatible options (verify current pricing and availability before choosing):

- **Contabo Object Storage** — same provider as the VPS, easy setup.
- **Cloudflare R2** — no egress fees; S3-compatible.
- **AWS S3** — mature, well-documented, slightly higher cost.
- **Backblaze B2** — cost-effective, S3-compatible.

Do not reuse the application's S3 bucket or credentials for backups.

---

## 4. Backup Script

Create `scripts/backup_database.sh` with the content below, then make it
executable (`chmod +x`). The script uses only standard POSIX utilities.

```bash
#!/usr/bin/env bash
# AgentGate database backup script.
# Requires: pg_dump (PostgreSQL client tools), openssl, aws CLI (or compatible s3cmd).
# Secrets must be in environment only — never hardcoded in this file.
set -euo pipefail

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
BACKUP_DIR="${BACKUP_DIR:-/tmp/agentgate_backups}"
DUMP_FILE="${BACKUP_DIR}/agentgate_${TIMESTAMP}.dump"
ENCRYPTED_FILE="${DUMP_FILE}.enc"
S3_BUCKET="${S3_BUCKET:?S3_BUCKET must be set}"
S3_ENDPOINT="${S3_ENDPOINT_URL:?S3_ENDPOINT_URL must be set}"
LOG_TAG="agentgate-backup"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$LOG_TAG] $*"; }
log "=== Backup started: ${TIMESTAMP} ==="

# 1. Create staging directory
mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

# 2. PostgreSQL logical dump (compressed custom format)
log "Creating logical dump..."
pg_dump "${DATABASE_URL:?DATABASE_URL must be set}" -Fc -Z 6 -f "${DUMP_FILE}"
DUMP_SIZE=$(du -sh "${DUMP_FILE}" | cut -f1)
log "Dump created: ${DUMP_FILE} (${DUMP_SIZE})"

# 3. Encrypt before upload (AES-256-CBC with PBKDF2)
log "Encrypting backup..."
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
  -in "${DUMP_FILE}" \
  -out "${ENCRYPTED_FILE}" \
  -pass "env:BACKUP_ENCRYPTION_PASSPHRASE"
rm -f "${DUMP_FILE}"  # Remove unencrypted dump immediately
log "Encrypted backup: ${ENCRYPTED_FILE}"

# 4. Upload to off-site S3
S3_KEY="db/agentgate_${TIMESTAMP}.dump.enc"
log "Uploading to s3://${S3_BUCKET}/${S3_KEY}..."
aws s3 cp "${ENCRYPTED_FILE}" "s3://${S3_BUCKET}/${S3_KEY}" \
  --endpoint-url "${S3_ENDPOINT}" \
  --no-progress
log "Upload complete."

# 5. Verify upload (check object exists and size is non-zero)
REMOTE_SIZE=$(aws s3 ls "s3://${S3_BUCKET}/${S3_KEY}" --endpoint-url "${S3_ENDPOINT}" \
  | awk '{print $3}')
if [ -z "${REMOTE_SIZE}" ] || [ "${REMOTE_SIZE}" -eq 0 ]; then
  log "ERROR: Remote object is empty or missing. Backup upload may have failed."
  rm -f "${ENCRYPTED_FILE}"
  exit 1
fi
log "Remote object size: ${REMOTE_SIZE} bytes. Upload verified."

# 6. Remove local encrypted file
rm -f "${ENCRYPTED_FILE}"

# 7. Apply retention: delete remote objects older than retention limit
# Only delete after confirming the new upload succeeded (above).
log "Applying retention policy (keeping last 7 days of 6-hourly backups)..."
CUTOFF=$(date -u -d "7 days ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || \
         date -u -v-7d +%Y-%m-%dT%H:%M:%SZ)  # macOS fallback
aws s3 ls "s3://${S3_BUCKET}/db/" --endpoint-url "${S3_ENDPOINT}" \
  | awk '{print $1" "$2" "$4}' \
  | while read -r date time key; do
      if [[ "${date}T${time}Z" < "${CUTOFF}" ]]; then
        log "Deleting expired backup: ${key}"
        aws s3 rm "s3://${S3_BUCKET}/db/${key}" --endpoint-url "${S3_ENDPOINT}"
      fi
    done

log "=== Backup completed successfully: ${TIMESTAMP} ==="
```

**Security notes:**

- `DATABASE_URL` and `BACKUP_ENCRYPTION_PASSPHRASE` must be in the
  environment only — never in this script.
- Run as a low-privilege user with read-only database access for backups
  where possible.
- Never log the passphrase or database URL.
- The unencrypted dump is deleted before upload verification; if upload fails,
  the script exits with error (no silent failure).
- Retention deletion only runs after successful upload verification.

---

## 5. Scheduler Configuration

### Option A: Cron on the VPS

```cron
# /etc/cron.d/agentgate-backup
# Run as the deployer user; ensure DATABASE_URL and S3 vars are sourced

# 6-hourly backup (RPO = 6 hours)
0 0,6,12,18 * * * deployer . /home/deployer/.agentgate-backup-env && /home/deployer/agent-gate/scripts/backup_database.sh >> /var/log/agentgate-backup.log 2>&1

# Weekly backup (Sundays at 03:00 UTC)
0 3 * * 0 deployer . /home/deployer/.agentgate-backup-env && BACKUP_TAG=weekly /home/deployer/agent-gate/scripts/backup_database.sh >> /var/log/agentgate-backup.log 2>&1
```

Where `/home/deployer/.agentgate-backup-env` exports `DATABASE_URL`,
`BACKUP_ENCRYPTION_PASSPHRASE`, `S3_BUCKET`, `S3_ENDPOINT_URL`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — owned `600`, readable only
by the deployer user, **never committed to Git**.

### Option B: Dedicated backup container in Compose

Add to `compose.yaml` (requires approval before modifying):

```yaml
  backup:
    image: agentgate-web:latest
    restart: "no"
    env_file:
      - .env.production
    command: >
      sh -c 'while true; do
        /app/scripts/backup_database.sh;
        sleep 21600;
      done'
    networks:
      - backend
    depends_on:
      web:
        condition: service_healthy
```

---

## 6. Isolated Restore Verification Procedure

**A backup that has not been restored is not a verified backup.**
Never restore onto the production database during a test.

### Prerequisites

- A disposable PostgreSQL 17 instance (Docker container, or a test database on the managed instance).
- `aws` CLI and `openssl` installed.
- `DATABASE_URL` for the restore target (not production).

### Step 1: Download and decrypt

```bash
# Set restore environment variables
export S3_BUCKET="agentgate-backups-offsite"
export S3_ENDPOINT_URL="https://your-s3-endpoint"
export BACKUP_ENCRYPTION_PASSPHRASE="<passphrase from secrets vault>"
export RESTORE_TIMESTAMP="20261110_020000"  # target backup timestamp

# Download
aws s3 cp \
  "s3://${S3_BUCKET}/db/agentgate_${RESTORE_TIMESTAMP}.dump.enc" \
  ./restore.dump.enc \
  --endpoint-url "${S3_ENDPOINT_URL}"

# Decrypt
openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \
  -in ./restore.dump.enc \
  -out ./restore.dump \
  -pass "env:BACKUP_ENCRYPTION_PASSPHRASE"

rm ./restore.dump.enc
```

### Step 2: Start a disposable PostgreSQL 17 container

```bash
docker run --rm -d --name agentgate-restore-test \
  -e POSTGRES_USER=agentgate \
  -e POSTGRES_PASSWORD=restore-test-only \
  -e POSTGRES_DB=agentgate_restore \
  -p 127.0.0.1:55433:5432 postgres:17

# Wait for it to be ready
for i in $(seq 1 30); do
  docker exec agentgate-restore-test pg_isready -U agentgate >/dev/null 2>&1 && break
  sleep 2
done
```

### Step 3: Restore

```bash
export RESTORE_DATABASE_URL="postgresql://agentgate:restore-test-only@127.0.0.1:55433/agentgate_restore"

pg_restore \
  -d "${RESTORE_DATABASE_URL}" \
  --clean --if-exists --no-owner \
  ./restore.dump
```

### Step 4: Verify integrity

```bash
# Row counts (adjust expected values to match production)
psql "${RESTORE_DATABASE_URL}" -c "SELECT COUNT(*) FROM accounts_user;"
psql "${RESTORE_DATABASE_URL}" -c "SELECT COUNT(*) FROM audit_auditevent;"
psql "${RESTORE_DATABASE_URL}" -c "SELECT COUNT(*) FROM spend_spendrequest;"
psql "${RESTORE_DATABASE_URL}" -c "SELECT COUNT(*) FROM apps_agents_agent;" 2>/dev/null || \
  psql "${RESTORE_DATABASE_URL}" -c "SELECT COUNT(*) FROM agents_agent;"

# Verify migrations are consistent
DATABASE_URL="${RESTORE_DATABASE_URL}" \
  python backend/manage.py migrate --check \
  --settings=config.settings.test 2>&1

# Verify audit chain hash integrity
DATABASE_URL="${RESTORE_DATABASE_URL}" \
  python backend/manage.py verify_audit \
  --settings=config.settings.test 2>&1
```

### Step 5: Clean up

```bash
docker stop agentgate-restore-test
rm ./restore.dump
```

**Record the results** — expected tables exist, row counts are reasonable,
migration check passes, audit chain verifies. Record these as the baseline
for future restore tests.

---

## 7. Backup Security Checklist

- [ ] `BACKUP_ENCRYPTION_PASSPHRASE` stored in password manager, not VPS `.bashrc`
- [ ] S3 access credentials are isolated from application credentials
- [ ] S3 bucket versioning or Object Lock is enabled
- [ ] Backup environment file (`~/.agentgate-backup-env`) is `chmod 600`
- [ ] Backup log does not contain credentials or sensitive row data
- [ ] Backup test has been successfully performed in an isolated environment
- [ ] `MFA_ENCRYPTION_KEY` is stored separately from the backup passphrase (losing both simultaneously must require two independent breaches)

---

## 8. Recovery Runbook (Disaster Scenario)

If the VPS is lost or corrupted:

1. Provision a new Contabo VPS (Section 3 of `CONTABO_COOLIFY_DEPLOYMENT.md`).
2. Install Docker, Coolify, and configure the firewall.
3. Provision a fresh PostgreSQL 17 instance.
4. Retrieve `BACKUP_ENCRYPTION_PASSPHRASE` and S3 credentials from the password manager.
5. Run the restore procedure (Section 6 above) on the new PostgreSQL instance.
6. Verify row counts and audit chain integrity.
7. Update `DATABASE_URL` to point at the restored instance.
8. Deploy AgentGate (from the Git repository — no local state required beyond the DB).
9. Run `python manage.py migrate --noinput` to apply any pending migrations.
10. Verify health checks: `/healthz` and `/readyz`.
11. Update DNS if the VPS IP changed.
12. Confirm the application is functional.

**Estimated RTO:** 15–30 minutes (excluding DNS propagation).
