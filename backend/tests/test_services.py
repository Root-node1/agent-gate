from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

import engine
from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.policies.models import MerchantRule, Policy
from apps.spend import services
from apps.spend.models import SpendRequest


class BuildLimitsMerchantModeTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", organization)

    def decide_against(self, policy, merchant):
        return engine.evaluate(
            engine.SpendInput(
                amount=Decimal("10"),
                currency="USD",
                merchant=merchant,
                source=engine.SOURCE_TRUSTED,
            ),
            services.build_limits(policy),
            engine.Spent(today=Decimal("0"), this_month=Decimal("0")),
        )

    def test_policy_version_change_switches_merchant_behavior(self):
        blocklist_policy = Policy.objects.create(
            agent=self.agent,
            version=1,
            merchant_mode=Policy.MerchantMode.BLOCKLIST,
        )
        MerchantRule.objects.create(
            policy=blocklist_policy,
            merchant_ref="acme.com",
            kind=MerchantRule.Kind.ALLOW,
        )
        self.assertEqual(self.decide_against(blocklist_policy, "other.com").outcome, engine.ALLOW)

        allowlist_policy = Policy.objects.create(
            agent=self.agent,
            version=2,
            merchant_mode=Policy.MerchantMode.ALLOWLIST_ONLY,
        )
        MerchantRule.objects.create(
            policy=allowlist_policy,
            merchant_ref="acme.com",
            kind=MerchantRule.Kind.ALLOW,
        )
        decision = self.decide_against(allowlist_policy, "other.com")
        self.assertEqual(decision.outcome, engine.DENY)
        self.assertIn("R04_MERCHANT_ALLOW", decision.matched_rules)


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


class BudgetPeriodTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", organization)
        self.policy = Policy.objects.create(
            agent=self.agent, currency="USD", timezone="Asia/Tokyo"
        )

    def spend(self, created_at, amount_minor):
        spend = SpendRequest.objects.create(
            organization=self.agent.organization,
            agent=self.agent,
            policy=self.policy,
            policy_version=self.policy.version,
            amount_minor=amount_minor,
            currency="USD",
            merchant_ref="acme.com",
            decision=SpendRequest.Decision.ALLOW,
            status=SpendRequest.Status.APPROVED,
        )
        SpendRequest.objects.filter(pk=spend.pk).update(created_at=created_at)

    def spent(self, now):
        return services.build_spent(
            self.agent, self.policy, "USD", "acme.com", now=now
        )

    def test_usage_changes_at_local_day_week_and_month_boundaries(self):
        now = datetime(2026, 1, 14, 15, 30, tzinfo=datetime_timezone.utc)
        day_start = datetime(2026, 1, 14, 15, 0, tzinfo=datetime_timezone.utc)
        week_start = datetime(2026, 1, 11, 15, 0, tzinfo=datetime_timezone.utc)
        month_start = datetime(2025, 12, 31, 15, 0, tzinfo=datetime_timezone.utc)

        self.assertEqual(
            services.budget_period_starts(self.policy, now),
            (day_start, week_start, month_start),
        )

        self.spend(day_start - timedelta(seconds=1), 100)
        self.spend(day_start, 200)
        self.spend(week_start - timedelta(seconds=1), 400)
        self.spend(week_start, 800)
        self.spend(month_start - timedelta(seconds=1), 1_600)
        self.spend(month_start, 3_200)

        spent = self.spent(now)
        self.assertEqual(spent.today, Decimal("2.00"))
        self.assertEqual(spent.this_week, Decimal("11.00"))
        self.assertEqual(spent.this_month, Decimal("47.00"))

    def test_changing_only_policy_timezone_changes_the_window(self):
        now = datetime(2026, 1, 14, 15, 30, tzinfo=datetime_timezone.utc)
        self.spend(datetime(2026, 1, 14, 14, 59, 59, tzinfo=datetime_timezone.utc), 100)
        self.spend(datetime(2026, 1, 14, 15, 0, tzinfo=datetime_timezone.utc), 200)
        self.spend(datetime(2026, 1, 11, 14, 59, 59, tzinfo=datetime_timezone.utc), 400)
        self.spend(datetime(2026, 1, 11, 15, 0, tzinfo=datetime_timezone.utc), 800)

        tokyo = self.spent(now)
        self.assertEqual(tokyo.today, Decimal("2.00"))
        self.assertEqual(tokyo.this_week, Decimal("11.00"))

        self.policy.timezone = "UTC"
        self.policy.save(update_fields=["timezone"])

        utc = self.spent(now)
        self.assertEqual(utc.today, Decimal("3.00"))
        self.assertEqual(utc.this_week, Decimal("3.00"))
        self.assertEqual(utc.this_month, Decimal("15.00"))

    def test_dst_transition_day_uses_the_correct_utc_cutoffs(self):
        self.policy.timezone = "America/New_York"
        self.policy.save(update_fields=["timezone"])
        now = datetime(2026, 3, 8, 20, 0, tzinfo=datetime_timezone.utc)
        day_start = datetime(2026, 3, 8, 5, 0, tzinfo=datetime_timezone.utc)
        week_start = datetime(2026, 3, 2, 5, 0, tzinfo=datetime_timezone.utc)
        month_start = datetime(2026, 3, 1, 5, 0, tzinfo=datetime_timezone.utc)

        self.assertEqual(
            services.budget_period_starts(self.policy, now),
            (day_start, week_start, month_start),
        )

        self.spend(day_start - timedelta(seconds=1), 100)
        self.spend(day_start, 200)
        self.spend(week_start - timedelta(seconds=1), 400)
        self.spend(week_start, 800)
        self.spend(month_start - timedelta(seconds=1), 1_600)
        self.spend(month_start, 3_200)

        spent = self.spent(now)
        self.assertEqual(spent.today, Decimal("2.00"))
        self.assertEqual(spent.this_week, Decimal("11.00"))
        self.assertEqual(spent.this_month, Decimal("47.00"))
