"""Tests for durable payout reservation (INT-13I).

Service-level and view-level tests run against PostgreSQL via TEST_DATABASE_URL.
The concurrency test is gated on PostgreSQL row locking.
"""

import threading
import uuid
from datetime import timedelta
from unittest import skipUnless

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
from apps.policies.models import Policy
from apps.spend.models import SpendRequest
from tests.base import PostgresTransactionTestCase, force_mfa

PAYOUT_URL = "/v1/payout-reservations/"


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


class PayoutReservationBase(TestCase):
    """Shared fixtures for payout reservation tests."""

    def setUp(self):
        self.organization = Organization.objects.create(name="payout-org")
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
        self.key = uuid.uuid4()


@override_settings(**PAYOUT_SETTINGS)
class PayoutServiceTests(PayoutReservationBase):
    """Service-level reservation tests."""

    def _reserve(self, **overrides):
        return payout_services.reserve_payout(
            self.organization,
            spend_request_id=overrides.pop("spend_request_id", self.spend_request.pk),
            idempotency_key=overrides.pop("idempotency_key", self.key),
            django_settings=settings,
        )

    def test_successful_reservation(self):
        reservation, replayed = self._reserve()
        self.assertFalse(replayed)
        self.assertEqual(reservation.status, PayoutReservation.Status.RESERVED)
        self.assertEqual(reservation.organization_id, self.organization.pk)
        self.assertEqual(reservation.spend_request_id, self.spend_request.pk)
        self.assertEqual(reservation.payee_id, self.payee.pk)
        self.assertEqual(reservation.amount_minor, self.spend_request.amount_minor)
        self.assertEqual(reservation.currency, self.spend_request.currency)
        self.assertEqual(reservation.destination_type, DestinationType.PAYPAL_EMAIL)
        self.assertEqual(reservation.destination_value, "payee@example.com")
        self.assertEqual(
            reservation.destination_fingerprint, _fingerprint_email("payee@example.com")
        )
        self.assertEqual(reservation.idempotency_key, self.key)
        self.assertIsNone(reservation.paypal_payout_batch_id)
        self.assertIsNone(reservation.paypal_payout_item_id)

    def test_approved_spend_request_required(self):
        pending = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            status=SpendRequest.Status.PENDING_APPROVAL,
        )
        with self.assertRaises(payout_services.PayoutNotEligible):
            payout_services.reserve_payout(
                self.organization,
                spend_request_id=pending.pk,
                idempotency_key=self.key,
                django_settings=settings,
            )

    def test_denied_approval_rejected(self):
        denied = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            decision=SpendRequest.Decision.NEEDS_APPROVAL,
            status=SpendRequest.Status.PENDING_APPROVAL,
        )
        Approval.objects.create(
            organization=self.organization,
            spend_request=denied,
            outcome=Approval.Outcome.DENIED,
            expires_at=timezone.now() + timedelta(minutes=60),
        )
        # Simulate the decision having been made (status would be REJECTED, not APPROVED)
        denied.status = SpendRequest.Status.REJECTED
        denied.save(update_fields=["status", "updated_at"])
        with self.assertRaises(payout_services.PayoutNotEligible):
            payout_services.reserve_payout(
                self.organization,
                spend_request_id=denied.pk,
                idempotency_key=self.key,
                django_settings=settings,
            )

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
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        with self.assertRaises(payout_services.PayoutNotEligible):
            payout_services.reserve_payout(
                self.organization,
                spend_request_id=expired.pk,
                idempotency_key=self.key,
                django_settings=settings,
            )

    def test_pending_approval_not_eligible(self):
        pending_approval = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            decision=SpendRequest.Decision.NEEDS_APPROVAL,
            status=SpendRequest.Status.APPROVED,
        )
        Approval.objects.create(
            organization=self.organization,
            spend_request=pending_approval,
            outcome=Approval.Outcome.PENDING,
            expires_at=timezone.now() + timedelta(minutes=60),
        )
        with self.assertRaises(payout_services.PayoutNotEligible):
            payout_services.reserve_payout(
                self.organization,
                spend_request_id=pending_approval.pk,
                idempotency_key=self.key,
                django_settings=settings,
            )

    def test_cross_organization_rejected(self):
        with self.assertRaises(payout_services.PayoutNotEligible):
            payout_services.reserve_payout(
                self.other_org,
                spend_request_id=self.spend_request.pk,
                idempotency_key=self.key,
                django_settings=settings,
            )

    def test_inactive_payee_rejected(self):
        self.payee.status = Payee.Status.ARCHIVED
        self.payee.save(update_fields=["status", "updated_at"])
        with self.assertRaises(payout_services.PayoutNotEligible):
            self._reserve()

    def test_non_paypal_email_destination_rejected(self):
        non_email = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            destination_type=DestinationType.PAYPAL_ID,
            destination_value="paypal-id-123",
            destination_fingerprint=_fingerprint_email("payee@example.com"),
        )
        with self.assertRaises(payout_services.PayoutNotEligible):
            payout_services.reserve_payout(
                self.organization,
                spend_request_id=non_email.pk,
                idempotency_key=self.key,
                django_settings=settings,
            )

    def test_fingerprint_mismatch_rejected(self):
        mismatch = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            destination_fingerprint="deadbeef",
        )
        with self.assertRaises(payout_services.PayoutNotEligible):
            payout_services.reserve_payout(
                self.organization,
                spend_request_id=mismatch.pk,
                idempotency_key=self.key,
                django_settings=settings,
            )

    def test_same_key_idempotent_replay(self):
        reservation1, _ = self._reserve()
        reservation2, replayed = self._reserve()
        self.assertTrue(replayed)
        self.assertEqual(reservation1.pk, reservation2.pk)
        self.assertEqual(
            PayoutReservation.objects.filter(idempotency_key=self.key).count(), 1
        )

    def test_different_key_conflict(self):
        self._reserve()
        different_key = uuid.uuid4()
        with self.assertRaises(payout_services.PayoutAlreadyReserved):
            payout_services.reserve_payout(
                self.organization,
                spend_request_id=self.spend_request.pk,
                idempotency_key=different_key,
                django_settings=settings,
            )

    def test_one_reservation_per_spend_request(self):
        self._reserve()
        other_key = uuid.uuid4()
        with self.assertRaises(payout_services.PayoutAlreadyReserved):
            payout_services.reserve_payout(
                self.organization,
                spend_request_id=self.spend_request.pk,
                idempotency_key=other_key,
                django_settings=settings,
            )

    def test_budget_recheck_denies(self):
        low_budget = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            amount_minor=10000,  # $100.00
        )
        self.policy.daily_budget_minor = 500  # $5.00
        self.policy.save(update_fields=["daily_budget_minor", "updated_at"])
        with self.assertRaises(payout_services.PayoutNotEligible):
            payout_services.reserve_payout(
                self.organization,
                spend_request_id=low_budget.pk,
                idempotency_key=self.key,
                django_settings=settings,
            )

    def test_audit_event_recorded(self):
        self._reserve()
        event = AuditEvent.objects.get(
            event_type=AuditEvent.EventType.PAYMENT_RESERVED,
            spend_request=self.spend_request,
        )
        self.assertEqual(event.organization_id, self.organization.pk)
        self.assertEqual(event.agent_id, self.agent.pk)
        self.assertEqual(event.actor_type, AuditEvent.ActorType.USER)

    def test_amount_immutable(self):
        reservation, _ = self._reserve()
        reservation.amount_minor = 9999
        with self.assertRaises(ValueError):
            reservation.save()

    def test_currency_immutable(self):
        reservation, _ = self._reserve()
        reservation.currency = "EUR"
        with self.assertRaises(ValueError):
            reservation.save()

    def test_destination_immutable(self):
        reservation, _ = self._reserve()
        reservation.destination_value = "changed@example.com"
        with self.assertRaises(ValueError):
            reservation.save()


