"""Security regression tests for webhook financial reconciliation (INT-13L.2)."""

import threading
import uuid
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase, override_settings

from apps.accounts.models import Organization
from apps.audit.models import AuditEvent
from apps.payments.models import CheckoutOrder, WebhookEvent
from apps.payments.payouts.models import PayoutReservation
from apps.payments.payouts.services import reserve_payout, submit_payout
from apps.payments.paypal.client import (
    PayPalClient,
    PayPalRateLimitError,
    PayPalServerError,
    PayPalTimeoutError,
)
from apps.payments.webhook_processing import process_webhook_event
from tests.base import PostgresTransactionTestCase
from tests.test_checkout_capture import (
    _COMPLETED_ORDER,
    PAYPAL_CAPTURE_ID,
    PAYPAL_ORDER_ID,
)
from tests.test_payout_submission import (
    _make_spend_request,
    _mock_paypal_get,
    _mock_paypal_post,
    _success_payload,
)
from tests.test_paypal_webhook_ingestion import (
    WEBHOOK_SETTINGS,
    _mock_response,
)

WEBHOOK_URL = "/v1/webhooks/paypal/"


def _checkout_order(
    org, status=CheckoutOrder.Status.APPROVED, paypal_order_id=PAYPAL_ORDER_ID
):
    return CheckoutOrder.objects.create(
        organization=org,
        amount_minor=1000,
        currency="USD",
        status=status,
        paypal_order_id=paypal_order_id,
    )


def _completed_order(capture_id=PAYPAL_CAPTURE_ID):
    return {
        "id": PAYPAL_ORDER_ID,
        "status": "COMPLETED",
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {"currency_code": "USD", "value": "10.00"},
                "payments": {
                    "captures": [
                        {
                            "id": capture_id,
                            "status": "COMPLETED",
                            "amount": {"currency_code": "USD", "value": "10.00"},
                        }
                    ]
                },
            }
        ],
    }


def _denied_order(capture_id="CAP-DENIED"):
    return {
        "id": PAYPAL_ORDER_ID,
        "status": "COMPLETED",
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {"currency_code": "USD", "value": "10.00"},
                "payments": {
                    "captures": [
                        {
                            "id": capture_id,
                            "status": "DENIED",
                            "amount": {"currency_code": "USD", "value": "10.00"},
                        }
                    ]
                },
            }
        ],
    }


def _mock_get(return_value=None, side_effect=None):
    mock = MagicMock()
    if side_effect is not None:
        mock.side_effect = side_effect
    else:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = return_value
        mock.return_value = resp
    return patch.object(PayPalClient, "get", mock)


def _capture_event(
    capture_id=PAYPAL_CAPTURE_ID,
    order_id=PAYPAL_ORDER_ID,
    amount="10.00",
    currency="USD",
):
    return {
        "id": "EVT-CAPTURE",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": capture_id,
            "amount": {"currency_code": currency, "value": amount},
            "supplementary_data": {"related_ids": {"order_id": order_id}},
        },
    }


@override_settings(**WEBHOOK_SETTINGS)
class CheckoutWebhookSecurityTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="org")
        self.checkout = _checkout_order(self.org)

    def _event(self, payload):
        ev = WebhookEvent.objects.create(
            paypal_event_id="EVT-" + str(uuid.uuid4()),
            event_type="PAYMENT.CAPTURE.COMPLETED",
            payload=payload,
            signature_verified=True,
        )
        return ev

    def test_valid_capture_completed(self):
        ev = self._event(_capture_event())
        with _mock_get(return_value=_completed_order()):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "processed")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.COMPLETED)
        self.assertEqual(self.checkout.paypal_capture_id, PAYPAL_CAPTURE_ID)

    def test_wrong_capture_id(self):
        ev = self._event(_capture_event(capture_id="WRONG-CAPTURE"))
        with _mock_get(return_value=_completed_order()):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_wrong_order_id(self):
        ev = self._event(_capture_event(order_id="WRONG-ORDER"))
        result = process_webhook_event(ev, settings)
        self.assertEqual(result, "unknown_identifier")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_wrong_currency(self):
        ev = self._event(_capture_event(currency="EUR"))
        with _mock_get(return_value=_completed_order()):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_wrong_amount(self):
        ev = self._event(_capture_event(amount="99.00"))
        with _mock_get(return_value=_completed_order()):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_wrong_intent(self):
        wrong_intent_order = dict(_COMPLETED_ORDER)
        wrong_intent_order["intent"] = "AUTHORIZE"
        ev = self._event(_capture_event())
        with _mock_get(return_value=wrong_intent_order):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_get_timeout(self):
        ev = self._event(_capture_event())
        with _mock_get(side_effect=PayPalTimeoutError("timeout")):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_get_429(self):
        ev = self._event(_capture_event())
        with _mock_get(side_effect=PayPalRateLimitError("rl")):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_get_5xx(self):
        ev = self._event(_capture_event())
        with _mock_get(side_effect=PayPalServerError("se")):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_stale_completion_after_failure(self):
        self.checkout.status = CheckoutOrder.Status.DECLINED
        self.checkout.save(update_fields=["status", "updated_at"])
        ev = self._event(_capture_event())
        with _mock_get(return_value=_completed_order()):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)

    def test_no_duplicate_audit(self):
        from django.conf import settings as dj_settings

        ev = self._event(_capture_event())
        with _mock_get(return_value=_completed_order()):
            process_webhook_event(ev, dj_settings)
        ev2 = self._event(_capture_event())
        ev2.paypal_event_id = "EVT-CAPTURE-2"
        ev2.save(update_fields=["paypal_event_id"])
        with _mock_get(return_value=_completed_order()):
            process_webhook_event(ev2, dj_settings)
        # First event processed; second has different event id but same checkout already completed -> already_processed
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type=AuditEvent.EventType.PAYMENT_SUCCEEDED,
                organization=self.org,
            ).count(),
            1,
        )


