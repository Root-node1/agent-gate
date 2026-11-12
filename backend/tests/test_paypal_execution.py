import json
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import httpx
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.approvals import services as approval_services
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
from apps.payees.models import Payee, fingerprint
from apps.payments import dispatch
from apps.payments.checks import check_paypal_configuration
from apps.payments.executors import (
    ExecutionResult,
    FakeExecutor,
    PaymentAmbiguous,
    PaymentNotSent,
    PayPalExecutor,
)
from apps.payments.paypal import (
    PayPalAmbiguousResponse,
    PayPalAuthenticationError,
    PayPalClient,
    PayPalConfigurationError,
    PayPalResponseError,
    PayPalTimeoutError,
    create_payout,
    payout_payload,
)
from apps.payments.services import (
    ExecutionOutcome,
    execute_spend_request,
    terminal_status,
)
from apps.policies.models import Policy
from apps.spend import pipeline
from apps.spend.idempotency import request_hash
from apps.spend.models import SpendRequest


def token_response():
    return httpx.Response(
        200, json={"access_token": "token", "expires_in": 3600}
    )


def payout_response(batch_id="B-1", status="PENDING"):
    return httpx.Response(
        200,
        json={
            "batch_header": {
                "payout_batch_id": batch_id,
                "batch_status": status,
            }
        },
    )


class PayPalClientTests(SimpleTestCase):
    def make_client(self, handler, **kwargs):
        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http_client.close)
        sleeps = []
        client = PayPalClient(
            "client-id",
            "secret",
            http_client=http_client,
            sleep=sleeps.append,
            **kwargs,
        )
        return client, sleeps

    def test_token_is_cached_and_bearer_is_used(self):
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.path == "/v1/oauth2/token":
                return token_response()
            return payout_response()

        client, _ = self.make_client(handler)
        client.post_json("/v1/payments/payouts", body={"x": 1}, request_id="req-1")
        client.post_json("/v1/payments/payouts", body={"x": 2}, request_id="req-2")

        token_calls = [r for r in calls if r.url.path == "/v1/oauth2/token"]
        self.assertEqual(len(token_calls), 1)
        payouts = [r for r in calls if r.url.path == "/v1/payments/payouts"]
        self.assertEqual(len(payouts), 2)
        for request in payouts:
            self.assertEqual(request.headers["authorization"], "Bearer token")
        self.assertEqual(
            [r.headers["paypal-request-id"] for r in payouts],
            ["req-1", "req-2"],
        )

    def test_get_json_uses_the_cached_bearer_token(self):
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.path == "/v1/oauth2/token":
                return token_response()
            return payout_response()

        client, _ = self.make_client(handler)
        payload = client.get_json("/v1/payments/payouts/B-1")

        self.assertEqual(payload["batch_header"]["payout_batch_id"], "B-1")
        request = next(r for r in calls if r.method == "GET")
        self.assertEqual(request.url.path, "/v1/payments/payouts/B-1")
        self.assertEqual(request.headers["authorization"], "Bearer token")

    def test_retryable_status_is_retried_with_backoff(self):
        count = {"payout": 0}

        def handler(request):
            if request.url.path == "/v1/oauth2/token":
                return token_response()
            count["payout"] += 1
            if count["payout"] == 1:
                return httpx.Response(503)
            return payout_response()

        client, sleeps = self.make_client(handler)
        payload = client.post_json(
            "/v1/payments/payouts", body={"x": 1}, request_id="req-1"
        )

        self.assertEqual(count["payout"], 2)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(payload["batch_header"]["payout_batch_id"], "B-1")

    def test_timeout_is_raised_after_retries(self):
        count = {"payout": 0}

        def handler(request):
            if request.url.path == "/v1/oauth2/token":
                return token_response()
            count["payout"] += 1
            raise httpx.TimeoutException("timed out")

        client, sleeps = self.make_client(handler, max_retries=1)
        with self.assertRaises(PayPalTimeoutError):
            client.post_json(
                "/v1/payments/payouts", body={"x": 1}, request_id="req-1"
            )

        self.assertEqual(count["payout"], 2)
        self.assertEqual(len(sleeps), 1)

    def test_rejection_carries_status_and_paypal_code(self):
        def handler(request):
            if request.url.path == "/v1/oauth2/token":
                return token_response()
            return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY"})

        client, _ = self.make_client(handler)
        with self.assertRaises(PayPalResponseError) as raised:
            client.post_json(
                "/v1/payments/payouts", body={"x": 1}, request_id="req-1"
            )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.code, "UNPROCESSABLE_ENTITY")

    def test_live_mode_is_refused_without_explicit_permission(self):
        with self.assertRaises(PayPalConfigurationError):
            PayPalClient("client-id", "secret", mode="live")

    def test_live_mode_is_allowed_when_explicitly_enabled(self):
        client = PayPalClient("client-id", "secret", mode="live", allow_live=True)
        self.addCleanup(client.close)

    def test_token_failure_never_sends_the_payment(self):
        paths = []

        def handler(request):
            paths.append(request.url.path)
            return httpx.Response(401)

        client, _ = self.make_client(handler)
        with self.assertRaises(PayPalAuthenticationError):
            client.post_json(
                "/v1/payments/payouts", body={"x": 1}, request_id="req-1"
            )

        self.assertEqual(paths, ["/v1/oauth2/token"])


