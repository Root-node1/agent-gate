from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import skipUnless
from uuid import uuid4

from django.db import close_old_connections, connection

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.policies.models import Policy
from apps.spend import services
from apps.spend.models import SpendRequest
from tests.base import PostgresTransactionTestCase


@skipUnless(connection.vendor == "postgresql", "row locking is exercised against PostgreSQL")
class BudgetLockTests(PostgresTransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        Policy.objects.create(agent=self.agent, daily_budget_minor=10_000)

    def worker(self):
        close_old_connections()
        try:
            return services.submit_spend_request(
                self.agent,
                amount=Decimal("10.00"),
                currency="USD",
                merchant="acme.com",
                source_type=SpendRequest.SourceType.TRUSTED,
                idempotency_key=str(uuid4()),
            )[0].decision
        finally:
            close_old_connections()

    def test_parallel_requests_never_overspend(self):
        with ThreadPoolExecutor(max_workers=20) as pool:
            outcomes = list(pool.map(lambda _: self.worker(), range(20)))

        self.assertEqual(outcomes.count(SpendRequest.Decision.ALLOW), 10)
        self.assertEqual(outcomes.count(SpendRequest.Decision.DENY), 10)
        total = sum(
            SpendRequest.objects.filter(
                status__in=SpendRequest.BUDGET_STATUSES
            ).values_list("amount_minor", flat=True)
        )
        self.assertEqual(total, 10_000)