@override_settings(**WEBHOOK_SETTINGS)
class CaptureDeniedSecurityTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="org2")
        self.checkout = _checkout_order(self.org)

    def _event(self):
        return WebhookEvent.objects.create(
            paypal_event_id="EVT-DENIED-" + str(uuid.uuid4()),
            event_type="PAYMENT.CAPTURE.DENIED",
            payload={
                "id": "EVT-DENIED",
                "event_type": "PAYMENT.CAPTURE.DENIED",
                "resource": {
                    "id": "CAP-DENIED",
                    "supplementary_data": {
                        "related_ids": {"order_id": self.checkout.paypal_order_id}
                    },
                },
            },
            signature_verified=True,
        )

    def test_valid_denied(self):
        ev = self._event()
        with _mock_get(return_value=_denied_order()):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "processed")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)

    def test_wrong_binding(self):
        ev = WebhookEvent.objects.create(
            paypal_event_id="EVT-DENIED-WRONG-" + str(uuid.uuid4()),
            event_type="PAYMENT.CAPTURE.DENIED",
            payload={
                "id": "EVT-DENIED-WRONG",
                "event_type": "PAYMENT.CAPTURE.DENIED",
                "resource": {
                    "id": "CAP-DENIED",
                    "supplementary_data": {"related_ids": {"order_id": "WRONG-ORDER"}},
                },
            },
            signature_verified=True,
        )
        result = process_webhook_event(ev, settings)
        self.assertEqual(result, "unknown_identifier")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_wrong_capture_id(self):
        ev = WebhookEvent.objects.create(
            paypal_event_id="EVT-DENIED-WC-" + str(uuid.uuid4()),
            event_type="PAYMENT.CAPTURE.DENIED",
            payload={
                "id": "EVT-DENIED-WC",
                "event_type": "PAYMENT.CAPTURE.DENIED",
                "resource": {
                    "id": "WRONG-CAP",
                    "supplementary_data": {
                        "related_ids": {"order_id": self.checkout.paypal_order_id}
                    },
                },
            },
            signature_verified=True,
        )
        with _mock_get(return_value=_denied_order()):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_missing_capture_id(self):
        ev = WebhookEvent.objects.create(
            paypal_event_id="EVT-DENIED-MC-" + str(uuid.uuid4()),
            event_type="PAYMENT.CAPTURE.DENIED",
            payload={
                "id": "EVT-DENIED-MC",
                "event_type": "PAYMENT.CAPTURE.DENIED",
                "resource": {
                    "supplementary_data": {
                        "related_ids": {"order_id": self.checkout.paypal_order_id}
                    },
                },
            },
            signature_verified=True,
        )
        result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_provider_status_not_denied(self):
        ev = self._event()
        with _mock_get(return_value=_completed_order()):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_get_timeout(self):
        ev = self._event()
        with _mock_get(side_effect=PayPalTimeoutError("timeout")):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_get_429(self):
        ev = self._event()
        with _mock_get(side_effect=PayPalRateLimitError("rl")):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_get_5xx(self):
        ev = self._event()
        with _mock_get(side_effect=PayPalServerError("se")):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.APPROVED)

    def test_duplicate_delivery(self):
        ev = self._event()
        with _mock_get(return_value=_denied_order()):
            r1 = process_webhook_event(ev, settings)
            r2 = process_webhook_event(ev, settings)
        self.assertEqual(r1, "processed")
        self.assertEqual(r2, "already_processed")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)

    def test_no_duplicate_audit(self):
        ev = self._event()
        with _mock_get(return_value=_denied_order()):
            process_webhook_event(ev, settings)
        ev2 = WebhookEvent.objects.create(
            paypal_event_id="EVT-DENIED-2-" + str(uuid.uuid4()),
            event_type="PAYMENT.CAPTURE.DENIED",
            payload=self._event().payload,
            signature_verified=True,
        )
        with _mock_get(return_value=_denied_order()):
            process_webhook_event(ev2, settings)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type=AuditEvent.EventType.PAYMENT_FAILED,
                organization=self.org,
            ).count(),
            1,
        )

    def test_retry_after_transient_failure(self):
        ev = self._event()
        with _mock_get(side_effect=PayPalTimeoutError("timeout")):
            result1 = process_webhook_event(ev, settings)
        self.assertEqual(result1, "retryable")
        with _mock_get(return_value=_denied_order()):
            result2 = process_webhook_event(ev, settings)
        self.assertEqual(result2, "processed")
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)

    def test_no_capture_post(self):
        from unittest.mock import patch

        with patch.object(
            PayPalClient, "post", side_effect=AssertionError("post called")
        ):
            ev = self._event()
            with _mock_get(return_value=_denied_order()):
                process_webhook_event(ev, settings)


