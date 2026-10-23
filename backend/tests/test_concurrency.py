from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import skipUnless
from uuid import uuid4

from django.db import close_old_connections, connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.approvals import services as approval_services
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
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


@skipUnless(connection.vendor == "postgresql", "row locking is exercised against PostgreSQL")
class PolicyLockOrderTests(PostgresTransactionTestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        Policy.objects.create(agent=self.agent)

    def test_submit_locks_agent_then_policy(self):
        with CaptureQueriesContext(connection) as queries:
            services.submit_spend_request(
                self.agent,
                amount=Decimal("10.00"),
                currency="USD",
                merchant="acme.com",
                source_type=SpendRequest.SourceType.TRUSTED,
                idempotency_key=str(uuid4()),
            )

        locked_tables = [
            query["sql"]
            for query in queries.captured_queries
            if "FOR UPDATE" in query["sql"]
        ]
        self.assertGreaterEqual(len(locked_tables), 2)
        self.assertIn("agents_agent", locked_tables[0])
        self.assertIn("policies_policy", locked_tables[1])


@skipUnless(connection.vendor == "postgresql", "row locking is exercised against PostgreSQL")
class VelocityLockTests(PostgresTransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        Policy.objects.create(agent=self.agent, velocity_max_count=5)

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

    def test_parallel_requests_respect_the_velocity_limit(self):
        with ThreadPoolExecutor(max_workers=20) as pool:
            outcomes = list(pool.map(lambda _: self.worker(), range(20)))

        self.assertEqual(outcomes.count(SpendRequest.Decision.ALLOW), 5)
        self.assertEqual(outcomes.count(SpendRequest.Decision.NEEDS_APPROVAL), 15)
        counted = SpendRequest.objects.filter(status__in=SpendRequest.BUDGET_STATUSES).count()
        self.assertEqual(counted, 5)


@skipUnless(connection.vendor == "postgresql", "row locking is exercised against PostgreSQL")
class ApprovalLockTests(PostgresTransactionTestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        Policy.objects.create(agent=self.agent)
        self.approver = User.objects.create_user("approver")
        OrgMembership.objects.create(
            user=self.approver,
            organization=self.organization,
            role=OrgMembership.Role.APPROVER,
        )
        self.spend_request, _ = services.submit_spend_request(
            self.agent,
            amount=Decimal("75.00"),
            currency="USD",
            merchant="acme.com",
            source_type=SpendRequest.SourceType.TRUSTED,
            idempotency_key=str(uuid4()),
        )

    def worker(self, _):
        close_old_connections()
        try:
            approval_services.decide(
                self.spend_request.approval.pk, user=self.approver, approve=True
            )
            return "ok"
        finally:
            close_old_connections()

    def test_parallel_approvals_write_one_event_and_stay_approved(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(self.worker, range(8)))

        self.assertEqual(outcomes, ["ok"] * 8)
        self.assertEqual(
            Approval.objects.get(pk=self.spend_request.approval.pk).outcome,
            Approval.Outcome.APPROVED,
        )
        self.spend_request.refresh_from_db()
        self.assertEqual(self.spend_request.status, SpendRequest.Status.APPROVED)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type=AuditEvent.EventType.APPROVAL_APPROVED
            ).count(),
            1,
        )
