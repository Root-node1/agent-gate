"""Tests for payout submission (INT-13J).

All PayPal HTTP is mocked; no real Sandbox or production calls are made.
"""

import threading
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.conf import settings
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
from apps.payees.models import DestinationType, Payee, fingerprint
from apps.payments.payouts import services as payout_services
from apps.payments.payouts.models import PayoutReservation
from apps.payments.paypal.client import PayPalClient
from apps.policies.models import Policy
from apps.spend.models import SpendRequest
from tests.base import PostgresTransactionTestCase, force_mfa

PAYOUT_SUBMIT_URL = "/v1/payout-reservations/{}/submit/"


def _fingerprint_email(value: str) -> str:
    return fingerprint(DestinationType.PAYPAL_EMAIL, value)


PAYOUT_SETTINGS = {
    "PAYPAL_PAYOUTS_ENABLED": "true",
    "PAYPAL_CLIENT_ID": "test-client-id",
    "PAYPAL_CLIENT_SECRET": "test-client-secret",
}


def _make_spend_request(organization, agent, policy, **overrides):
    values = {
        "organization": organization,
        "agent": agent,
        "policy": policy,
        "policy_version": policy.version,
        "amount_minor": 1000,
        "currency": "USD",
        "merchant_ref": "acme.com",
        "destination_type": DestinationType.PAYPAL_EMAIL,
        "destination_value": "payee@example.com",
        "destination_fingerprint": _fingerprint_email("payee@example.com"),
        "purpose": "test payout",
        "source_type": SpendRequest.SourceType.TRUSTED,
        "decision": SpendRequest.Decision.ALLOW,
        "status": SpendRequest.Status.APPROVED,
    }
    values.update(overrides)
    return SpendRequest.objects.create(**values)


def _mock_response(status_code, json_data, reason="OK"):
    response = MagicMock()
    response.status_code = status_code
    response.reason = reason
    response.json.return_value = json_data
    return response


def _mock_paypal_post(return_value=None, exception=None):
    """Patch PayPalClient.post to return a response or raise."""
    mock = MagicMock()
    if exception is not None:
        mock.side_effect = exception
    else:
        mock.return_value = return_value
    return patch.object(PayPalClient, "post", mock)


def _success_payload(batch_id="BATCH-123", item_id="ITEM-456", status="PENDING"):
    return {
        "batch_header": {
            "payout_batch_id": batch_id,
            "batch_status": status,
            "sender_batch_header": {
                "sender_batch_id": "batch-xyz",
                "email_subject": "Your payout from AgentGate",
            },
        },
        "items": [
            {
                "payout_item_id": item_id,
                "payout_batch_id": batch_id,
                "payout_item": {
                    "recipient_type": "EMAIL",
                    "amount": {"currency": "USD", "value": "10.00"},
                    "receiver": "payee@example.com",
                    "sender_item_id": "item-xyz",
                },
                "transaction_status": "UNCLAIMED",
            },
        ],
    }


class PayoutSubmissionBase(TestCase):
    """Shared fixtures for payout submission tests."""

    def setUp(self):
        self.organization = Organization.objects.create(name="payout-submit-org")
        self.other_org = Organization.objects.create(name="other-org")
        self.agent = Agent.objects.create(
            name="shopper", organization=self.organization
        )
        self.policy = Policy.objects.create(agent=self.agent)
        self.admin = User.objects.create_user("admin")
        OrgMembership.objects.create(
            user=self.admin,
            organization=self.organization,
            role=OrgMembership.Role.ADMIN,
        )
        force_mfa(self.admin)

        self.payee = Payee.objects.create(
            organization=self.organization,
            merchant_ref="acme.com",
            destination_type=DestinationType.PAYPAL_EMAIL,
            destination_value="payee@example.com",
            destination_fingerprint=_fingerprint_email("payee@example.com"),
            status=Payee.Status.ACTIVE,
        )

        self.spend_request = _make_spend_request(
            self.organization, self.agent, self.policy, payee=self.payee
        )

        self.reservation, _ = payout_services.reserve_payout(
            self.organization,
            spend_request_id=self.spend_request.pk,
            idempotency_key=uuid4(),
            django_settings=settings,
        )


