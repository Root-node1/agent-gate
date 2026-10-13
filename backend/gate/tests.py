from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Agent, AuditEvent, MerchantRule, Policy, hash_key


class HealthTests(TestCase):
    def test_health_returns_ok(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class AgentTests(TestCase):
    def test_create_with_key_stores_only_the_hash(self):
        agent, raw_key = Agent.create_with_key("shopper")
        self.assertTrue(raw_key.startswith("agk_"))
        self.assertEqual(agent.api_key_hash, hash_key(raw_key))
        self.assertNotEqual(agent.api_key_hash, raw_key)
        self.assertEqual(agent.api_key_prefix, raw_key[:8])


class PolicyTests(TestCase):
    def test_threshold_cannot_exceed_cap(self):
        agent, _ = Agent.create_with_key("a")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Policy.objects.create(
                agent=agent,
                per_transaction_cap=Decimal("10.00"),
                approval_threshold=Decimal("20.00"),
            )

    def test_merchant_unique_per_policy(self):
        agent, _ = Agent.create_with_key("b")
        policy = Policy.objects.create(agent=agent)
        MerchantRule.objects.create(policy=policy, merchant="acme.com", action="allow")
        with self.assertRaises(IntegrityError), transaction.atomic():
            MerchantRule.objects.create(policy=policy, merchant="acme.com", action="block")


class AuditEventTests(TestCase):
    def test_record_creates_event(self):
        event = AuditEvent.record("test.event", detail="hello")
        self.assertEqual(event.payload, {"detail": "hello"})

    def test_cannot_modify_or_delete(self):
        event = AuditEvent.record("test.event")
        event.event_type = "changed"
        with self.assertRaises(PermissionError):
            event.save()
        with self.assertRaises(PermissionError):
            event.delete()
