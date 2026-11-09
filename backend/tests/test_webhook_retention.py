from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Organization
from apps.audit.models import AuditEvent
from apps.payments.models import WebhookEvent
from apps.payments.retention import purge_processed_webhook_payloads
from apps.payments.tasks import purge_webhook_payloads_periodic


class WebhookRetentionTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.organization = Organization.objects.create(name="acme")

    def make_event(self, event_id, *, processed_at=None, payload=None):
        event = WebhookEvent.objects.create(
            paypal_event_id=event_id,
            event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
            payload=payload or {"provider": "secret-value"},
            signature_verified=True,
        )
        if processed_at is not None:
            WebhookEvent.objects.filter(pk=event.pk).update(processed_at=processed_at)
        event.refresh_from_db()
        return event

    def test_purges_processed_payloads_older_than_the_cutoff(self):
        old = self.make_event(
            "old",
            processed_at=self.now - timedelta(days=31),
        )
        boundary = self.make_event(
            "boundary",
            processed_at=self.now - timedelta(days=30),
        )
        recent = self.make_event(
            "recent",
            processed_at=self.now - timedelta(days=29),
        )
        audit = AuditEvent.record(
            AuditEvent.EventType.WEBHOOK_RECEIVED,
            organization=self.organization,
            actor_id=old.paypal_event_id,
        )

        self.assertEqual(
            purge_processed_webhook_payloads(now=self.now, retention_days=30),
            1,
        )

        old.refresh_from_db()
        boundary.refresh_from_db()
        recent.refresh_from_db()
        self.assertEqual(old.payload, {})
        self.assertEqual(old.payload_purged_at, self.now)
        self.assertEqual(boundary.payload, {"provider": "secret-value"})
        self.assertIsNone(boundary.payload_purged_at)
        self.assertEqual(recent.payload, {"provider": "secret-value"})
        self.assertIsNone(recent.payload_purged_at)
        self.assertTrue(AuditEvent.objects.filter(pk=audit.pk).exists())

    def test_unprocessed_events_are_never_purged(self):
        event = self.make_event(
            "unprocessed",
            processed_at=None,
            payload={"provider": "still-needed"},
        )

        self.assertEqual(
            purge_processed_webhook_payloads(now=self.now, retention_days=30),
            0,
        )

        event.refresh_from_db()
        self.assertEqual(event.payload, {"provider": "still-needed"})
        self.assertIsNone(event.payload_purged_at)

    def test_rerun_is_idempotent_and_logs_only_the_event_id(self):
        event = self.make_event(
            "processed",
            processed_at=self.now - timedelta(days=40),
            payload={"provider": "secret-value"},
        )

        with self.assertLogs("apps.payments.retention", level="INFO") as logs:
            self.assertEqual(
                purge_processed_webhook_payloads(now=self.now, retention_days=30),
                1,
            )
        event.refresh_from_db()
        first_purged_at = event.payload_purged_at
        self.assertIsNotNone(first_purged_at)
        self.assertIn(str(event.pk), "\n".join(logs.output))
        self.assertNotIn("secret-value", "\n".join(logs.output))

        with self.assertNoLogs("apps.payments.retention", level="INFO"):
            self.assertEqual(
                purge_processed_webhook_payloads(now=self.now, retention_days=30),
                0,
            )
        event.refresh_from_db()
        self.assertEqual(event.payload_purged_at, first_purged_at)

    def test_batching_purges_every_eligible_event(self):
        events = [
            self.make_event(
                f"old-{index}",
                processed_at=self.now - timedelta(days=31 + index),
            )
            for index in range(3)
        ]

        self.assertEqual(
            purge_processed_webhook_payloads(
                now=self.now,
                retention_days=30,
                batch_size=1,
            ),
            3,
        )

        for event in events:
            event.refresh_from_db()
            self.assertEqual(event.payload, {})
            self.assertIsNotNone(event.payload_purged_at)

    @override_settings(WEBHOOK_RETENTION_DAYS=30)
    def test_command_supports_dry_run_and_actual_purge(self):
        event = self.make_event(
            "command",
            processed_at=self.now - timedelta(days=31),
        )

        output = StringIO()
        call_command("purge_webhook_payloads", "--dry-run", stdout=output)
        event.refresh_from_db()
        self.assertEqual(event.payload, {"provider": "secret-value"})
        self.assertIn("Would purge payloads for 1", output.getvalue())

        output = StringIO()
        call_command("purge_webhook_payloads", stdout=output)
        event.refresh_from_db()
        self.assertEqual(event.payload, {})
        self.assertIn("Purged payloads for 1", output.getvalue())

    def test_command_rejects_a_zero_day_window(self):
        with self.assertRaises(CommandError):
            call_command("purge_webhook_payloads", "--days", "0", stdout=StringIO())

    @override_settings(WEBHOOK_RETENTION_DAYS=30)
    def test_periodic_task_purges_old_processed_payloads(self):
        event = self.make_event(
            "periodic",
            processed_at=timezone.now() - timedelta(days=31),
        )

        self.assertEqual(purge_webhook_payloads_periodic(timestamp=0), 1)

        event.refresh_from_db()
        self.assertEqual(event.payload, {})
        self.assertIsNotNone(event.payload_purged_at)
