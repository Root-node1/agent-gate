"""PostgreSQL tests for the periodic approval-expiration Procrastinate task.

These tests exercise ``expire_approvals_periodic`` end to end: periodic-task
registration, worker execution of overdue / future / already-expired approvals,
idempotency under repeated execution, exactly-once audit emission, and
PostgreSQL connection cleanup.

They use ``PostgresTransactionTestCase`` (not ``TestCase``) because the worker
executes the task on a separate connection and uses ``SELECT FOR UPDATE``; rows
must be visible outside Django's transaction-wrapping test harness, and the
append-only ``audit_auditevent`` table needs trigger-aware teardown.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import connection, connections
from django.utils import timezone
from procrastinate.contrib.django import app

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
from apps.background.tasks import expire_approvals_periodic
from apps.policies.models import Policy
from apps.spend import services
from apps.spend.models import SpendRequest
from tests.base import PostgresTransactionTestCase


class ApprovalExpiryPeriodicTests(PostgresTransactionTestCase):
    """Periodic ``expire_approvals_periodic`` task against PostgreSQL."""

    def setUp(self):
        super().setUp()
        self.organization = Organization.objects.create(name="acme")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        Policy.objects.create(agent=self.agent)
        self.spend_request, _ = services.submit_spend_request(
            self.agent,
            amount=Decimal("75.00"),
            currency="USD",
            merchant="acme.com",
            source_type=SpendRequest.SourceType.TRUSTED,
        )
        self.approval = self.spend_request.approval
        # Start each test from a clean job queue and periodic-defer ledger so
        # the worker's built-in periodic deferrer cannot leak occurrences across
        # tests.
        with connection.cursor() as cursor:
            cursor.execute(
                "TRUNCATE procrastinate_jobs, procrastinate_events, "
                "procrastinate_periodic_defers, procrastinate_workers "
                "RESTART IDENTITY CASCADE"
            )

    def tearDown(self):
        super().tearDown()
        app.close()
        connections.close_all()

    def _defer_now(self):
        expire_approvals_periodic.defer(timestamp=int(timezone.now().timestamp()))

    def _run_worker(self):
        with app.replace_connector(app.connector.get_worker_connector()):
            app.run_worker(
                queues=[expire_approvals_periodic.queue],
                wait=False,
                install_signal_handlers=False,
                listen_notify=False,
            )
        app.close()
        connections.close_all()

    def _expired_audit_count(self):
        return AuditEvent.objects.filter(
            event_type=AuditEvent.EventType.APPROVAL_EXPIRED
        ).count()

    def _pg_session_count(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
            return cursor.fetchone()[0]

    def test_periodic_task_is_registered(self):
        matches = [
            v
            for (name, periodic_id), v in app.periodic_registry.periodic_tasks.items()
            if periodic_id == "approval_expiry"
        ]
        self.assertEqual(len(matches), 1, "expiration task is registered once")
        task = matches[0].task
        self.assertEqual(task.queue, "approvals")
        self.assertEqual(matches[0].cron, "*/1 * * * *")

    def test_overdue_pending_approval_is_expired(self):
        Approval.objects.filter(pk=self.approval.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self._defer_now()
        self._run_worker()

        self.assertEqual(
            Approval.objects.get(pk=self.approval.pk).outcome,
            Approval.Outcome.EXPIRED,
        )
        # Exactly one APPROVAL_EXPIRED event per transitioned approval.
        self.assertEqual(self._expired_audit_count(), 1)

    def test_future_approval_remains_pending(self):
        # Fresh approval expires in the future (Policy default TTL of 60m).
        self._defer_now()
        self._run_worker()

        self.assertEqual(
            Approval.objects.get(pk=self.approval.pk).outcome,
            Approval.Outcome.PENDING,
        )
        self.assertEqual(self._expired_audit_count(), 0)

    def test_already_expired_approval_is_unchanged(self):
        Approval.objects.filter(pk=self.approval.pk).update(
            outcome=Approval.Outcome.EXPIRED,
            expires_at=timezone.now() - timedelta(seconds=1),
            decided_at=timezone.now(),
        )
        self._defer_now()
        self._run_worker()

        self.assertEqual(
            Approval.objects.get(pk=self.approval.pk).outcome,
            Approval.Outcome.EXPIRED,
        )
        self.assertEqual(self._expired_audit_count(), 0)

    def test_repeated_execution_is_idempotent(self):
        Approval.objects.filter(pk=self.approval.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        # First occurrence: transitions the approval.
        self._defer_now()
        self._run_worker()
        self.assertEqual(
            Approval.objects.get(pk=self.approval.pk).outcome,
            Approval.Outcome.EXPIRED,
        )
        self.assertEqual(self._expired_audit_count(), 1)
        # Second occurrence: approval is already expired, no new transition.
        self._defer_now()
        self._run_worker()
        self.assertEqual(
            Approval.objects.get(pk=self.approval.pk).outcome,
            Approval.Outcome.EXPIRED,
        )
        self.assertEqual(self._expired_audit_count(), 1)

    def test_worker_releases_connections(self):
        Approval.objects.filter(pk=self.approval.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self._defer_now()
        self._run_worker()
        # The worker must release every PostgreSQL session before the test
        # database is destroyed; the Django integration's per-task
        # close_old_connections middleware + pool teardown must leave none.
        self.assertEqual(self._pg_session_count(), 0)