class PayoutViewBase(APITestCase):
    """Shared fixtures for view-level payout tests."""

    def setUp(self):
        self.organization = Organization.objects.create(name="payout-org")
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


@override_settings(**PAYOUT_SETTINGS)
class PayoutViewTests(PayoutViewBase):
    """View-level reservation tests."""

    def _post(self, user=None, **overrides):
        if user is not None:
            self.client.force_authenticate(user=user)
        body = {
            "spend_request": str(self.spend_request.pk),
            "idempotency_key": str(uuid.uuid4()),
        }
        body.update(overrides)
        return self.client.post(PAYOUT_URL, body, format="json")

    def test_successful_reservation(self):
        response = self._post(user=self.admin)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], PayoutReservation.Status.RESERVED)
        self.assertEqual(data["spend_request"], str(self.spend_request.pk))
        self.assertEqual(data["amount"], "10.00")
        self.assertEqual(data["currency"], "USD")
        self.assertEqual(data["destination_type"], DestinationType.PAYPAL_EMAIL)
        self.assertEqual(data["destination_value"], "payee@example.com")

    def test_idempotent_replay(self):
        key = str(uuid.uuid4())
        response1 = self._post(user=self.admin, idempotency_key=key)
        self.assertEqual(response1.status_code, 201)
        response2 = self._post(user=self.admin, idempotency_key=key)
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2["Idempotent-Replayed"], "true")
        self.assertEqual(
            PayoutReservation.objects.filter(spend_request=self.spend_request).count(),
            1,
        )

    def test_different_key_conflict(self):
        self._post(user=self.admin, idempotency_key=str(uuid.uuid4()))
        response = self._post(user=self.admin, idempotency_key=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 409)

    def test_approved_spend_request_required(self):
        pending = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            status=SpendRequest.Status.PENDING_APPROVAL,
        )
        response = self._post(
            user=self.admin,
            spend_request=str(pending.pk),
            idempotency_key=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 422)

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
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        response = self._post(
            user=self.admin,
            spend_request=str(expired.pk),
            idempotency_key=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 422)

    def test_denied_approval_rejected(self):
        denied = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            decision=SpendRequest.Decision.NEEDS_APPROVAL,
            status=SpendRequest.Status.REJECTED,
        )
        Approval.objects.create(
            organization=self.organization,
            spend_request=denied,
            outcome=Approval.Outcome.DENIED,
            expires_at=timezone.now() + timedelta(minutes=60),
        )
        response = self._post(
            user=self.admin,
            spend_request=str(denied.pk),
            idempotency_key=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 422)

    def test_cross_organization_rejected(self):
        other_agent = Agent.objects.create(name="other", organization=self.other_org)
        other_policy = Policy.objects.create(agent=other_agent)
        other_spend = _make_spend_request(
            self.other_org,
            other_agent,
            other_policy,
            payee=Payee.objects.create(
                organization=self.other_org,
                merchant_ref="other.com",
                destination_type=DestinationType.PAYPAL_EMAIL,
                destination_value="other@example.com",
                destination_fingerprint=_fingerprint_email("other@example.com"),
                status=Payee.Status.ACTIVE,
            ),
        )
        response = self._post(
            user=self.admin,
            spend_request=str(other_spend.pk),
            idempotency_key=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 422)

    def test_unauthorized_role_rejected(self):
        response = self._post(user=self.viewer)
        self.assertEqual(response.status_code, 403)

    def test_mfa_enforcement(self):
        no_mfa = User.objects.create_user("no_mfa")
        OrgMembership.objects.create(
            user=no_mfa,
            organization=self.organization,
            role=OrgMembership.Role.ADMIN,
        )
        response = self._post(user=no_mfa)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "mfa_enrollment_required")

    def test_disabled_payout_feature(self):
        with override_settings(PAYPAL_PAYOUTS_ENABLED="false"):
            response = self._post(user=self.admin)
            self.assertEqual(response.status_code, 503)

    def test_missing_credentials(self):
        with override_settings(
            PAYPAL_PAYOUTS_ENABLED="true",
            PAYPAL_CLIENT_ID="",
            PAYPAL_CLIENT_SECRET="",
        ):
            response = self._post(user=self.admin)
            self.assertEqual(response.status_code, 503)

    def test_inactive_payee_rejected(self):
        self.payee.status = Payee.Status.ARCHIVED
        self.payee.save(update_fields=["status", "updated_at"])
        response = self._post(user=self.admin)
        self.assertEqual(response.status_code, 422)

    def test_invalid_destination_type_rejected(self):
        self.spend_request.destination_type = DestinationType.PAYPAL_ID
        self.spend_request.save(update_fields=["destination_type", "updated_at"])
        response = self._post(user=self.admin)
        self.assertEqual(response.status_code, 422)

    def test_no_sensitive_data_leakage(self):
        response = self._post(user=self.admin)
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertNotIn("client_id", str(payload).lower())
        self.assertNotIn("secret", str(payload).lower())
        self.assertNotIn("test-client-id", str(payload))
        self.assertNotIn("test-client-secret", str(payload))

    def test_no_client_override_of_amount(self):
        response = self._post(
            user=self.admin,
            amount="9999.00",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["details"]["amount"], "Unknown field.")