@override_settings(**PAYOUT_SETTINGS)
class PayoutSubmissionServiceTests(PayoutSubmissionBase):
    """Service-level submission tests."""

    def _submit(self):
        return payout_services.submit_payout(
            self.reservation.pk, django_settings=settings
        )

    def test_successful_submission(self):
        response = _mock_response(200, _success_payload())
        with _mock_paypal_post(return_value=response):
            result = self._submit()
        self.assertEqual(result.outcome, "submitted")
        self.assertEqual(result.paypal_batch_id, "BATCH-123")
        self.assertEqual(result.paypal_item_id, "ITEM-456")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, PayoutReservation.Status.SUBMITTED)
        self.assertEqual(self.reservation.paypal_payout_batch_id, "BATCH-123")
        self.assertEqual(self.reservation.paypal_payout_item_id, "ITEM-456")

    def test_submission_creates_audit_event(self):
        response = _mock_response(200, _success_payload())
        with _mock_paypal_post(return_value=response):
            self._submit()
        event = AuditEvent.objects.filter(
            event_type=AuditEvent.EventType.PAYMENT_EXECUTING,
            spend_request=self.spend_request,
        ).latest("created_at")
        self.assertEqual(event.organization_id, self.organization.pk)
        self.assertIn("paypal_payout_batch_id", event.payload)

    def test_sender_batch_id_stable_on_retry(self):
        response = _mock_response(200, _success_payload())
        with _mock_paypal_post(return_value=response):
            self._submit()
        self.reservation.refresh_from_db()
        batch_id_1 = self.reservation.sender_batch_id
        self.assertIsNotNone(batch_id_1)

        result2 = self._submit()
        self.reservation.refresh_from_db()
        self.assertEqual(result2.outcome, "already_submitted")
        self.assertEqual(self.reservation.sender_batch_id, batch_id_1)

    def test_recipient_type_email(self):
        captured = {}

        def capturing_post(self, path, *, json=None, request_id=None):
            captured["json"] = json
            captured["request_id"] = request_id
            return _mock_response(200, _success_payload())

        with patch.object(PayPalClient, "post", capturing_post):
            self._submit()
        payload = captured["json"]
        self.assertEqual(payload["sender_batch_header"]["recipient_type"], "EMAIL")
        self.assertEqual(payload["items"][0]["recipient_type"], "EMAIL")
        self.assertEqual(payload["items"][0]["receiver"], "payee@example.com")

    def test_amount_and_currency(self):
        captured = {}

        def capturing_post(self, path, *, json=None, request_id=None):
            captured["json"] = json
            return _mock_response(200, _success_payload())

        with patch.object(PayPalClient, "post", capturing_post):
            self._submit()
        item = captured["json"]["items"][0]
        self.assertEqual(item["amount"]["value"], "10.00")
        self.assertEqual(item["amount"]["currency"], "USD")

    def test_request_id_matches_sender_batch_id(self):
        captured = {}

        def capturing_post(self, path, *, json=None, request_id=None):
            captured["request_id"] = request_id
            return _mock_response(200, _success_payload())

        with patch.object(PayPalClient, "post", capturing_post):
            self._submit()
        self.reservation.refresh_from_db()
        self.assertEqual(captured["request_id"], str(self.reservation.sender_batch_id))

    def test_timeout_keeps_pending(self):
        from apps.payments.paypal.client import PayPalTimeoutError

        with _mock_paypal_post(exception=PayPalTimeoutError("timeout")):
            result = self._submit()
        self.assertEqual(result.outcome, "pending")
        self.reservation.refresh_from_db()
        self.assertEqual(
            self.reservation.status, PayoutReservation.Status.SUBMISSION_PENDING
        )
        self.assertIsNone(self.reservation.paypal_payout_batch_id)

    def test_5xx_keeps_pending(self):

        response = _mock_response(500, {"name": "INTERNAL_SERVER_ERROR"})
        with _mock_paypal_post(return_value=response):
            result = self._submit()
        self.assertEqual(result.outcome, "pending")
        self.reservation.refresh_from_db()
        self.assertEqual(
            self.reservation.status, PayoutReservation.Status.SUBMISSION_PENDING
        )

    def test_429_keeps_pending(self):
        response = _mock_response(429, {"name": "RATE_LIMITED"})
        with _mock_paypal_post(return_value=response):
            result = self._submit()
        self.assertEqual(result.outcome, "pending")

    def test_4xx_marks_failed(self):

        response = _mock_response(403, {"name": "FORBIDDEN", "message": "No access"})
        with _mock_paypal_post(return_value=response):
            result = self._submit()
        self.assertEqual(result.outcome, "failed")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, PayoutReservation.Status.FAILED)

    def test_no_automatic_post_retry(self):
        call_count = 0

        def counting_post(self, path, *, json=None, request_id=None):
            nonlocal call_count
            call_count += 1
            raise PayPalClientError("boom")

        from apps.payments.paypal.client import PayPalClientError

        with patch.object(PayPalClient, "post", counting_post):
            with self.assertRaises(PayPalClientError):
                self._submit()
        self.assertEqual(call_count, 1)

    def test_batch_accepted_not_completed(self):
        """200 with PENDING → SUBMITTED, not COMPLETED."""
        response = _mock_response(200, _success_payload(status="PENDING"))
        with _mock_paypal_post(return_value=response):
            self._submit()
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, PayoutReservation.Status.SUBMITTED)
        self.assertNotEqual(self.reservation.status, PayoutReservation.Status.COMPLETED)
        self.assertFalse(
            SpendRequest.objects.filter(pk=self.spend_request.pk)
            .exclude(status=SpendRequest.Status.APPROVED)
            .exists()
        )

    def test_approved_spend_request_required(self):
        self.spend_request.status = SpendRequest.Status.PENDING_APPROVAL
        self.spend_request.save(update_fields=["status", "updated_at"])
        with self.assertRaises(payout_services.PayoutNotReserved):
            self._submit()

    def test_expired_approval_rejected(self):
        expired = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            decision=SpendRequest.Decision.NEEDS_APPROVAL,
            status=SpendRequest.Status.APPROVED,
        )
        Approval.objects.create(
            organization=self.organization,
            spend_request=expired,
            outcome=Approval.Outcome.APPROVED,
            expires_at=timezone.now() + timedelta(minutes=60),
        )
        expired_reservation, _ = payout_services.reserve_payout(
            self.organization,
            spend_request_id=expired.pk,
            idempotency_key=uuid4(),
            django_settings=settings,
        )
        # Now expire the approval.
        expired.approval.expires_at = timezone.now() - timedelta(seconds=1)
        expired.approval.save(update_fields=["expires_at", "updated_at"])
        with self.assertRaises(payout_services.PayoutNotReserved):
            payout_services.submit_payout(
                expired_reservation.pk, django_settings=settings
            )

    def test_inactive_payee_rejected(self):
        self.payee.status = Payee.Status.ARCHIVED
        self.payee.save(update_fields=["status", "updated_at"])
        with self.assertRaises(payout_services.PayoutNotReserved):
            self._submit()


