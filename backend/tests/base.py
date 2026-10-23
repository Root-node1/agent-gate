from django.db import connection
from django.test import TransactionTestCase

AUDIT_TABLE = "audit_auditevent"


class PostgresTransactionTestCase(TransactionTestCase):
    """Transaction test case that can flush the append-only audit table."""

    def _audit_triggers(self):
        if connection.vendor != "postgresql":
            return []
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tgname FROM pg_trigger WHERE tgrelid = to_regclass(%s) AND NOT tgisinternal",
                [AUDIT_TABLE],
            )
            return [row[0] for row in cursor.fetchall()]

    def _fixture_teardown(self):
        triggers = self._audit_triggers()
        for trigger in triggers:
            with connection.cursor() as cursor:
                cursor.execute(f"ALTER TABLE {AUDIT_TABLE} DISABLE TRIGGER {trigger}")
        try:
            super()._fixture_teardown()
        finally:
            for trigger in triggers:
                with connection.cursor() as cursor:
                    cursor.execute(f"ALTER TABLE {AUDIT_TABLE} ENABLE TRIGGER {trigger}")
