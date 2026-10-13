from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import Agent, hash_key


class CreateAgentCommandTests(TestCase):
    def test_creates_agent_policy_rules_and_prints_key(self):
        out = StringIO()
        call_command(
            "create_agent", "bot",
            "--allow", "https://www.acme.com/x",
            "--block", "evil.com",
            "--cap", "80",
            "--threshold", "40",
            stdout=out,
        )
        agent = Agent.objects.get(name="bot")
        self.assertEqual(agent.policy.per_transaction_cap, Decimal("80"))
        rules = {r.merchant: r.action for r in agent.policy.merchant_rules.all()}
        self.assertEqual(rules, {"acme.com": "allow", "evil.com": "block"})
        raw_key = next(line.split(": ")[-1] for line in out.getvalue().splitlines() if "agk_" in line)
        self.assertEqual(agent.api_key_hash, hash_key(raw_key))

    def test_threshold_above_cap_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command("create_agent", "bot", "--cap", "10", "--threshold", "20", stdout=StringIO())
        self.assertFalse(Agent.objects.exists())

    def test_duplicate_name_is_rejected(self):
        call_command("create_agent", "bot", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("create_agent", "bot", stdout=StringIO())
