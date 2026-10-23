from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.agents.keys import hash_key
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.policies.models import Policy


class CreateAgentCommandTests(TestCase):
    def test_creates_agent_policy_rules_and_prints_key(self):
        out = StringIO()
        call_command(
            "create_agent",
            "bot",
            "--allow",
            "https://www.acme.com/x",
            "--block",
            "evil.com",
            "--cap",
            "80",
            "--threshold",
            "40",
            stdout=out,
        )
        agent = Agent.objects.get(name="bot")
        policy = Policy.objects.get(agent=agent)
        self.assertEqual(policy.per_transaction_cap_minor, 8000)
        self.assertEqual(policy.weekly_budget_minor, 200_000)
        rules = {r.merchant_ref: r.kind for r in policy.merchant_rules.all()}
        self.assertEqual(rules, {"acme.com": "allow", "evil.com": "block"})
        raw_key = next(line.split(": ")[-1] for line in out.getvalue().splitlines() if "agk_" in line)
        self.assertEqual(agent.api_keys.get().key_hash, hash_key(raw_key))

    def test_threshold_above_cap_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command("create_agent", "bot", "--cap", "10", "--threshold", "20", stdout=StringIO())
        self.assertFalse(Agent.objects.exists())

    def test_negative_budget_is_rejected(self):
        for flag in ("--daily", "--weekly", "--monthly"):
            with self.subTest(flag=flag):
                with self.assertRaises(CommandError):
                    call_command("create_agent", "bot", flag, "-100", stdout=StringIO())
                self.assertFalse(Agent.objects.exists())

    def test_invalid_currency_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command("create_agent", "bot", "--currency", "ZZZ", stdout=StringIO())
        self.assertFalse(Agent.objects.exists())

    def test_duplicate_name_is_rejected(self):
        call_command("create_agent", "bot", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("create_agent", "bot", stdout=StringIO())

    def test_currency_is_stored_uppercase(self):
        call_command("create_agent", "bot", "--currency", "usd", stdout=StringIO())
        self.assertEqual(Policy.objects.get().currency, "USD")

    def test_weekly_budget_can_be_overridden(self):
        call_command("create_agent", "bot", "--weekly", "1500", stdout=StringIO())
        self.assertEqual(Policy.objects.get().weekly_budget_minor, 150_000)


class SeedDemoCommandTests(TestCase):
    def test_reset_suspends_the_old_agent_and_keeps_history(self):
        call_command("seed_demo", stdout=StringIO())
        first = Agent.objects.get()
        call_command("seed_demo", stdout=StringIO())

        first.refresh_from_db()
        self.assertEqual(first.status, Agent.Status.SUSPENDED)
        self.assertEqual(Agent.objects.filter(status=Agent.Status.ACTIVE).count(), 1)
        self.assertEqual(Policy.objects.count(), 2)
        self.assertEqual(AuditEvent.objects.filter(event_type=AuditEvent.EventType.DEMO_RESET).count(), 2)
        latest = AuditEvent.objects.filter(event_type=AuditEvent.EventType.DEMO_RESET).first()
        self.assertEqual(latest.payload["previous_agent_id"], str(first.pk))
