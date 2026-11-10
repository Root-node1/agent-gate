"""Tests for verified PayPal webhook processing (INT-13L)."""

import json

from django.conf import settings
from django.test import TestCase, override_settings

from apps.payments.models import WebhookEvent
from apps.payments.payouts.models import PayoutReservation
from apps.payments.webhook_processing import process_webhook_event
from tests.test_paypal_webhook_ingestion import (
    WEBHOOK_SETTINGS,
    _event,
    _headers,
    _mock_response,
    _mock_verify,
)

WEBHOOK_URL = "/v1/webhooks/paypal/"


@override_settings(**WEBHOOK_SETTINGS)
class WebhookProcessingTests(TestCase):
    def _ingest(self, event_id="EVT-1", event_type="PAYMENT.CAPTURE.COMPLETED"):
        from django.test import Client

        c = Client()
        data = json.dumps(_event(event_id=event_id, event_type=event_type)).encode()
        headers = {"HTTP_" + k.replace("-", "_"): v for k, v in _headers().items()}
        with _mock_verify(
            return_value=_mock_response(200, {"verification_status": "SUCCESS"})
        ):
            resp = c.post(
                WEBHOOK_URL, data=data, content_type="application/json", **headers
            )
        self.assertEqual(resp.status_code, 200)
        return WebhookEvent.objects.get(paypal_event_id=event_id)

    def test_unverified_event_rejected(self):
        ev = WebhookEvent.objects.create(
            paypal_event_id="UNVERIFIED",
            event_type="PAYMENT.CAPTURE.COMPLETED",
            payload=_event(event_id="UNVERIFIED"),
            signature_verified=False,
        )
        result = process_webhook_event(ev, settings)
        self.assertEqual(result, "unverified")
        ev.refresh_from_db()
        self.assertIsNone(ev.processed_at)

    def test_unsupported_event_ignored(self):
        ev = self._ingest(event_id="EVT-UNSUPPORTED", event_type="FOO.BAR")
        result = process_webhook_event(ev, settings)
        self.assertEqual(result, "ignored")
        ev.refresh_from_db()
        self.assertIsNotNone(ev.processed_at)

    def test_duplicate_event_idempotency(self):
        ev = self._ingest(event_id="EVT-DUP", event_type="FOO.BAR")
        process_webhook_event(ev, settings)
        r2 = process_webhook_event(ev, settings)
        self.assertEqual(r2, "already_processed")

    def test_unknown_identifier(self):
        ev = self._ingest(
            event_id="EVT-UNKNOWN", event_type="PAYMENT.CAPTURE.COMPLETED"
        )
        result = process_webhook_event(ev, settings)
        self.assertEqual(result, "unknown_identifier")
        ev.refresh_from_db()
        self.assertIsNone(ev.processed_at)

    def test_no_payment_submission(self):
        before = PayoutReservation.objects.count()
        ev = self._ingest(
            event_id="EVT-NOSUBMIT", event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED"
        )
        process_webhook_event(ev, settings)
        self.assertEqual(PayoutReservation.objects.count(), before)
