-- Restrict the application role on the append-only audit table.
-- Run as the table owner after `manage.py migrate`:
--   psql "$DATABASE_URL" -v app_role=agentgate_app -f deploy/audit-table-grants.sql
-- The role must not own audit_auditevent; owners bypass grants.

REVOKE UPDATE, DELETE, TRUNCATE ON audit_auditevent FROM :app_role;
GRANT SELECT, INSERT ON audit_auditevent TO :app_role;
GRANT USAGE, SELECT ON SEQUENCE audit_auditevent_id_seq TO :app_role;
