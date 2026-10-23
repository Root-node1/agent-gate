from unittest import skipUnless

from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from apps.accounts.models import Organization
from apps.audit.models import AuditEvent


@skipUnless(connection.vendor == "postgresql", "the append-only trigger is PostgreSQL-only")
class AuditTriggerTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.event = AuditEvent.record(
            AuditEvent.EventType.DECISION_MADE, organization=self.organization
        )

    def test_raw_update_is_blocked(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE audit_auditevent SET event_type = %s WHERE id = %s",
                    [AuditEvent.EventType.PAYMENT_FAILED, self.event.pk],
                )

    def test_raw_delete_is_blocked(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM audit_auditevent WHERE id = %s", [self.event.pk])
