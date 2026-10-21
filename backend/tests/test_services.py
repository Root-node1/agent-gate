from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.policies.models import Policy
from apps.spend import services
from apps.spend.models import SpendRequest


class CountedSpendTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", organization)
        self.policy = Policy.objects.create(agent=self.agent)

    def spend(self, amount_minor, status, decision):
        return SpendRequest.objects.create(
            organization=self.agent.organization,
            agent=self.agent,
            policy=self.policy,
            policy_version=self.policy.version,
            amount_minor=amount_minor,
            currency="USD",
            merchant_ref="acme.com",
            decision=decision,
            status=status,
        )

    def test_only_budget_statuses_count(self):
        self.spend(1_000, SpendRequest.Status.APPROVED, SpendRequest.Decision.ALLOW)
        self.spend(5_000, SpendRequest.Status.PENDING_APPROVAL, SpendRequest.Decision.NEEDS_APPROVAL)
        self.spend(9_000, SpendRequest.Status.DENIED, SpendRequest.Decision.DENY)
        since = timezone.now() - timedelta(days=1)
        self.assertEqual(services.counted_spend(self.agent, "USD", since), Decimal("10.00"))

    def test_counted_spend_is_a_single_query(self):
        for _ in range(3):
            self.spend(1_000, SpendRequest.Status.SUCCEEDED, SpendRequest.Decision.ALLOW)
        since = timezone.now() - timedelta(days=1)
        with self.assertNumQueries(1):
            services.counted_spend(self.agent, "USD", since)