@override_settings(
    PAYPAL_PAYOUTS_ENABLED="true",
    PAYPAL_CLIENT_ID="test-client-id",
    PAYPAL_CLIENT_SECRET="test-client-secret",
    PAYPAL_WEBHOOK_ID="WH-123",
)
class PayoutWebhookSecurityTests(TestCase):
    def setUp(self):
        from apps.agents.models import Agent
        from apps.policies.models import Policy

        self.org = Organization.objects.create(name="payout-org")
        agent = Agent.objects.create(name="agent", organization=self.org)
        policy = Policy.objects.create(agent=agent)
        payee = None
        from apps.payees.models import DestinationType, Payee, fingerprint

        payee = Payee.objects.create(
            organization=self.org,
            merchant_ref="acme.com",
            destination_type=DestinationType.PAYPAL_EMAIL,
            destination_value="payee@example.com",
            destination_fingerprint=fingerprint(
                DestinationType.PAYPAL_EMAIL, "payee@example.com"
            ),
            status=Payee.Status.ACTIVE,
        )
        spend = _make_spend_request(self.org, agent, policy, payee=payee)
        self.reservation, _ = reserve_payout(
            self.org,
            spend_request_id=spend.pk,
            idempotency_key=uuid.uuid4(),
            django_settings=settings,
        )
        # submit to get paypal ids

        response = _mock_response(
            200, _success_payload(status="PENDING", item_status="UNCLAIMED")
        )
        with _mock_paypal_post(return_value=response):
            submit_payout(self.reservation.pk, django_settings=settings)
        self.reservation.refresh_from_db()
        self.batch_id = self.reservation.paypal_payout_batch_id
        self.item_id = self.reservation.paypal_payout_item_id

    def _event(
        self,
        item_id=None,
        batch_id=None,
        sender_batch_id=None,
        event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
    ):
        resource = {
            "payout_item_id": item_id if item_id is not None else self.item_id,
            "payout_batch_id": batch_id if batch_id is not None else self.batch_id,
            "transaction_status": "SUCCESS",
        }
        if sender_batch_id is not None:
            resource["sender_batch_id"] = sender_batch_id
        return WebhookEvent.objects.create(
            paypal_event_id="EVT-PAYOUT-" + str(uuid.uuid4()),
            event_type=event_type,
            payload={"id": "EVT", "event_type": event_type, "resource": resource},
            signature_verified=True,
        )

    def _reconcile_response(self, item_status="SUCCESS"):
        return {
            "batch_header": {
                "payout_batch_id": self.batch_id,
                "batch_status": "SUCCESS",
            },
            "items": [
                {"payout_item_id": self.item_id, "transaction_status": item_status}
            ],
        }

    def test_correct_payout_completes(self):
        ev = self._event()
        with _mock_paypal_get(
            return_value=_mock_response(200, self._reconcile_response("SUCCESS"))
        ):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "processed")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, PayoutReservation.Status.COMPLETED)

    def test_wrong_item_id(self):
        ev = self._event(item_id="WRONG-ITEM")
        result = process_webhook_event(ev, settings)
        self.assertEqual(result, "unknown_identifier")
        self.reservation.refresh_from_db()
        self.assertNotEqual(self.reservation.status, PayoutReservation.Status.COMPLETED)

    def test_wrong_batch_id(self):
        ev = self._event(batch_id="WRONG-BATCH")
        result = process_webhook_event(ev, settings)
        self.assertEqual(result, "unknown_identifier")
        self.reservation.refresh_from_db()
        self.assertNotEqual(self.reservation.status, PayoutReservation.Status.COMPLETED)

    def test_conflicting_sender_batch_id(self):
        ev = self._event(sender_batch_id="conflicting")
        result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.reservation.refresh_from_db()
        self.assertNotEqual(self.reservation.status, PayoutReservation.Status.COMPLETED)

    def test_batch_success_alone_not_completed(self):
        ev = self._event()
        with _mock_paypal_get(
            return_value=_mock_response(200, self._reconcile_response("PENDING"))
        ):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "processed")
        self.reservation.refresh_from_db()
        self.assertEqual(
            self.reservation.status, PayoutReservation.Status.SUBMISSION_PENDING
        )

    def test_provider_get_timeout(self):
        ev = self._event()
        with _mock_paypal_get(exception=PayPalTimeoutError("timeout")):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.reservation.refresh_from_db()
        self.assertNotEqual(self.reservation.status, PayoutReservation.Status.COMPLETED)

    def test_provider_get_429(self):
        ev = self._event()
        with _mock_paypal_get(exception=PayPalRateLimitError("rl")):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.reservation.refresh_from_db()
        self.assertNotEqual(self.reservation.status, PayoutReservation.Status.COMPLETED)

    def test_provider_get_5xx(self):
        ev = self._event()
        with _mock_paypal_get(exception=PayPalServerError("se")):
            result = process_webhook_event(ev, settings)
        self.assertEqual(result, "retryable")
        self.reservation.refresh_from_db()
        self.assertNotEqual(self.reservation.status, PayoutReservation.Status.COMPLETED)

    def test_stale_event_after_terminal(self):
        self.reservation.status = PayoutReservation.Status.FAILED
        self.reservation.save(update_fields=["status", "updated_at"])
        ev = self._event()
        with _mock_paypal_get(
            return_value=_mock_response(200, self._reconcile_response("SUCCESS"))
        ):
            process_webhook_event(ev, settings)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, PayoutReservation.Status.FAILED)

    def test_no_duplicate_audit(self):
        ev = self._event()
        with _mock_paypal_get(
            return_value=_mock_response(200, self._reconcile_response("SUCCESS"))
        ):
            process_webhook_event(ev, settings)
        ev2 = self._event()
        with _mock_paypal_get(
            return_value=_mock_response(200, self._reconcile_response("SUCCESS"))
        ):
            process_webhook_event(ev2, settings)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type=AuditEvent.EventType.PAYMENT_SUCCEEDED,
                spend_request=self.reservation.spend_request,
            ).count(),
            1,
        )

    def test_no_payout_post(self):
        with patch.object(
            PayPalClient, "post", side_effect=AssertionError("post called")
        ):
            ev = self._event()
            with _mock_paypal_get(
                return_value=_mock_response(200, self._reconcile_response("SUCCESS"))
            ):
                process_webhook_event(ev, settings)
        # If no assertion error, post was not called


