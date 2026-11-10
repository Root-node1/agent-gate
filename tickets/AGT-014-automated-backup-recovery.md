# AGT-014: Automated Backup and Recovery

**Ticket ID:** AGT-014
**Title:** Implement automated backups for Neon PostgreSQL and persistent data
**Objective:** Implement automated encrypted backups for Neon PostgreSQL with isolated restore testing.
**Priority:** High (required before team uses VPS)
**Status:** Not started
**Assigned owner:** Winstone, Isaac supporting database configuration

## Context
All AgentGate application state lives in Neon PostgreSQL. The repository documents backup procedures (`docs/deployment/BACKUP_AND_RESTORE.md`, `docs/deployment/BACKUP_VERIFICATION.md`) but automation is not yet deployed.

## Scope
- Investigate Neon-native backup/PITR capabilities and current plan limitations
- Implement scheduled logical `pg_dump` backups
- Define retention policy (proposed: 30 daily / 90 days weekly / 12 months monthly)
- Implement encryption with `age` or GPG
- Configure secure backup storage (off-server where available)
- Implement backup failure logging
- Perform restore test in isolated database (not over live database)
- Document recovery procedure
- Verify actual backup file can be restored

## Acceptance Criteria
- Scheduled backups running (cron or systemd timer)
- Retention policy defined and implemented
- Encryption configured for backup files
- Secure storage configured (off-server where available)
- Failure logging and alerting
- Restore test performed in isolated database with successful verification
- Recovery procedure documented
- Backup schedule, retention, storage location, encryption method, and last successful restore test recorded

## Dependencies
- AGT-013 (VPS backend deployment must be complete first)

## Files/modules
- `docs/deployment/BACKUP_AND_RESTORE.md`
- `docs/deployment/BACKUP_VERIFICATION.md`
- `backend/config/settings/prod.py` (DATABASE_URL)

## Testing
- Restore dump into temporary database
- `python manage.py migrate --check` against restored database
- `python manage.py verify_audit` against restored database
- Record counts for key tables (`accounts_user`, `accounts_organization`, `spend_spendrequest`, `audit_auditevent`, `procrastinate_jobs`)

## Definition of Done
- Automated backups running with encryption
- Restore test succeeded in isolated database
- Recovery procedure documented
- No database passwords or encryption keys stored in scripts or committed

## Notes
- Do not assume an S3 service is already available
- Do not store database passwords or encryption keys in scripts
- Never commit secrets
- Avoid putting backups in publicly accessible directories
- A successful backup command alone is not proof of recoverability
- Investigate Neon plan retention before designing redundant backup strategy