def unsaved_spend(**overrides):
    values = {
        "id": uuid4(),
        "amount_minor": 1_234,
        "currency": "USD",
        "merchant_ref": "acme.com",
        "destination_type": "paypal_email",
        "destination_value": "payee@example.com",
        "purpose": "Invoice 7",
    }
    values.update(overrides)
    return SpendRequest(**values)


class PayoutPayloadTests(SimpleTestCase):
    def test_email_payout_uses_minor_units_and_stable_ids(self):
        spend = unsaved_spend()
        payload = payout_payload(spend)

        header = payload["sender_batch_header"]
        item = payload["items"][0]
        self.assertEqual(header["sender_batch_id"], str(spend.id))
        self.assertEqual(item["recipient_type"], "EMAIL")
        self.assertEqual(item["amount"], {"value": "12.34", "currency": "USD"})
        self.assertEqual(item["receiver"], "payee@example.com")
        self.assertEqual(item["sender_item_id"], str(spend.id))

    def test_zero_decimal_currency_has_no_fraction(self):
        spend = unsaved_spend(amount_minor=1_234, currency="JPY")
        self.assertEqual(
            payout_payload(spend)["items"][0]["amount"]["value"], "1234"
        )

    def test_phone_and_paypal_id_recipients_are_supported(self):
        self.assertEqual(
            payout_payload(unsaved_spend(destination_type="phone"))["items"][0][
                "recipient_type"
            ],
            "PHONE",
        )
        self.assertEqual(
            payout_payload(unsaved_spend(destination_type="paypal_id"))["items"][0][
                "recipient_type"
            ],
            "PAYPAL_ID",
        )

    def test_url_destination_is_rejected_before_sending(self):
        with self.assertRaises(PayPalConfigurationError):
            payout_payload(unsaved_spend(destination_type="url"))

    def test_missing_destination_is_rejected(self):
        with self.assertRaises(PayPalConfigurationError):
            payout_payload(unsaved_spend(destination_value=""))

    def test_create_payout_extracts_the_batch(self):
        class StubClient:
            def post_json(self, path, *, body, request_id):
                self.path = path
                self.body = body
                self.request_id = request_id
                return {"batch_header": {"payout_batch_id": "B-1", "batch_status": "PENDING"}}

        spend = unsaved_spend()
        client = StubClient()
        result = create_payout(client, spend)

        self.assertEqual(result.reference, "B-1")
        self.assertEqual(result.status, "PENDING")
        self.assertEqual(client.path, "/v1/payments/payouts")
        self.assertEqual(client.request_id, f"agentgate-{spend.id}")

    def test_missing_batch_id_is_ambiguous(self):
        class StubClient:
            def post_json(self, path, *, body, request_id):
                return {"batch_header": {}}

        with self.assertRaises(PayPalAmbiguousResponse):
            create_payout(StubClient(), unsaved_spend())


