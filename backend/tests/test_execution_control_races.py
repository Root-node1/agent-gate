import queue
import threading
import time
from decimal import Decimal
from unittest import skipUnless
from uuid import uuid4

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.test import override_settings

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.payees.models import DestinationType
from apps.payments.executors import ExecutionResult
from apps.payments.payouts.models import PayoutReservation, SpendExecutionClaim
from apps.payments.payouts.services import (
    PayoutNotEligible,
    reserve_payout,
)
from apps.payments.services import ExecutionOutcome, execute_spend_request
from apps.policies.models import MerchantRule, Policy
from apps.policies.serializers import PolicyUpdateSerializer
from apps.policies.services import add_merchant_rule, create_policy_update
from apps.spend import pipeline
from apps.spend.models import SpendRequest
from tests.base import PostgresTransactionTestCase


class BlockingFakeExecutor:
    def __init__(self):
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()

    def execute(self, spend_request):
        self.calls += 1
        self.entered.set()
        if not self.release.wait(timeout=10):
            raise TimeoutError("test did not release fake executor")
        return ExecutionResult("FAKE-CONTROL-RACE", "COMPLETED")


@skipUnless(
    connection.vendor == "postgresql",
    "worker/control row-lock races require PostgreSQL",
)
@override_settings(PAYMENTS_EXECUTION_ENABLED=False)
class ExecutionControlRaceTests(PostgresTransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.organization = Organization.objects.create(name=f"race-{uuid4()}")
        self.agent, _ = Agent.create_with_key("worker", self.organization)
        self.policy = Policy.objects.create(
            agent=self.agent,
            daily_budget_minor=1_050,
        )
        self.admin = User.objects.create_user(f"admin-{uuid4()}")
        OrgMembership.objects.create(
            user=self.admin,
            organization=self.organization,
            role=OrgMembership.Role.ADMIN,
        )
        self.spend, _ = pipeline.submit_spend_request(
            self.agent,
            amount=Decimal("10.00"),
            currency="USD",
            merchant="acme.com",
            source_type=SpendRequest.SourceType.TRUSTED,
            destination_type=DestinationType.PAYPAL_EMAIL,
            destination_value="payee@example.test",
            idempotency_key=str(uuid4()),
        )
        self.assertEqual(self.spend.status, SpendRequest.Status.APPROVED)
        self.budget_request, _ = pipeline.submit_spend_request(
            self.agent,
            amount=Decimal("1.00"),
            currency="USD",
            merchant="other.com",
            source_type=SpendRequest.SourceType.TRUSTED,
            destination_type=DestinationType.PAYPAL_EMAIL,
            destination_value="payee@example.test",
            idempotency_key=str(uuid4()),
        )
        self.assertEqual(self.budget_request.status, SpendRequest.Status.DENIED)

    def _block_agent(self):
        agent = Agent.objects.select_for_update().get(pk=self.agent.pk)
        agent.status = Agent.Status.SUSPENDED
        agent.save(update_fields=["status"])

    def _revoke_agent_key(self):
        Agent.objects.get(pk=self.agent.pk).revoke_current_key()

    def _create_denying_policy_version(self):
        serializer = PolicyUpdateSerializer(
            data={
                "expected_version": self.policy.version,
                "per_transaction_cap": Decimal("5.00"),
                "approval_threshold": Decimal("5.00"),
            }
        )
        serializer.is_valid(raise_exception=True)
        create_policy_update(
            user=User.objects.get(pk=self.admin.pk),
            policy_id=self.policy.pk,
            validated=serializer.validated_data,
        )

    def _block_merchant(self):
        add_merchant_rule(
            user=User.objects.get(pk=self.admin.pk),
            policy_id=self.policy.pk,
            validated={
                "expected_version": self.policy.version,
                "merchant_ref": "acme.com",
                "kind": MerchantRule.Kind.BLOCK,
            },
        )

    def _consume_budget(self):
        Agent.objects.select_for_update().get(pk=self.agent.pk)
        request = SpendRequest.objects.select_for_update().get(pk=self.budget_request.pk)
        request.status = SpendRequest.Status.SUCCEEDED
        request.save(update_fields=["status", "updated_at"])

    def _run_control_first(self, mutate, expected_outcome, expected_status):
        locked = threading.Event()
        release_control = threading.Event()
        worker_started = threading.Event()
        worker_pid = {}
        errors = queue.Queue()
        outcome = {}
        executor = BlockingFakeExecutor()

        def control():
            close_old_connections()
            try:
                with transaction.atomic():
                    mutate()
                    locked.set()
                    if not release_control.wait(timeout=10):
                        raise TimeoutError("test did not release control transaction")
            except BaseException as exc:
                errors.put(exc)
                locked.set()
            finally:
                close_old_connections()

        def worker():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    worker_pid["value"] = cursor.fetchone()[0]
                worker_started.set()
                outcome["value"] = execute_spend_request(
                    self.spend.pk,
                    executor=executor,
                )
            except BaseException as exc:
                errors.put(exc)
            finally:
                close_old_connections()

        control_thread = threading.Thread(target=control)
        worker_thread = threading.Thread(target=worker)
        control_thread.start()
        self.assertTrue(locked.wait(timeout=5), "control mutation did not acquire its lock")
        worker_thread.start()
        self.assertTrue(worker_started.wait(timeout=5), "worker did not start")
        try:
            self.assertTrue(
                self._worker_waiting_on_lock(worker_pid["value"]),
                "worker did not wait for the control transaction",
            )
        finally:
            release_control.set()
        control_thread.join(timeout=10)
        worker_thread.join(timeout=10)
        self.assertFalse(control_thread.is_alive(), "control thread did not finish")
        self.assertFalse(worker_thread.is_alive(), "worker thread did not finish")
        self._raise_thread_error(errors)

        self.spend.refresh_from_db()
        self.assertEqual(outcome.get("value"), expected_outcome)
        self.assertEqual(self.spend.status, expected_status)
        self.assertEqual(executor.calls, 0)

    def _run_worker_first(self, mutate, expected_status):
        errors = queue.Queue()
        outcome = {}
        mutation_finished = threading.Event()
        executor = BlockingFakeExecutor()

        def worker():
            close_old_connections()
            try:
                outcome["value"] = execute_spend_request(
                    self.spend.pk,
                    executor=executor,
                )
            except BaseException as exc:
                errors.put(exc)
            finally:
                close_old_connections()

        def control():
            close_old_connections()
            try:
                with transaction.atomic():
                    mutate()
                mutation_finished.set()
            except BaseException as exc:
                errors.put(exc)
                mutation_finished.set()
            finally:
                close_old_connections()

        worker_thread = threading.Thread(target=worker)
        control_thread = threading.Thread(target=control)
        worker_thread.start()
        self.assertTrue(
            executor.entered.wait(timeout=5),
            "worker did not commit EXECUTING and enter the fake executor",
        )
        control_thread.start()
        try:
            self.assertTrue(
                mutation_finished.wait(timeout=5),
                "post-claim control change did not complete while executor was paused",
            )
        finally:
            executor.release.set()
        control_thread.join(timeout=10)
        worker_thread.join(timeout=10)
        self.assertFalse(control_thread.is_alive(), "control thread did not finish")
        self.assertFalse(worker_thread.is_alive(), "worker thread did not finish")
        self._raise_thread_error(errors)

        self.spend.refresh_from_db()
        self.assertEqual(outcome.get("value"), ExecutionOutcome.SUCCEEDED)
        self.assertEqual(self.spend.status, expected_status)
        self.assertEqual(executor.calls, 1)

    @staticmethod
    def _raise_thread_error(errors):
        if not errors.empty():
            raise errors.get()

    @staticmethod
    def _worker_waiting_on_lock(pid):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                    [pid],
                )
                row = cursor.fetchone()
            if row and row[0] == "Lock":
                return True
            time.sleep(0.01)
        return False

    def test_agent_suspension_before_worker_claim_blocks(self):
        self._run_control_first(
            self._block_agent,
            ExecutionOutcome.EXECUTION_BLOCKED,
            SpendRequest.Status.EXECUTION_BLOCKED,
        )
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, Agent.Status.SUSPENDED)

    def test_key_revocation_before_worker_claim_blocks(self):
        self._run_control_first(
            self._revoke_agent_key,
            ExecutionOutcome.EXECUTION_BLOCKED,
            SpendRequest.Status.EXECUTION_BLOCKED,
        )
        self.assertFalse(
            self.agent.api_keys.filter(revoked_at__isnull=True).exists()
        )

    def test_policy_version_before_worker_claim_blocks(self):
        self._run_control_first(
            self._create_denying_policy_version,
            ExecutionOutcome.EXECUTION_BLOCKED,
            SpendRequest.Status.EXECUTION_BLOCKED,
        )
        self.assertEqual(
            Policy.objects.filter(agent=self.agent).order_by("-version").first().version,
            self.policy.version + 1,
        )

    def test_merchant_rule_version_before_worker_claim_blocks(self):
        self._run_control_first(
            self._block_merchant,
            ExecutionOutcome.EXECUTION_BLOCKED,
            SpendRequest.Status.EXECUTION_BLOCKED,
        )
        latest = Policy.objects.filter(agent=self.agent).order_by("-version").first()
        self.assertTrue(
            latest.merchant_rules.filter(
                merchant_ref="acme.com",
                kind=MerchantRule.Kind.BLOCK,
            ).exists()
        )

    def test_budget_status_change_before_worker_claim_blocks(self):
        self._run_control_first(
            self._consume_budget,
            ExecutionOutcome.EXECUTION_BLOCKED,
            SpendRequest.Status.EXECUTION_BLOCKED,
        )
        self.budget_request.refresh_from_db()
        self.assertEqual(self.budget_request.status, SpendRequest.Status.SUCCEEDED)

    def test_agent_suspension_after_worker_claim_does_not_cancel_claim(self):
        self._run_worker_first(
            self._block_agent,
            SpendRequest.Status.SUCCEEDED,
        )
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, Agent.Status.SUSPENDED)

    def test_key_revocation_after_worker_claim_does_not_cancel_claim(self):
        self._run_worker_first(
            self._revoke_agent_key,
            SpendRequest.Status.SUCCEEDED,
        )
        self.assertFalse(
            self.agent.api_keys.filter(revoked_at__isnull=True).exists()
        )

    def test_policy_update_after_worker_claim_does_not_cancel_claim(self):
        self._run_worker_first(
            self._create_denying_policy_version,
            SpendRequest.Status.SUCCEEDED,
        )
        latest = Policy.objects.filter(agent=self.agent).order_by("-version").first()
        self.assertEqual(latest.per_transaction_cap_minor, 500)

    def test_merchant_rule_change_after_worker_claim_does_not_cancel_claim(self):
        self._run_worker_first(
            self._block_merchant,
            SpendRequest.Status.SUCCEEDED,
        )
        latest = Policy.objects.filter(agent=self.agent).order_by("-version").first()
        self.assertTrue(
            latest.merchant_rules.filter(
                merchant_ref="acme.com",
                kind=MerchantRule.Kind.BLOCK,
            ).exists()
        )

    def test_budget_status_change_after_worker_claim_does_not_cancel_claim(self):
        self._run_worker_first(
            self._consume_budget,
            SpendRequest.Status.SUCCEEDED,
        )
        self.budget_request.refresh_from_db()
        self.assertEqual(self.budget_request.status, SpendRequest.Status.SUCCEEDED)

    @override_settings(
        PAYPAL_PAYOUTS_ENABLED="true",
        PAYPAL_CLIENT_ID="test-client-id",
        PAYPAL_CLIENT_SECRET="test-client-secret",
    )
    def test_manual_reservation_claim_blocks_automatic_worker(self):
        Policy.objects.filter(pk=self.policy.pk).update(daily_budget_minor=2_500)
        reservation, replayed = reserve_payout(
            self.organization,
            spend_request_id=self.spend.pk,
            idempotency_key=uuid4(),
            django_settings=settings,
        )

        outcome = execute_spend_request(
            self.spend.pk,
            executor=BlockingFakeExecutor(),
        )

        self.assertFalse(replayed)
        self.assertEqual(outcome, ExecutionOutcome.SKIPPED)
        self.assertEqual(reservation.status, PayoutReservation.Status.RESERVED)
        self.spend.refresh_from_db()
        self.assertEqual(self.spend.status, SpendRequest.Status.APPROVED)
        claim = SpendExecutionClaim.objects.get(spend_request=self.spend)
        self.assertEqual(claim.path, SpendExecutionClaim.Path.MANUAL)
        self.assertEqual(claim.status, SpendExecutionClaim.Status.CLAIMED)
        self.assertEqual(claim.payout_reservation_id, reservation.pk)

    @override_settings(
        PAYPAL_PAYOUTS_ENABLED="true",
        PAYPAL_CLIENT_ID="test-client-id",
        PAYPAL_CLIENT_SECRET="test-client-secret",
    )
    def test_automatic_claim_blocks_manual_reservation(self):
        executor = BlockingFakeExecutor()
        outcome = {}
        errors = queue.Queue()

        def worker():
            close_old_connections()
            try:
                outcome["value"] = execute_spend_request(
                    self.spend.pk,
                    executor=executor,
                )
            except BaseException as exc:
                errors.put(exc)
            finally:
                close_old_connections()

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        self.assertTrue(executor.entered.wait(timeout=5))

        with self.assertRaises(PayoutNotEligible):
            reserve_payout(
                self.organization,
                spend_request_id=self.spend.pk,
                idempotency_key=uuid4(),
                django_settings=settings,
            )

        executor.release.set()
        worker_thread.join(timeout=10)
        self.assertFalse(worker_thread.is_alive())
        self._raise_thread_error(errors)

        self.spend.refresh_from_db()
        claim = SpendExecutionClaim.objects.get(spend_request=self.spend)
        self.assertEqual(outcome["value"], ExecutionOutcome.SUCCEEDED)
        self.assertEqual(executor.calls, 1)
        self.assertEqual(self.spend.status, SpendRequest.Status.SUCCEEDED)
        self.assertEqual(claim.path, SpendExecutionClaim.Path.AUTOMATIC)
        self.assertEqual(claim.status, SpendExecutionClaim.Status.SUCCEEDED)
        self.assertFalse(
            PayoutReservation.objects.filter(spend_request=self.spend).exists()
        )

    def test_two_automatic_workers_make_one_executor_call(self):
        executor = BlockingFakeExecutor()
        outcomes = {}
        errors = queue.Queue()

        def worker(label):
            close_old_connections()
            try:
                outcomes[label] = execute_spend_request(
                    self.spend.pk,
                    executor=executor,
                )
            except BaseException as exc:
                errors.put(exc)
            finally:
                close_old_connections()

        first = threading.Thread(target=worker, args=("first",))
        second = threading.Thread(target=worker, args=("second",))
        first.start()
        self.assertTrue(executor.entered.wait(timeout=5))
        second.start()
        second.join(timeout=10)
        self.assertFalse(second.is_alive())
        executor.release.set()
        first.join(timeout=10)
        self.assertFalse(first.is_alive())
        self._raise_thread_error(errors)

        self.spend.refresh_from_db()
        self.assertCountEqual(
            outcomes.values(),
            [ExecutionOutcome.SUCCEEDED, ExecutionOutcome.SKIPPED],
        )
        self.assertEqual(executor.calls, 1)
        self.assertEqual(self.spend.status, SpendRequest.Status.SUCCEEDED)
        claim = SpendExecutionClaim.objects.get(spend_request=self.spend)
        self.assertEqual(claim.path, SpendExecutionClaim.Path.AUTOMATIC)
        self.assertEqual(claim.status, SpendExecutionClaim.Status.SUCCEEDED)
