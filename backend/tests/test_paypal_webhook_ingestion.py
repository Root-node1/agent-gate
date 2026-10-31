"""Tests for PayPal webhook ingestion (INT-13K)."""

import threading
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.payments.models import WebhookEvent
from apps.payments.paypal.client import PayPalClient
from tests.base import PostgresTransactionTestCase

WEBHOOK_URL = "/v1/webhooks/paypal/"

WEBHOOK_SETTINGS = {
    "PAYPAL_PAYOUTS_ENABLED": "true",
    "PAYPAL_CLIENT_ID": "test-client-id",
    "PAYPAL_CLIENT_SECRET": "test-client-secret",
    "PAYPAL_WEBHOOK_ID": "WH-123",
}


def _headers():
    return {
        "PAYPAL-TRANSMISSION-ID": "tx-1",
        "PAYPAL-TRANSMISSION-TIME": "2026-01-01T00:00:00Z",
        "PAYPAL-TRANSMISSION-SIG": "sig",
        "PAYPAL-CERT-URL": "https://example.com/cert",
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    }


def _event(event_id="EVT-1", event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED"):
    return {"id": event_id, "event_type": event_type, "resource": {"x": 1}}


def _mock_response(status_code=200, json_data=None):
    response = MagicMock()
    response.status_code = status_code
    response.reason = "OK"
    response.json.return_value = json_data if json_data is not None else {}
    return response


def _mock_verify(return_value=None, exception=None):
    mock = MagicMock()
    if exception is not None:
        mock.side_effect = exception
    else:
        mock.return_value = return_value
    return patch.object(PayPalClient, "post", mock)


@override_settings(**WEBHOOK_SETTINGS)
class PayPalWebhookIngestionTests(TestCase):
    def _post(self, body=None, headers=None, content_type="application/json"):
        payload = body if body is not None else _event()
        import json

        data = json.dumps(payload).encode()
        return self.client.post(
            WEBHOOK_URL,
            data=data,
            content_type=content_type,
            **{
                "HTTP_" + k.replace("-", "_"): v
                for k, v in (headers or _headers()).items()
            },
        )

    def test_valid_verified_webhook(self):
        response_obj = _mock_response(200, {"verification_status": "SUCCESS"})
        with _mock_verify(return_value=response_obj):
            resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "created")
        self.assertEqual(WebhookEvent.objects.count(), 1)
        event = WebhookEvent.objects.get(paypal_event_id="EVT-1")
        self.assertTrue(event.signature_verified)
        self.assertEqual(event.event_type, "PAYMENT.PAYOUTS-ITEM.SUCCEEDED")

    def test_invalid_signature(self):
        response_obj = _mock_response(200, {"verification_status": "FAILURE"})
        with _mock_verify(return_value=response_obj):
            resp = self._post()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_missing_signature_headers(self):
        headers = _headers()
        del headers["PAYPAL-TRANSMISSION-SIG"]
        with _mock_verify(
            return_value=_mock_response(200, {"verification_status": "SUCCESS"})
        ):
            resp = self._post(headers=headers)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_verification_api_failure(self):
        from apps.payments.paypal.client import PayPalAPIError

        with _mock_verify(exception=PayPalAPIError("boom")):
            resp = self._post()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_verification_timeout(self):
        from apps.payments.paypal.client import PayPalTimeoutError

        with _mock_verify(exception=PayPalTimeoutError("timeout")):
            resp = self._post()
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_malformed_json(self):

        with _mock_verify(
            return_value=_mock_response(200, {"verification_status": "SUCCESS"})
        ):
            resp = self.client.post(
                WEBHOOK_URL,
                data=b"{not json",
                content_type="application/json",
                **{"HTTP_" + k.replace("-", "_"): v for k, v in _headers().items()},
            )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_missing_provider_event_id(self):
        body = {"event_type": "X"}
        with _mock_verify(
            return_value=_mock_response(200, {"verification_status": "SUCCESS"})
        ):
            resp = self._post(body=body)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_duplicate_delivery(self):
        response_obj = _mock_response(200, {"verification_status": "SUCCESS"})
        with _mock_verify(return_value=response_obj):
            resp1 = self._post()
            resp2 = self._post()
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["status"], "duplicate")
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_request_size_limit(self):
        big_body = b"x" * (32 * 1024 + 1)
        with _mock_verify(
            return_value=_mock_response(200, {"verification_status": "SUCCESS"})
        ):
            resp = self.client.post(
                WEBHOOK_URL,
                data=big_body,
                content_type="application/json",
                **{"HTTP_" + k.replace("-", "_"): v for k, v in _headers().items()},
            )
        self.assertEqual(resp.status_code, 413)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_unsupported_http_method(self):
        resp = self.client.get(WEBHOOK_URL)
        self.assertEqual(resp.status_code, 405)

    def test_feature_disabled(self):
        with override_settings(PAYPAL_WEBHOOK_ID=""):
            resp = self._post()
        self.assertEqual(resp.status_code, 503)

    def test_no_financial_state_mutation(self):
        from apps.payments.payouts.models import PayoutReservation
        from apps.spend.models import SpendRequest

        before_spend = SpendRequest.objects.count()
        before_payout = PayoutReservation.objects.count()
        response_obj = _mock_response(200, {"verification_status": "SUCCESS"})
        with _mock_verify(return_value=response_obj):
            self._post()
        self.assertEqual(SpendRequest.objects.count(), before_spend)
        self.assertEqual(PayoutReservation.objects.count(), before_payout)

    def test_no_sensitive_data_leakage(self):
        response_obj = _mock_response(200, {"verification_status": "SUCCESS"})
        with _mock_verify(return_value=response_obj):
            resp = self._post()
        self.assertNotIn("test-client-secret", str(resp.content))
        self.assertNotIn("secret", str(resp.content).lower())

    def test_acknowledgment_after_commit(self):
        response_obj = _mock_response(200, {"verification_status": "SUCCESS"})
        with _mock_verify(return_value=response_obj):
            resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            WebhookEvent.objects.filter(paypal_event_id="EVT-1").count(), 1
        )