class StubPayPalClient:
    def __init__(self, *, response=None, error=None):
        self.response = response
        self.error = error

    def post_json(self, path, *, body, request_id):
        if self.error is not None:
            raise self.error
        return self.response


class PayPalExecutorTests(SimpleTestCase):
    def test_success_maps_to_execution_result(self):
        executor = PayPalExecutor(
            client=StubPayPalClient(
                response={
                    "batch_header": {
                        "payout_batch_id": "B-2",
                        "batch_status": "SUCCESS",
                    }
                }
            )
        )
        result = executor.execute(unsaved_spend())
        self.assertEqual(result.reference, "B-2")
        self.assertEqual(result.status, "SUCCESS")

    def test_rejection_is_not_sent(self):
        executor = PayPalExecutor(
            client=StubPayPalClient(
                error=PayPalResponseError("bad", status_code=422, code="BAD")
            )
        )
        with self.assertRaises(PaymentNotSent):
            executor.execute(unsaved_spend())

    def test_timeout_is_ambiguous(self):
        executor = PayPalExecutor(
            client=StubPayPalClient(error=PayPalTimeoutError("slow"))
        )
        with self.assertRaises(PaymentAmbiguous):
            executor.execute(unsaved_spend())

    def test_unpayable_destination_is_not_sent(self):
        executor = PayPalExecutor(client=StubPayPalClient(response={}))
        with self.assertRaises(PaymentNotSent):
            executor.execute(unsaved_spend(destination_type="url"))

    def test_terminal_status_mapping(self):
        self.assertEqual(terminal_status("COMPLETED"), SpendRequest.Status.SUCCEEDED)
        self.assertEqual(terminal_status("SUCCESS"), SpendRequest.Status.SUCCEEDED)
        self.assertEqual(terminal_status("FAILED"), SpendRequest.Status.FAILED)
        self.assertEqual(terminal_status("DENIED"), SpendRequest.Status.FAILED)
        self.assertIsNone(terminal_status("PENDING"))
        self.assertIsNone(terminal_status(""))


class CountingExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def execute(self, spend_request):
        self.calls += 1
        return self.result


class ExecutionServiceTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="default")
        self.agent, self.raw_key = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)

    def spend(self, status=SpendRequest.Status.APPROVED, **overrides):
        values = {
            "organization": self.organization,
            "agent": self.agent,
            "policy": self.policy,
            "policy_version": self.policy.version,
            "source_type": SpendRequest.SourceType.TRUSTED,
            "amount_minor": 1_000,
            "currency": "USD",
            "merchant_ref": "acme.com",
            "destination_type": "paypal_email",
            "destination_value": "payee@example.com",
            "decision": SpendRequest.Decision.ALLOW,
            "status": status,
        }
        values.update(overrides)
        values["destination_fingerprint"] = (
            fingerprint(values["destination_type"], values["destination_value"])
            if values["destination_type"] and values["destination_value"]
            else ""
        )
        values["request_hash"] = request_hash(
            amount_minor=values["amount_minor"],
            currency=values["currency"],
            merchant_ref=values["merchant_ref"],
            purpose=values.get("purpose", ""),
            source_type=values["source_type"],
            source_ref=values.get("source_ref", ""),
            evidence_excerpt=values.get("evidence_excerpt", ""),
            destination_type=values["destination_type"],
            destination_value=values["destination_value"],
        )
        spend = SpendRequest.objects.create(**values)
        if spend.destination_type:
            Payee.objects.get_or_create(
                organization=self.organization,
                merchant_ref=spend.merchant_ref,
                defaults={
                    "destination_type": spend.destination_type,
                    "destination_value": spend.destination_value,
                    "destination_fingerprint": spend.destination_fingerprint,
                },
            )
        return spend

    def events(self, spend):
        return list(
            AuditEvent.objects.filter(spend_request=spend)
            .order_by("id")
            .values_list("event_type", flat=True)
        )

    def test_success_is_terminal_and_audited(self):
        spend = self.spend()
        outcome = execute_spend_request(
            spend.pk, executor=FakeExecutor("succeed")
        )

        self.assertEqual(outcome, ExecutionOutcome.SUCCEEDED)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.SUCCEEDED)
        self.assertEqual(spend.paypal_status, "COMPLETED")
        self.assertTrue(spend.paypal_reference.startswith("FAKE-"))
        self.assertIsNotNone(spend.executed_at)
        self.assertEqual(
            self.events(spend),
            [
                AuditEvent.EventType.PAYMENT_EXECUTING,
                AuditEvent.EventType.PAYMENT_SUCCEEDED,
            ],
        )

    def test_second_call_does_not_pay_again(self):
        spend = self.spend()
        executor = CountingExecutor(ExecutionResult("B-1", "COMPLETED"))

        first = execute_spend_request(spend.pk, executor=executor)
        second = execute_spend_request(spend.pk, executor=executor)

        self.assertEqual(first, ExecutionOutcome.SUCCEEDED)
        self.assertEqual(second, ExecutionOutcome.SKIPPED)
        self.assertEqual(executor.calls, 1)

    def test_failure_is_terminal_and_audited(self):
        spend = self.spend()
        outcome = execute_spend_request(spend.pk, executor=FakeExecutor("fail"))

        self.assertEqual(outcome, ExecutionOutcome.FAILED)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.FAILED)
        self.assertEqual(spend.paypal_status, "FAILED")
        self.assertEqual(
            self.events(spend),
            [
                AuditEvent.EventType.PAYMENT_EXECUTING,
                AuditEvent.EventType.PAYMENT_FAILED,
            ],
        )

    def test_timeout_leaves_the_request_executing(self):
        spend = self.spend()
        outcome = execute_spend_request(spend.pk, executor=FakeExecutor("timeout"))

        self.assertEqual(outcome, ExecutionOutcome.AMBIGUOUS)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.EXECUTING)
        self.assertIsNone(spend.paypal_reference)
        self.assertEqual(
            self.events(spend), [AuditEvent.EventType.PAYMENT_EXECUTING]
        )

    def test_held_response_keeps_the_reference_and_stays_executing(self):
        spend = self.spend()
        outcome = execute_spend_request(spend.pk, executor=FakeExecutor("held"))

        self.assertEqual(outcome, ExecutionOutcome.EXECUTING)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.EXECUTING)
        self.assertTrue(spend.paypal_reference.startswith("FAKE-"))
        self.assertEqual(spend.paypal_status, "HELD")
        self.assertEqual(
            self.events(spend),
            [
                AuditEvent.EventType.PAYMENT_EXECUTING,
                AuditEvent.EventType.PAYMENT_EXECUTING,
            ],
        )

    def test_not_sent_marks_failed_without_a_reference(self):
        class NotSentExecutor:
            def execute(self, spend_request):
                raise PaymentNotSent("rejected")

        spend = self.spend()
        outcome = execute_spend_request(spend.pk, executor=NotSentExecutor())

        self.assertEqual(outcome, ExecutionOutcome.FAILED)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.FAILED)
        self.assertIsNone(spend.paypal_reference)

    def test_ambiguous_error_leaves_the_request_executing(self):
        class AmbiguousExecutor:
            def execute(self, spend_request):
                raise PaymentAmbiguous("unknown")

        spend = self.spend()
        outcome = execute_spend_request(spend.pk, executor=AmbiguousExecutor())

        self.assertEqual(outcome, ExecutionOutcome.AMBIGUOUS)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.EXECUTING)

    def test_non_approved_request_is_skipped(self):
        spend = self.spend(status=SpendRequest.Status.PENDING_APPROVAL)
        executor = CountingExecutor(ExecutionResult("B-1", "COMPLETED"))

        outcome = execute_spend_request(spend.pk, executor=executor)

        self.assertEqual(outcome, ExecutionOutcome.SKIPPED)
        self.assertEqual(executor.calls, 0)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.PENDING_APPROVAL)

    def assert_execution_blocked(self, spend, expected_reason):
        executor = CountingExecutor(ExecutionResult("B-1", "COMPLETED"))

        outcome = execute_spend_request(spend.pk, executor=executor)

        self.assertEqual(outcome, ExecutionOutcome.EXECUTION_BLOCKED)
        spend.refresh_from_db()
        self.assertEqual(spend.status, SpendRequest.Status.EXECUTION_BLOCKED)
        self.assertEqual(spend.status, "execution_blocked")
        self.assertEqual(executor.calls, 0)
        event = AuditEvent.objects.get(
            spend_request=spend,
            event_type=AuditEvent.EventType.EXECUTION_BLOCKED,
        )
        self.assertEqual(event.event_type, "execution.blocked")
        self.assertIn(expected_reason, event.payload["reason_codes"])
        if (
            self.agent.status == Agent.Status.ACTIVE
            and self.agent.api_keys.filter(revoked_at__isnull=True).exists()
        ):
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
            response = client.get(f"/v1/spend-requests/{spend.pk}/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "execution_blocked")

        repeated = execute_spend_request(spend.pk, executor=executor)

        self.assertEqual(repeated, ExecutionOutcome.SKIPPED)
        self.assertEqual(executor.calls, 0)

    def test_suspended_agent_blocks_execution(self):
        spend = self.spend()
        self.agent.status = Agent.Status.SUSPENDED
        self.agent.save(update_fields=["status"])

        self.assert_execution_blocked(spend, "agent_inactive")

    def test_revoked_agent_key_blocks_execution(self):
        spend = self.spend()
        self.agent.revoke_current_key()

        self.assert_execution_blocked(spend, "agent_unauthorized")

    def test_current_policy_deny_blocks_execution(self):
        spend = self.spend(decision=SpendRequest.Decision.NEEDS_APPROVAL)
        approver = get_user_model().objects.create_user("policy-denial-approver")
        Approval.objects.create(
            organization=self.organization,
            spend_request=spend,
            outcome=Approval.Outcome.APPROVED,
            approver=approver,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
            decided_at=timezone.now(),
        )
        Policy.objects.create(
            agent=self.agent,
            version=self.policy.version + 1,
            per_transaction_cap_minor=500,
            approval_threshold_minor=500,
        )

        self.assert_execution_blocked(spend, "policy_denied")

    def test_new_current_approval_requirement_blocks_without_approval(self):
        spend = self.spend()
        Policy.objects.create(
            agent=self.agent,
            version=self.policy.version + 1,
            approval_threshold_minor=500,
        )

        self.assert_execution_blocked(spend, "approval_required")

    def test_exhausted_current_budget_blocks_execution(self):
        spend = self.spend()
        Policy.objects.create(
            agent=self.agent,
            version=self.policy.version + 1,
            daily_budget_minor=1_500,
        )
        self.spend(status=SpendRequest.Status.SUCCEEDED, amount_minor=1_000)

        self.assert_execution_blocked(spend, "policy_denied")

    def test_changed_payee_destination_blocks_execution(self):
        spend = self.spend()
        payee = Payee.objects.get(
            organization=self.organization, merchant_ref=spend.merchant_ref
        )
        payee.destination_value = "different@example.com"
        payee.destination_fingerprint = fingerprint(
            payee.destination_type, payee.destination_value
        )
        payee.save(update_fields=["destination_value", "destination_fingerprint"])

        self.assert_execution_blocked(spend, "destination_changed")

    def test_new_current_payee_cooldown_blocks_execution(self):
        spend = self.spend()
        payee = Payee.objects.get(
            organization=self.organization, merchant_ref=spend.merchant_ref
        )
        payee.trusted_at = timezone.now()
        payee.save(update_fields=["trusted_at", "updated_at"])
        Policy.objects.create(
            agent=self.agent,
            version=self.policy.version + 1,
            new_payee_cooldown_hours=24,
        )

        self.assert_execution_blocked(spend, "R11_NEW_PAYEE")

    def test_new_payee_approval_requirement_cannot_be_bypassed(self):
        spend = self.spend()
        payee = Payee.objects.get(
            organization=self.organization, merchant_ref=spend.merchant_ref
        )
        payee.first_seen_at = timezone.now() - timezone.timedelta(days=2)
        payee.save(update_fields=["first_seen_at", "updated_at"])
        Policy.objects.create(
            agent=self.agent,
            version=self.policy.version + 1,
            new_payee_cooldown_hours=24,
        )

        self.assert_execution_blocked(spend, "R11_NEW_PAYEE")

    def test_missing_required_approval_blocks_execution(self):
        spend = self.spend(decision=SpendRequest.Decision.NEEDS_APPROVAL)

        self.assert_execution_blocked(spend, "approval_required")

    def test_pending_required_approval_blocks_execution(self):
        spend = self.spend(decision=SpendRequest.Decision.NEEDS_APPROVAL)
        Approval.objects.create(
            organization=self.organization,
            spend_request=spend,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )

        self.assert_execution_blocked(spend, "approval_required")

    def test_approved_request_amount_is_not_counted_twice(self):
        spend = self.spend()
        Policy.objects.create(
            agent=self.agent,
            version=self.policy.version + 1,
            daily_budget_minor=1_000,
        )
        executor = CountingExecutor(ExecutionResult("B-1", "COMPLETED"))

        outcome = execute_spend_request(spend.pk, executor=executor)

        self.assertEqual(outcome, ExecutionOutcome.SUCCEEDED)
        self.assertEqual(executor.calls, 1)

    def test_valid_human_approval_remains_executable(self):
        spend = self.spend(decision=SpendRequest.Decision.NEEDS_APPROVAL)
        approver = get_user_model().objects.create_user("execution-approver")
        Approval.objects.create(
            organization=self.organization,
            spend_request=spend,
            outcome=Approval.Outcome.APPROVED,
            approver=approver,
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
            decided_at=timezone.now(),
        )
        executor = CountingExecutor(ExecutionResult("B-1", "COMPLETED"))

        outcome = execute_spend_request(spend.pk, executor=executor)

        self.assertEqual(outcome, ExecutionOutcome.SUCCEEDED)
        self.assertEqual(executor.calls, 1)

    def test_modified_request_snapshot_blocks_execution(self):
        spend = self.spend()
        spend.amount_minor += 1
        spend.save(update_fields=["amount_minor", "updated_at"])

        self.assert_execution_blocked(spend, "request_snapshot_mismatch")


class DispatchTests(TestCase):
    @override_settings(PAYMENTS_EXECUTION_ENABLED=False)
    def test_disabled_execution_does_not_enqueue(self):
        with patch("apps.payments.tasks.execute_payment") as task:
            self.assertFalse(dispatch.enqueue_execution("request-id"))
        task.configure.assert_not_called()

    @override_settings(PAYMENTS_EXECUTION_ENABLED=True)
    def test_enabled_execution_enqueues_with_a_queueing_lock(self):
        with patch("apps.payments.tasks.execute_payment") as task:
            task.configure.return_value.defer.return_value = 1
            self.assertTrue(dispatch.enqueue_execution("request-id"))

        task.configure.assert_called_once_with(
            queueing_lock="payment:request-id"
        )
        task.configure.return_value.defer.assert_called_once_with("request-id")

    @override_settings(PAYMENTS_EXECUTION_ENABLED=True)
    def test_enqueue_failure_is_logged_and_not_raised(self):
        with patch("apps.payments.tasks.execute_payment") as task:
            task.configure.side_effect = RuntimeError("queue unavailable")
            with self.assertLogs("apps.payments.dispatch", level="ERROR"):
                self.assertFalse(dispatch.enqueue_execution("request-id"))

    def test_schedule_runs_after_commit(self):
        with patch("apps.payments.dispatch.enqueue_execution") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                dispatch.schedule_execution("request-id")
        enqueue.assert_called_once_with("request-id")


class ExecutionTriggerTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)

    def submit(self, amount, source_type=SpendRequest.SourceType.TRUSTED):
        spend_request, _ = pipeline.submit_spend_request(
            self.agent,
            amount=Decimal(amount),
            currency="USD",
            merchant="acme.com",
            source_type=source_type,
        )
        return spend_request

    def test_allow_schedules_execution(self):
        with patch("apps.payments.dispatch.schedule_execution") as schedule:
            spend = self.submit("10.00")

        self.assertEqual(spend.decision, SpendRequest.Decision.ALLOW)
        schedule.assert_called_once_with(spend.pk)

    def test_needs_approval_does_not_schedule_execution(self):
        with patch("apps.payments.dispatch.schedule_execution") as schedule:
            spend = self.submit("75.00")

        self.assertEqual(spend.decision, SpendRequest.Decision.NEEDS_APPROVAL)
        schedule.assert_not_called()

    def test_deny_does_not_schedule_execution(self):
        with patch("apps.payments.dispatch.schedule_execution") as schedule:
            spend = self.submit("200.00")

        self.assertEqual(spend.decision, SpendRequest.Decision.DENY)
        schedule.assert_not_called()

    def test_approval_schedules_execution_after_commit(self):
        from apps.accounts.models import OrgMembership, User

        user = User.objects.create_user("approver")
        OrgMembership.objects.create(
            user=user,
            organization=self.organization,
            role=OrgMembership.Role.APPROVER,
        )
        spend = self.submit("75.00")

        with patch("apps.payments.dispatch.schedule_execution") as schedule:
            approval_services.decide(
                spend.approval.pk, user=user, approve=True
            )

        schedule.assert_called_once_with(spend.pk)