class PayoutSubmissionViewBase(APITestCase):
    """Shared fixtures for view-level submission tests."""

    def setUp(self):
        self.organization = Organization.objects.create(name="payout-submit-org")
        self.other_org = Organization.objects.create(name="other-org")
        self.admin = self._make_member("admin", OrgMembership.Role.ADMIN)
        self.viewer = self._make_member("viewer", OrgMembership.Role.VIEWER)
        self.agent = Agent.objects.create(
            name="shopper", organization=self.organization
        )
        self.policy = Policy.objects.create(agent=self.agent)
        self.payee = Payee.objects.create(
            organization=self.organization,
            merchant_ref="acme.com",
            destination_type=DestinationType.PAYPAL_EMAIL,
            destination_value="payee@example.com",
            destination_fingerprint=_fingerprint_email("payee@example.com"),
            status=Payee.Status.ACTIVE,
        )
        self.spend_request = _make_spend_request(
            self.organization, self.agent, self.policy, payee=self.payee
        )
        self.reservation, _ = payout_services.reserve_payout(
            self.organization,
            spend_request_id=self.spend_request.pk,
            idempotency_key=uuid4(),
            django_settings=settings,
        )

    def _make_member(self, name, role):
        user = User.objects.create_user(name)
        OrgMembership.objects.create(
            user=user,
            organization=self.organization,
            role=role,
        )
        if role in (OrgMembership.Role.ADMIN, OrgMembership.Role.APPROVER):
            force_mfa(user)
        return user

    def _post_submit(self, user=None, pk=None):
        if user is not None:
            self.client.force_authenticate(user=user)
        target = pk or self.reservation.pk
        return self.client.post(PAYOUT_SUBMIT_URL.format(target), {}, format="json")


