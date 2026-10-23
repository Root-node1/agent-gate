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


class WindowUsageTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", organization)
        self.policy = Policy.objects.create(agent=self.agent)

    def spend(
        self,
        amount_minor,
        *,
        status=SpendRequest.Status.APPROVED,
        decision=SpendRequest.Decision.ALLOW,
        merchant_ref="acme.com",
        currency="USD",
        created_at=None,
    ):
        spend = SpendRequest.objects.create(
            organization=self.agent.organization,
            agent=self.agent,
            policy=self.policy,
            policy_version=self.policy.version,
            amount_minor=amount_minor,
            currency=currency,
            merchant_ref=merchant_ref,
            decision=decision,
            status=status,
        )
        if created_at is not None:
            SpendRequest.objects.filter(pk=spend.pk).update(created_at=created_at)
        return spend

    def test_counts_only_budget_consuming_requests_for_merchant_in_window(self):
        now = timezone.now()
        self.spend(1_000, status=SpendRequest.Status.APPROVED)
        self.spend(500, status=SpendRequest.Status.EXECUTING)
        self.spend(700, merchant_ref="other.example", status=SpendRequest.Status.SUCCEEDED)
        self.spend(
            900,
            status=SpendRequest.Status.DENIED,
            decision=SpendRequest.Decision.DENY,
        )
        self.spend(
            300,
            status=SpendRequest.Status.PENDING_APPROVAL,
            decision=SpendRequest.Decision.NEEDS_APPROVAL,
        )
        self.spend(
            800,
            status=SpendRequest.Status.APPROVED,
            created_at=now - timedelta(hours=2),
        )
        self.spend(1_100, currency="EUR", status=SpendRequest.Status.APPROVED)

        count, amount = services.window_usage(
            self.agent, "USD", "acme.com", now - timedelta(hours=1)
        )
        self.assertEqual(count, 3)
        self.assertEqual(amount, Decimal("15.00"))

    def test_window_usage_is_a_single_query(self):
        for _ in range(3):
            self.spend(1_000)
        since = timezone.now() - timedelta(hours=1)
        with self.assertNumQueries(1):
            services.window_usage(self.agent, "USD", "acme.com", since)
