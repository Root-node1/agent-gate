#!/usr/bin/env bash
# AgentGate database backup script.
#
# Required environment variables (never hardcode here):
#   DATABASE_URL                  — PostgreSQL connection URL
#   BACKUP_ENCRYPTION_PASSPHRASE  — passphrase for AES-256-CBC encryption
#   S3_BUCKET                     — S3-compatible bucket name
#   S3_ENDPOINT_URL               — S3-compatible endpoint URL
#   AWS_ACCESS_KEY_ID             — S3 access key
#   AWS_SECRET_ACCESS_KEY         — S3 secret key
#
# Optional:
#   BACKUP_DIR      — local staging directory (default: /tmp/agentgate_backups)
#   RETENTION_DAYS  — days to keep 6-hourly backups (default: 7)
#
# Usage: ./scripts/backup_database.sh
# Log:   stdout/stderr (redirect to your preferred log destination)
#
# Security:
#   - Unencrypted dump is deleted before upload.
#   - Retention deletion only runs after upload verification.
#   - Script exits non-zero on any failure.
#   - No credentials are logged.
#
# See docs/deployment/BACKUP_AND_DISASTER_RECOVERY.md for full documentation.

set -euo pipefail

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
BACKUP_DIR="${BACKUP_DIR:-/tmp/agentgate_backups}"
DUMP_FILE="${BACKUP_DIR}/agentgate_${TIMESTAMP}.dump"
ENCRYPTED_FILE="${DUMP_FILE}.enc"
S3_BUCKET="${S3_BUCKET:?S3_BUCKET must be set}"
S3_ENDPOINT="${S3_ENDPOINT_URL:?S3_ENDPOINT_URL must be set}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
LOG_TAG="agentgate-backup"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$LOG_TAG] $*"; }

log "=== Backup started: ${TIMESTAMP} ==="

# 1. Create staging directory with restricted permissions
mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

# 2. PostgreSQL logical dump (compressed custom format, compression level 6)
log "Creating PostgreSQL logical dump..."
if ! pg_dump "${DATABASE_URL:?DATABASE_URL must be set}" -Fc -Z 6 -f "${DUMP_FILE}"; then
    log "ERROR: pg_dump failed. Aborting."
    rm -f "${DUMP_FILE}"
    exit 1
fi
DUMP_SIZE=$(du -sh "${DUMP_FILE}" | cut -f1)
log "Dump created: ${DUMP_FILE} (${DUMP_SIZE})"

# 3. Encrypt before upload (AES-256-CBC with PBKDF2, 100000 iterations)
log "Encrypting backup with AES-256-CBC..."
if ! openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
    -in "${DUMP_FILE}" \
    -out "${ENCRYPTED_FILE}" \
    -pass "env:BACKUP_ENCRYPTION_PASSPHRASE"; then
    log "ERROR: Encryption failed. Removing plaintext dump."
    rm -f "${DUMP_FILE}" "${ENCRYPTED_FILE}"
    exit 1
fi

# Remove unencrypted dump immediately after encryption
rm -f "${DUMP_FILE}"
ENC_SIZE=$(du -sh "${ENCRYPTED_FILE}" | cut -f1)
log "Encrypted backup: ${ENCRYPTED_FILE} (${ENC_SIZE})"

# 4. Upload to off-site S3-compatible storage
S3_KEY="db/agentgate_${TIMESTAMP}.dump.enc"
log "Uploading to s3://${S3_BUCKET}/${S3_KEY}..."
if ! aws s3 cp "${ENCRYPTED_FILE}" "s3://${S3_BUCKET}/${S3_KEY}" \
    --endpoint-url "${S3_ENDPOINT}" \
    --no-progress; then
    log "ERROR: S3 upload failed. Local encrypted file retained for retry: ${ENCRYPTED_FILE}"
    exit 1
fi
log "Upload complete."

# 5. Verify upload (object must exist and have non-zero size)
REMOTE_SIZE=$(aws s3 ls "s3://${S3_BUCKET}/${S3_KEY}" \
    --endpoint-url "${S3_ENDPOINT}" \
    | awk '{print $3}' || echo "")
if [ -z "${REMOTE_SIZE}" ] || [ "${REMOTE_SIZE}" -le 0 ]; then
    log "ERROR: Remote object is empty or missing after upload. Manual check required."
    # Do NOT delete the local file — it may be the last good copy.
    exit 1
fi
log "Remote object verified: ${REMOTE_SIZE} bytes."

# 6. Remove local encrypted file (upload and verification succeeded)
rm -f "${ENCRYPTED_FILE}"

# 7. Apply retention: delete remote objects older than RETENTION_DAYS
# This only runs AFTER successful upload verification (step 5 above).
log "Applying retention policy (keeping last ${RETENTION_DAYS} days)..."
if command -v date >/dev/null 2>&1; then
    CUTOFF=$(date -u -d "${RETENTION_DAYS} days ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || \
             date -u -v-"${RETENTION_DAYS}"d +%Y-%m-%dT%H:%M:%SZ)  # macOS fallback
    aws s3 ls "s3://${S3_BUCKET}/db/" --endpoint-url "${S3_ENDPOINT}" \
      | awk '{print $1" "$2" "$4}' \
      | while read -r fdate ftime fkey; do
            FILE_DATETIME="${fdate}T${ftime}Z"
            if [[ "${FILE_DATETIME}" < "${CUTOFF}" ]] && [[ "${fkey}" == agentgate_*.dump.enc ]]; then
                log "Deleting expired backup: ${fkey}"
                aws s3 rm "s3://${S3_BUCKET}/db/${fkey}" --endpoint-url "${S3_ENDPOINT}"
            fi
        done
fi

log "=== Backup completed successfully: ${TIMESTAMP} ==="