@override_settings(**PAYOUT_SETTINGS)
class PayoutSubmissionViewTests(PayoutSubmissionViewBase):
    """View-level submission tests."""

    def test_successful_submission(self):
        response = _mock_response(200, _success_payload())
        with _mock_paypal_post(return_value=response):
            resp = self._post_submit(user=self.admin)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["status"], PayoutReservation.Status.SUBMITTED)
        self.assertEqual(data["paypal_payout_batch_id"], "BATCH-123")

    def test_idempotent_replay(self):
        response = _mock_response(200, _success_payload())
        with _mock_paypal_post(return_value=response):
            resp1 = self._post_submit(user=self.admin)
        self.assertEqual(resp1.status_code, 201)

        resp2 = self._post_submit(user=self.admin)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(
            PayoutReservation.objects.filter(pk=self.reservation.pk).count(), 1
        )

    def test_admin_authorization_required(self):
        response = _mock_response(200, _success_payload())
        with _mock_paypal_post(return_value=response):
            resp = self._post_submit(user=self.viewer)
        self.assertEqual(resp.status_code, 403)

    def test_mfa_enforcement(self):
        no_mfa = User.objects.create_user("no_mfa")
        OrgMembership.objects.create(
            user=no_mfa,
            organization=self.organization,
            role=OrgMembership.Role.ADMIN,
        )
        response = _mock_response(200, _success_payload())
        with _mock_paypal_post(return_value=response):
            resp = self._post_submit(user=no_mfa)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "mfa_enrollment_required")

    def test_organization_isolation(self):
        other_agent = Agent.objects.create(name="other", organization=self.other_org)
        other_policy = Policy.objects.create(agent=other_agent)
        other_payee = Payee.objects.create(
            organization=self.other_org,
            merchant_ref="acme.com",
            destination_type=DestinationType.PAYPAL_EMAIL,
            destination_value="other@example.com",
            destination_fingerprint=_fingerprint_email("other@example.com"),
            status=Payee.Status.ACTIVE,
        )
        other_spend = _make_spend_request(
            self.other_org,
            other_agent,
            other_policy,
            payee=other_payee,
            destination_value="other@example.com",
            destination_fingerprint=_fingerprint_email("other@example.com"),
        )
        other_reservation, _ = payout_services.reserve_payout(
            self.other_org,
            spend_request_id=other_spend.pk,
            idempotency_key=uuid4(),
            django_settings=settings,
        )
        response = _mock_response(200, _success_payload())
        with _mock_paypal_post(return_value=response):
            resp = self._post_submit(user=self.admin, pk=other_reservation.pk)
        self.assertEqual(resp.status_code, 404)

    def test_disabled_payout_feature(self):
        with override_settings(PAYPAL_PAYOUTS_ENABLED="false"):
            resp = self._post_submit(user=self.admin)
        self.assertEqual(resp.status_code, 503)

    def test_missing_credentials(self):
        with override_settings(
            PAYPAL_PAYOUTS_ENABLED="true",
            PAYPAL_CLIENT_ID="",
            PAYPAL_CLIENT_SECRET="",
        ):
            resp = self._post_submit(user=self.admin)
        self.assertEqual(resp.status_code, 503)

    def test_no_sensitive_data_leakage(self):
        response = _mock_response(200, _success_payload())
        with _mock_paypal_post(return_value=response):
            resp = self._post_submit(user=self.admin)
        self.assertEqual(resp.status_code, 201)
        payload = resp.json()
        self.assertNotIn("client_id", str(payload).lower())
        self.assertNotIn("secret", str(payload).lower())
        self.assertNotIn("test-client-id", str(payload))
        self.assertNotIn("test-client-secret", str(payload))


@skipUnless(
    connection.vendor == "postgresql", "row locking is exercised against PostgreSQL"
)
@override_settings(**PAYOUT_SETTINGS)
class PayoutSubmissionConcurrencyTests(PostgresTransactionTestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="payout-submit-conc")
        self.agent = Agent.objects.create(
            name="shopper", organization=self.organization
        )
        self.policy = Policy.objects.create(agent=self.agent)
        self.payee = Payee.objects.create(
            organization=self.organization,
            merchant_ref="acme.com",
            destination_type=DestinationType.PAYPAL_EMAIL,
            destination_value="payee@example.com",
            destination_fingerprint=_fingerprint_email("payee@example.com"),
            status=Payee.Status.ACTIVE,
        )
        self.spend_request = _make_spend_request(
            self.organization, self.agent, self.policy, payee=self.payee
        )
        self.reservation, _ = payout_services.reserve_payout(
            self.organization,
            spend_request_id=self.spend_request.pk,
            idempotency_key=uuid4(),
            django_settings=settings,
        )

    def test_concurrent_submission_single_batch(self):
        """Concurrent submissions to the same reservation yield one batch."""
        response = _mock_response(200, _success_payload())
        patcher = _mock_paypal_post(return_value=response)
        patcher.start()
        try:
            results = {}

            def worker(label):
                from django.db import connection as _conn

                _conn.close_if_unusable_or_obsolete()
                try:
                    results[label] = payout_services.submit_payout(
                        self.reservation.pk, django_settings=settings
                    )
                except Exception as exc:
                    results[label] = exc
                finally:
                    _conn.close_if_unusable_or_obsolete()

            threads = [
                threading.Thread(target=worker, args=(f"worker{i}",)) for i in range(2)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            for label, value in results.items():
                self.assertNotIsInstance(value, Exception, f"{label} raised {value!r}")

            self.reservation.refresh_from_db()
            self.assertEqual(
                self.reservation.status, PayoutReservation.Status.SUBMITTED
            )
            self.assertIsNotNone(self.reservation.sender_batch_id)
        finally:
            patcher.stop()