class PayPalChecksTests(SimpleTestCase):
    def test_production_env_rejected_is_an_error(self):
        with override_settings(PAYPAL_ENV="production"):
            errors = check_paypal_configuration(None)
        self.assertIn("payments.E001", [error.id for error in errors])

    def test_checkout_enabled_requires_credentials(self):
        with override_settings(
            PAYPAL_ENV="sandbox",
            PAYPAL_CLIENT_ID="",
            PAYPAL_CLIENT_SECRET="",
            PAYPAL_WEBHOOK_ID="webhook-id",
            PAYPAL_CHECKOUT_ENABLED="true",
            PAYPAL_PAYOUTS_ENABLED="false",
        ):
            errors = check_paypal_configuration(None)
        self.assertIn("payments.E001", [error.id for error in errors])

    def test_valid_sandbox_configuration_passes(self):
        with override_settings(
            PAYPAL_ENV="sandbox",
            PAYPAL_CLIENT_ID="id",
            PAYPAL_CLIENT_SECRET="secret",
            PAYPAL_WEBHOOK_ID="webhook-id",
            PAYPAL_CHECKOUT_ENABLED="true",
            PAYPAL_PAYOUTS_ENABLED="true",
        ):
            errors = check_paypal_configuration(None)
        self.assertEqual(errors, [])

    def test_checkout_enabled_requires_webhook_id(self):
        with override_settings(
            PAYPAL_ENV="sandbox",
            PAYPAL_CLIENT_ID="id",
            PAYPAL_CLIENT_SECRET="secret",
            PAYPAL_WEBHOOK_ID="",
            PAYPAL_CHECKOUT_ENABLED="true",
            PAYPAL_PAYOUTS_ENABLED="false",
        ):
            errors = check_paypal_configuration(None)
        self.assertIn("payments.E001", [error.id for error in errors])

    def test_invalid_boolean_flag_is_an_error(self):
        with override_settings(
            PAYPAL_ENV="sandbox",
            PAYPAL_CLIENT_ID="id",
            PAYPAL_CLIENT_SECRET="secret",
            PAYPAL_WEBHOOK_ID="webhook-id",
            PAYPAL_CHECKOUT_ENABLED="maybe",
            PAYPAL_PAYOUTS_ENABLED="false",
        ):
            errors = check_paypal_configuration(None)
        self.assertIn("payments.E001", [error.id for error in errors])


class PayloadTests(SimpleTestCase):
    def test_payout_body_is_json_serializable(self):
        payload = payout_payload(unsaved_spend())
        self.assertIsInstance(json.dumps(payload), str)