@skipUnless(
    connection.vendor == "postgresql", "row locking is exercised against PostgreSQL"
)
class PayoutConcurrencyTests(PostgresTransactionTestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="payout-concurrency")
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
        self.key = uuid.uuid4()

    def _reserve(self):
        return payout_services.reserve_payout(
            self.organization,
            spend_request_id=self.spend_request.pk,
            idempotency_key=self.key,
            django_settings=settings,
        )

    @override_settings(**PAYOUT_SETTINGS)
    def test_concurrent_same_key_single_reservation(self):
        barrier = threading.Barrier(2)
        results = {}

        def worker(label):
            from django.db import connection as _conn

            _conn.close_if_unusable_or_obsolete()
            try:
                barrier.wait(timeout=10)
                results[label] = payout_services.reserve_payout(
                    self.organization,
                    spend_request_id=self.spend_request.pk,
                    idempotency_key=self.key,
                    django_settings=settings,
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

        reservation_count = PayoutReservation.objects.filter(
            spend_request=self.spend_request
        ).count()
        self.assertEqual(reservation_count, 1)
        reservation = PayoutReservation.objects.get(spend_request=self.spend_request)
        self.assertEqual(reservation.idempotency_key, self.key)

    @override_settings(**PAYOUT_SETTINGS)
    def test_concurrent_different_spend_requests_same_budget(self):
        """Two approved SpendRequests for the same agent reserve concurrently."""
        key2 = uuid.uuid4()
        spend_request2 = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            amount_minor=500,  # $5.00 each, well within any reasonable budget
        )
        results = {}

        def worker(label, sr_id, key):
            from django.db import connection as _conn

            _conn.close_if_unusable_or_obsolete()
            try:
                results[label] = payout_services.reserve_payout(
                    self.organization,
                    spend_request_id=sr_id,
                    idempotency_key=key,
                    django_settings=settings,
                )
            except Exception as exc:
                results[label] = exc
            finally:
                _conn.close_if_unusable_or_obsolete()

        threads = [
            threading.Thread(
                target=worker, args=("worker1", self.spend_request.pk, self.key)
            ),
            threading.Thread(target=worker, args=("worker2", spend_request2.pk, key2)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for label, value in results.items():
            self.assertNotIsInstance(value, Exception, f"{label} raised {value!r}")
            reservation, replayed = value
            self.assertFalse(replayed)
            self.assertEqual(reservation.status, PayoutReservation.Status.RESERVED)

        self.assertEqual(
            PayoutReservation.objects.filter(
                spend_request__in=[self.spend_request, spend_request2]
            ).count(),
            2,
        )

    @override_settings(**PAYOUT_SETTINGS)
    def test_reservation_rejects_pending_approval(self):
        """A SpendRequest whose approval is still PENDING cannot reserve."""
        pending_approval = _make_spend_request(
            self.organization,
            self.agent,
            self.policy,
            payee=self.payee,
            decision=SpendRequest.Decision.NEEDS_APPROVAL,
            status=SpendRequest.Status.APPROVED,
        )
        Approval.objects.create(
            organization=self.organization,
            spend_request=pending_approval,
            outcome=Approval.Outcome.PENDING,
            expires_at=timezone.now() + timedelta(minutes=60),
        )
        with self.assertRaises(payout_services.PayoutNotEligible):
            payout_services.reserve_payout(
                self.organization,
                spend_request_id=pending_approval.pk,
                idempotency_key=self.key,
                django_settings=settings,
            )

    @override_settings(**PAYOUT_SETTINGS)
    def test_reservation_does_not_mark_executed(self):
        """Reservation must not change SpendRequest status to EXECUTING/SUCCEEDED."""
        self._reserve()
        self.spend_request.refresh_from_db()
        self.assertEqual(self.spend_request.status, SpendRequest.Status.APPROVED)
        self.assertIsNone(self.spend_request.executed_at)