@override_settings(**WEBHOOK_SETTINGS)
class ConcurrencySecurityTests(PostgresTransactionTestCase):
    def test_concurrent_processing_one_transition(self):
        org = Organization.objects.create(name="conc-org")
        checkout = CheckoutOrder.objects.create(
            organization=org,
            amount_minor=1000,
            currency="USD",
            status=CheckoutOrder.Status.APPROVED,
            paypal_order_id=PAYPAL_ORDER_ID,
        )
        ev = WebhookEvent.objects.create(
            paypal_event_id="EVT-CONC",
            event_type="PAYMENT.CAPTURE.COMPLETED",
            payload=_capture_event(),
            signature_verified=True,
        )
        patcher = _mock_get(return_value=_completed_order())
        patcher.start()
        try:
            results = {}

            def worker(label):
                from django.db import connection as _conn

                _conn.close_if_unusable_or_obsolete()
                try:
                    results[label] = process_webhook_event(ev, settings)
                except Exception as exc:
                    results[label] = exc
                finally:
                    _conn.close_if_unusable_or_obsolete()

            threads = [
                threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            for label, value in results.items():
                self.assertNotIsInstance(value, Exception, f"{label} raised {value!r}")
            checkout.refresh_from_db()
            self.assertEqual(checkout.status, CheckoutOrder.Status.COMPLETED)
            self.assertEqual(
                AuditEvent.objects.filter(
                    event_type=AuditEvent.EventType.PAYMENT_SUCCEEDED,
                    organization=org,
                ).count(),
                1,
            )
        finally:
            patcher.stop()