@override_settings(**WEBHOOK_SETTINGS)
class PayPalWebhookConcurrencyTests(PostgresTransactionTestCase):
    def test_concurrent_duplicate_delivery(self):
        response_obj = _mock_response(200, {"verification_status": "SUCCESS"})
        patcher = _mock_verify(return_value=response_obj)
        patcher.start()
        try:
            results = {}

            def worker(label):
                from django.db import connection as _conn

                _conn.close_if_unusable_or_obsolete()
                import json

                data = json.dumps(_event()).encode()
                from django.test import Client

                c = Client()
                headers = {
                    "HTTP_" + k.replace("-", "_"): v for k, v in _headers().items()
                }
                try:
                    results[label] = c.post(
                        WEBHOOK_URL,
                        data=data,
                        content_type="application/json",
                        **headers,
                    )
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
                self.assertEqual(value.status_code, 200)
            self.assertEqual(WebhookEvent.objects.count(), 1)
        finally:
            patcher.stop()

    def test_inbox_persistence_failure(self):
        from django.db import DatabaseError

        from apps.payments import webhook_service

        response_obj = _mock_response(200, {"verification_status": "SUCCESS"})

        def failing_create(*args, **kwargs):
            raise DatabaseError("db down")

        with _mock_verify(return_value=response_obj):
            with patch.object(
                webhook_service.WebhookEvent.objects, "create", failing_create
            ):
                import json

                data = json.dumps(_event()).encode()
                from django.test import Client

                c = Client()
                headers = {
                    "HTTP_" + k.replace("-", "_"): v for k, v in _headers().items()
                }
                resp = c.post(
                    WEBHOOK_URL, data=data, content_type="application/json", **headers
                )
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(WebhookEvent.objects.count(), 0)
