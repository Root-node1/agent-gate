from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from procrastinate.contrib.django import app

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.payments.paypal import PayoutResult, PayPalTransientError, get_payout_batch
from apps.payments.reconciliation import reconcile_payments
from apps.policies.models import Policy
from apps.spend.models import SpendRequest


class StubClient:
    def __init__(self, response=None):
        self.response = response
        self.paths = []
        self.closed = False

    def get_json(self, path):
        self.paths.append(path)
        return self.response

    def close(self):
        self.closed = True


def batch_response(batch_id="B-1", status="SUCCESS"):
    return {"batch_header": {"payout_batch_id": batch_id, "batch_status": status}}


class GetPayoutBatchTests(SimpleTestCase):
    def test_fetches_the_batch_by_reference(self):
        client = StubClient(batch_response())
        result = get_payout_batch(client, "B-1")

        self.assertEqual(result, PayoutResult(reference="B-1", status="SUCCESS"))
        self.assertEqual(client.paths, ["/v1/payments/payouts/B-1"])

    def test_empty_reference_is_rejected(self):
        from apps.payments.paypal import PayPalConfigurationError

        with self.assertRaises(PayPalConfigurationError):
            get_payout_batch(StubClient(), "")


@override_settings(PAYMENT_EXECUTOR="paypal")
class ReconciliationTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)

    def spend(self, *, reference="B-1", status=SpendRequest.Status.EXECUTING, age=10):
        spend = SpendRequest.objects.create(
            organization=self.organization,
            agent=self.agent,
            policy=self.policy,
            policy_version=self.policy.version,
            amount_minor=1_000,
            currency="USD",
            merchant_ref="acme.com",
            destination_type="paypal_email",
            destination_value="payee@example.com",
            decision=SpendRequest.Decision.ALLOW,
            status=status,
            paypal_reference=reference,
            paypal_status="PENDING" if reference else "",
        )
        SpendRequest.objects.filter(pk=spend.pk).update(
            updated_at=timezone.now() - timedelta(minutes=age)
        )
        return spend

    def run_reconciliation(self, result=None, *, client=None, **kwargs):
        client = client or StubClient()
        with patch(
            "apps.payments.reconciliation.build_paypal_client",
            return_value=client,
        ):
            with patch(
                "apps.payments.reconciliation.get_payout_batch",
                return_value=result,
            ):
                return reconcile_payments(**kwargs), client

    def events(self, spend):
        return list(
            AuditEvent.objects.filter(spend_request=spend)
            .order_by("id")
            .values_list("event_type", flat=True)
        )

    def test_terminal_success_is_applied_and_audited(self):
        spend = self.spend()
        summary, client = self.run_reconciliation(
            PayoutResult(reference="B-1", status="SUCCESS")
        )

        self.assertEqual(summary.succeeded, 1)
        self.assertEqual(summary.checked, 1)
        self.assertTrue(client.closed)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.SUCCEEDED)
        self.assertEqual(spend.paypal_status, "SUCCESS")
        self.assertIsNotNone(spend.executed_at)
        self.assertEqual(
            self.events(spend), [AuditEvent.EventType.PAYMENT_SUCCEEDED]
        )

    def test_terminal_failure_is_applied(self):
        spend = self.spend()
        summary, _ = self.run_reconciliation(
            PayoutResult(reference="B-1", status="DENIED")
        )

        self.assertEqual(summary.failed, 1)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.FAILED)
        self.assertEqual(
            self.events(spend), [AuditEvent.EventType.PAYMENT_FAILED]
        )

    def test_pending_result_keeps_the_payment_executing(self):
        spend = self.spend()
        SpendRequest.objects.filter(pk=spend.pk).update(paypal_status="")
        summary, _ = self.run_reconciliation(
            PayoutResult(reference="B-1", status="PENDING")
        )

        self.assertEqual(summary.still_executing, 1)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.EXECUTING)
        self.assertEqual(spend.paypal_status, "PENDING")
        self.assertEqual(
            self.events(spend), [AuditEvent.EventType.PAYMENT_EXECUTING]
        )

    def test_second_pass_is_throttled_after_a_pending_result(self):
        spend = self.spend()
        self.run_reconciliation(PayoutResult(reference="B-1", status="PENDING"))

        summary, client = self.run_reconciliation(
            PayoutResult(reference="B-1", status="PENDING")
        )

        self.assertEqual(summary.candidates, 0)
        self.assertEqual(client.paths, [])
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.EXECUTING)

    def test_payment_without_reference_is_reported_only(self):
        spend = self.spend(reference=None)
        summary, client = self.run_reconciliation(
            PayoutResult(reference="B-1", status="SUCCESS")
        )

        self.assertEqual(summary.candidates, 0)
        self.assertEqual(summary.unreferenced, 1)
        self.assertEqual(client.paths, [])
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.EXECUTING)

    def test_recent_payment_is_not_checked(self):
        self.spend(age=0)
        summary, client = self.run_reconciliation(
            PayoutResult(reference="B-1", status="SUCCESS")
        )

        self.assertEqual(summary.candidates, 0)
        self.assertEqual(client.paths, [])

    def test_provider_error_leaves_the_payment_executing(self):
        spend = self.spend()
        with patch(
            "apps.payments.reconciliation.build_paypal_client",
            return_value=StubClient(),
        ):
            with patch(
                "apps.payments.reconciliation.get_payout_batch",
                side_effect=PayPalTransientError("unavailable"),
            ):
                summary = reconcile_payments()

        self.assertEqual(summary.errors, 1)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.EXECUTING)

    def test_dry_run_does_not_call_paypal(self):
        self.spend()
        with patch(
            "apps.payments.reconciliation.build_paypal_client",
            side_effect=AssertionError("must not build a client"),
        ):
            summary = reconcile_payments(dry_run=True)

        self.assertTrue(summary.dry_run)
        self.assertEqual(summary.candidates, 1)
        self.assertEqual(summary.checked, 0)

    def test_blank_reference_is_treated_as_unreferenced(self):
        spend = self.spend()
        SpendRequest.objects.filter(pk=spend.pk).update(paypal_reference="")

        summary, client = self.run_reconciliation(
            PayoutResult(reference="B-1", status="SUCCESS")
        )

        self.assertEqual(summary.unreferenced, 1)
        self.assertEqual(client.paths, [])

    @override_settings(PAYMENT_EXECUTOR="fake")
    def test_non_paypal_executor_is_skipped(self):
        self.spend()
        with patch(
            "apps.payments.reconciliation.build_paypal_client",
            side_effect=AssertionError("must not build a client"),
        ):
            summary = reconcile_payments()

        self.assertEqual(summary.skipped_reason, "executor_not_paypal")
        self.assertEqual(summary.checked, 0)


class ReconciliationTaskRegistrationTests(SimpleTestCase):
    def test_periodic_task_is_registered_on_the_payments_queue(self):
        matches = [
            value
            for (name, periodic_id), value in app.periodic_registry.periodic_tasks.items()
            if periodic_id == "payment_reconciliation"
        ]

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].task.queue, "payments")
        self.assertEqual(matches[0].cron, "*/5 * * * *")
