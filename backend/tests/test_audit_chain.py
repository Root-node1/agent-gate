from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from unittest import skipUnless
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.test import TestCase

from apps.accounts.models import Organization
from apps.audit.chain import GENESIS_HASH, canonical_payload, event_hash
from apps.audit.models import AuditEvent
from tests.base import PostgresTransactionTestCase


class AuditChainTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")

    def record(self, **payload):
        return AuditEvent.record(
            AuditEvent.EventType.DECISION_MADE,
            organization=self.organization,
            **payload,
        )

    def test_first_event_starts_at_genesis(self):
        event = self.record(amount="10.00")
        self.assertEqual(event.prev_hash, GENESIS_HASH)
        self.assertEqual(len(event.hash), 64)

    def test_events_form_a_chain(self):
        first = self.record(amount="10.00")
        second = self.record(amount="20.00")
        self.assertEqual(second.prev_hash, first.hash)
        self.assertNotEqual(second.hash, first.hash)

    def test_hash_is_stable_after_reading_back(self):
        event = self.record(amount="10.00", extra={"nested": [1, True, None]})
        stored = AuditEvent.objects.get(pk=event.pk)
        expected = event_hash(
            prev_hash=stored.prev_hash,
            created_at=stored.created_at,
            event_type=stored.event_type,
            actor_type=stored.actor_type,
            actor_id=stored.actor_id,
            organization_id=stored.organization_id,
            agent_id=stored.agent_id,
            spend_request_id=stored.spend_request_id,
            payload=stored.payload,
        )
        self.assertEqual(stored.hash, expected)

    def test_payload_is_canonicalized_without_floats(self):
        event = self.record(
            amount=Decimal("12.30"),
            when=datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc),
        )
        self.assertEqual(event.payload["amount"], "12.30")
        self.assertEqual(event.payload["when"], "2026-01-02T03:04:05.123456+00:00")

    def test_float_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            canonical_payload({"amount": 1.5})

    def test_created_at_is_utc_with_microseconds(self):
        event = self.record()
        self.assertEqual(event.created_at.tzinfo, timezone.utc)

    def test_verifier_accepts_a_clean_chain(self):
        self.record(amount="10.00")
        self.record(amount="20.00")
        out = StringIO()
        call_command("verify_audit", stdout=out)
        self.assertIn("2 event(s)", out.getvalue())

    @skipUnless(connection.vendor == "sqlite", "the PostgreSQL trigger blocks this tampering")
    def test_verifier_detects_a_modified_payload(self):
        event = self.record(amount="10.00")
        AuditEvent.objects.filter(pk=event.pk).update(payload={"amount": "99.00"})
        with self.assertRaises(CommandError):
            call_command("verify_audit", stdout=StringIO())


@skipUnless(connection.vendor == "postgresql", "the chain lock is exercised against PostgreSQL")
class AuditChainConcurrencyTests(PostgresTransactionTestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")

    def worker(self):
        close_old_connections()
        try:
            return AuditEvent.record(
                AuditEvent.EventType.REQUEST_RECEIVED,
                organization=self.organization,
                nonce=str(uuid4()),
            )
        finally:
            close_old_connections()

    def test_parallel_events_keep_one_chain(self):
        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(lambda _: self.worker(), range(20)))
        out = StringIO()
        call_command("verify_audit", stdout=out)
        self.assertIn("20 event(s)", out.getvalue())
