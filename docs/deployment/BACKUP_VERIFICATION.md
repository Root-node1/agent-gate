# AgentGate — Backup Verification

**Branch:** `integration/agentgate-dashboard`
**Status:** Verification plan documented; no restore test executed yet

---

## 1. Restore Verification Plan

A successful backup command alone is not proof of recoverability. The following verification must be performed:

### 1.1 Pre-Restore Checks

| Check | Method | Pass Criteria |
|---|---|---|
| Dump file exists | `ls -lh agentgate-*.dump` | File present, non-zero size |
| Dump size consistent | Compare with 7-day average | Within ±50% of average |
| Checksum matches | `sha256sum -c agentgate-*.dump.sha256` | Checksum OK |
| Encryption key available | Secrets manager lookup | Key retrievable |

### 1.2 Restore Test Steps

1. **Create temporary database** (Neon branch or local PostgreSQL 17):
   ```bash
   # Neon: Create branch from latest restore point in Neon dashboard
   # Local: createdb agentgate_restore_test_$(date +%F)
   ```

2. **Restore dump into temporary database:**
   ```bash
   pg_restore --dbname="$RESTORE_URL" --clean --if-exists agentgate-YYYY-MM-DD.dump
   ```

3. **Verify migration state:**
   ```bash
   DJANGO_SETTINGS_MODULE=config.settings.prod DATABASE_URL="$RESTORE_URL" \
     python manage.py migrate --check
   ```
   Expected: No unapplied migrations.

4. **Verify record counts (presence only):**
   ```bash
   DJANGO_SETTINGS_MODULE=config.settings.prod DATABASE_URL="$RESTORE_URL" \
     python manage.py shell -c "
     from django.db import connection
     with connection.cursor() as cursor:
         for table in ['accounts_user', 'accounts_organization', 'spend_spendrequest',
                       'audit_auditevent', 'procrastinate_jobs']:
             cursor.execute(f'SELECT count(*) FROM {table}')
             print(f'{table}: {cursor.fetchone()[0]}')
     "
   ```

5. **Verify audit-chain integrity:**
   ```bash
   DJANGO_SETTINGS_MODULE=config.settings.prod DATABASE_URL="$RESTORE_URL" \
     python manage.py verify_audit
   ```
   Expected: No audit chain violations.

6. **Run Django checks:**
   ```bash
   DJANGO_SETTINGS_MODULE=config.settings.prod DATABASE_URL="$RESTORE_URL" \
     REDIS_URL="redis://localhost:6379/0" MFA_ENCRYPTION_KEY="..." \
     python manage.py check --deploy
   ```
   Expected: No errors (MFA_ENCRYPTION_KEY warning acceptable).

7. **Run test suite against restored database:**
   ```bash
   TEST_DATABASE_URL="$RESTORE_URL" python manage.py test
   ```
   Expected: All tests pass.

### 1.3 Verification Sign-Off

| Verification | Date | Performed By | Result |
|---|---|---|---|
| Initial restore test | — | — | Not yet performed |
| Weekly restore test (recurring) | — | — | Not yet scheduled |

---

## 2. Last Successful Restore Test

**Status:** Not yet performed.

**Required before team testing begins:**
1. Execute the restore test procedure above against a temporary database.
2. Confirm `verify_audit` passes.
3. Confirm Django checks pass.
4. Record the result in this document.
5. Update `PRESENTATION_READINESS.md` accordingly.

---

## 3. Monitoring and Alerting

| Alert | Condition | Action |
|---|---|---|
| Backup not created | No new dump within 25 hours | Investigate cron/systemd timer |
| Dump size anomaly | Size deviates >50% from 7-day average | Investigate data loss or corruption |
| Restore test failure | `verify_audit` or Django checks fail on restored DB | Investigate before relying on backups |
| Storage near capacity | Backup storage >85% full | Rotate old backups or expand storage |

**Recommended tooling:** Cron + simple script with notification, or dedicated backup service (pgBackRest, WAL-G) for production scale.

---

## 4. Remaining Risks

| Risk | Impact | Mitigation |
|---|---|---|
| No off-server backup storage | VPS loss = data loss | Configure off-server storage (S3, etc.) |
| Encryption key not backed up | Cannot decrypt backups | Store key in separate secrets manager |
| No automated restore testing | Backup may be unusable | Schedule weekly restore tests |
| Neon plan retention unknown | PITR may not cover needed window | Verify Neon plan entitlements |