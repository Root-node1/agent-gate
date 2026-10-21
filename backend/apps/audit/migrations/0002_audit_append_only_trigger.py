"""Block direct mutation of audit rows at the database layer on PostgreSQL."""

from django.db import migrations

FUNCTION = """
CREATE OR REPLACE FUNCTION audit_auditevent_deny_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditevent is append-only';
END;
$$ LANGUAGE plpgsql;
"""

UPDATE_DELETE_TRIGGER = """
CREATE TRIGGER audit_auditevent_no_update_delete
BEFORE UPDATE OR DELETE ON audit_auditevent
FOR EACH ROW EXECUTE FUNCTION audit_auditevent_deny_mutation();
"""

TRUNCATE_TRIGGER = """
CREATE TRIGGER audit_auditevent_no_truncate
BEFORE TRUNCATE ON audit_auditevent
FOR EACH STATEMENT EXECUTE FUNCTION audit_auditevent_deny_mutation();
"""


def create_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FUNCTION)
    schema_editor.execute(UPDATE_DELETE_TRIGGER)
    schema_editor.execute(TRUNCATE_TRIGGER)


def drop_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS audit_auditevent_no_update_delete ON audit_auditevent;")
    schema_editor.execute("DROP TRIGGER IF EXISTS audit_auditevent_no_truncate ON audit_auditevent;")
    schema_editor.execute("DROP FUNCTION IF EXISTS audit_auditevent_deny_mutation();")


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_guards, drop_guards),
    ]
