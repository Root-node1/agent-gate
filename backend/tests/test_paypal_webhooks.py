import json
from unittest.mock import patch
from uuid import uuid4

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.payments.models import WebhookEvent
from apps.payments.paypal import (
    PayPalResponseError,
    PayPalTransientError,
    parse_payout_event,
    read_signature,
    verify_webhook_signature,
)
from apps.payments.paypal.webhooks import WebhookSignature
from apps.payments.tasks import process_webhook_event
from apps.payments.webhook_service import apply_webhook_event
from apps.policies.models import Policy
from apps.spend.models import SpendRequest

SIGNATURE_HEADERS = {
    "HTTP_PAYPAL_TRANSMISSION_ID": "transmission-1",
    "HTTP_PAYPAL_TRANSMISSION_TIME": "2026-11-03T00:00:00Z",
    "HTTP_PAYPAL_CERT_URL": "https://api.paypal.com/cert.pem",
    "HTTP_PAYPAL_AUTH_ALGO": "SHA256withRSA",
    "HTTP_PAYPAL_TRANSMISSION_SIG": "signature",
}


def payout_event(
    *,
    event_id="WH-1",
    event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
    spend_request_id=None,
    batch_id="B-1",
):
    return {
        "id": event_id,
        "event_type": event_type,
        "resource": {
            "payout_batch_id": batch_id,
            "payout_item": {
                "sender_item_id": spend_request_id or str(uuid4()),
            },
        },
    }


class StubVerifyClient:
    def __init__(self, *, status="SUCCESS", error=None):
        self.status = status
        self.error = error
        self.closed = False
        self.calls = []

    def post_json(self, path, *, body, request_id):
        self.calls.append((path, body, request_id))
        if self.error is not None:
            raise self.error
        return {"verification_status": self.status}

    def close(self):
        self.closed = True


class SignatureParsingTests(SimpleTestCase):
    def test_all_headers_are_required(self):
        headers = {
            key.removeprefix("HTTP_").replace("_", "-"): value
            for key, value in SIGNATURE_HEADERS.items()
        }
        self.assertIsNotNone(read_signature(headers))

        for key in headers:
            incomplete = dict(headers)
            incomplete.pop(key)
            self.assertIsNone(read_signature(incomplete))

    def test_verification_uses_the_webhook_id_and_event(self):
        client = StubVerifyClient()
        signature = WebhookSignature(
            transmission_id="t-1",
            transmission_time="2026-11-03T00:00:00Z",
            cert_url="https://api.paypal.com/cert.pem",
            auth_algo="SHA256withRSA",
            transmission_sig="signature",
        )
        event = {"id": "WH-1", "event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED"}

        self.assertTrue(
            verify_webhook_signature(client, "webhook-id", signature, event)
        )
        path, body, request_id = client.calls[0]
        self.assertEqual(path, "/v1/notifications/verify-webhook-signature")
        self.assertEqual(body["webhook_id"], "webhook-id")
        self.assertEqual(body["webhook_event"], event)
        self.assertEqual(request_id, "verify-t-1")

    def test_non_success_status_is_not_verified(self):
        client = StubVerifyClient(status="FAILURE")
        signature = WebhookSignature("t", "time", "cert", "algo", "sig")
        self.assertFalse(verify_webhook_signature(client, "id", signature, {}))


class PayoutEventParsingTests(SimpleTestCase):
    def test_item_event_uses_sender_item_id(self):
        spend_id = str(uuid4())
        parsed = parse_payout_event(
            payout_event(
                event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
                spend_request_id=spend_id,
            )
        )
        self.assertEqual(parsed.spend_request_id, spend_id)
        self.assertEqual(parsed.reference, "B-1")
        self.assertEqual(parsed.provider_status, "SUCCESS")
        self.assertEqual(parsed.outcome, "succeeded")

    def test_batch_event_uses_sender_batch_id(self):
        spend_id = str(uuid4())
        parsed = parse_payout_event(
            {
                "event_type": "PAYMENT.PAYOUTSBATCH.DENIED",
                "resource": {
                    "batch_header": {
                        "sender_batch_id": spend_id,
                        "payout_batch_id": "B-2",
                    }
                },
            }
        )
        self.assertEqual(parsed.spend_request_id, spend_id)
        self.assertEqual(parsed.reference, "B-2")
        self.assertEqual(parsed.outcome, "failed")

    def test_unknown_event_has_no_outcome(self):
        parsed = parse_payout_event(
            payout_event(event_type="PAYMENT.PAYOUTS-ITEM.PENDING")
        )
        self.assertIsNone(parsed.outcome)
        self.assertEqual(parsed.provider_status, "")

    def test_invalid_sender_id_is_ignored(self):
        parsed = parse_payout_event(payout_event(spend_request_id="not-a-uuid"))
        self.assertIsNone(parsed.spend_request_id)


@override_settings(PAYPAL_WEBHOOK_ID="webhook-id")
class WebhookEndpointTests(TestCase):
    def setUp(self):
        self.http = Client(enforce_csrf_checks=True)

    def post(self, event=None, headers=None, body=None, content_type="application/json"):
        payload = body if body is not None else json.dumps(event or payout_event())
        return self.http.post(
            "/webhooks/paypal",
            data=payload,
            content_type=content_type,
            **(SIGNATURE_HEADERS if headers is None else headers),
        )

    def test_verified_event_is_stored_and_scheduled(self):
        client = StubVerifyClient()
        with patch(
            "apps.payments.views.build_paypal_client", return_value=client
        ), patch("apps.payments.views.schedule_webhook_processing") as schedule:
            response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(client.closed)
        event = WebhookEvent.objects.get(paypal_event_id="WH-1")
        self.assertTrue(event.signature_verified)
        self.assertEqual(event.event_type, "PAYMENT.PAYOUTS-ITEM.SUCCEEDED")
        schedule.assert_called_once_with(event.pk)

    def test_missing_signature_headers_are_rejected(self):
        headers = dict(SIGNATURE_HEADERS)
        headers.pop("HTTP_PAYPAL_TRANSMISSION_SIG")
        with patch("apps.payments.views.build_paypal_client") as build:
            response = self.post(headers=headers)

        self.assertEqual(response.status_code, 400)
        build.assert_not_called()
        self.assertFalse(WebhookEvent.objects.exists())

    def test_invalid_json_is_rejected(self):
        with patch("apps.payments.views.build_paypal_client") as build:
            response = self.post(body="{not-json")
        self.assertEqual(response.status_code, 400)
        build.assert_not_called()

    def test_missing_event_id_is_rejected(self):
        event = payout_event()
        event.pop("id")
        with patch("apps.payments.views.build_paypal_client") as build:
            response = self.post(event=event)
        self.assertEqual(response.status_code, 400)
        build.assert_not_called()

    def test_wrong_content_type_is_rejected(self):
        with patch("apps.payments.views.build_paypal_client") as build:
            response = self.post(content_type="text/plain")
        self.assertEqual(response.status_code, 400)
        build.assert_not_called()

    def test_failed_verification_is_rejected(self):
        client = StubVerifyClient(status="FAILURE")
        with patch(
            "apps.payments.views.build_paypal_client", return_value=client
        ):
            response = self.post()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(WebhookEvent.objects.exists())

    def test_rejected_verification_request_is_rejected(self):
        client = StubVerifyClient(
            error=PayPalResponseError("bad", status_code=422, code="BAD")
        )
        with patch(
            "apps.payments.views.build_paypal_client", return_value=client
        ):
            response = self.post()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(WebhookEvent.objects.exists())

    def test_unauthorized_verification_request_is_unavailable(self):
        client = StubVerifyClient(
            error=PayPalResponseError("bad", status_code=401, code="AUTH")
        )
        with patch(
            "apps.payments.views.build_paypal_client", return_value=client
        ):
            response = self.post()

        self.assertEqual(response.status_code, 503)
        self.assertFalse(WebhookEvent.objects.exists())

    def test_transient_verification_failure_is_unavailable(self):
        client = StubVerifyClient(error=PayPalTransientError("down"))
        with patch(
            "apps.payments.views.build_paypal_client", return_value=client
        ):
            response = self.post()

        self.assertEqual(response.status_code, 503)
        self.assertFalse(WebhookEvent.objects.exists())

    @override_settings(PAYPAL_WEBHOOK_ID="")
    def test_missing_webhook_id_is_unavailable(self):
        with patch("apps.payments.views.build_paypal_client") as build:
            response = self.post()
        self.assertEqual(response.status_code, 503)
        build.assert_not_called()

    def test_duplicate_event_is_deduplicated(self):
        client = StubVerifyClient()
        with patch(
            "apps.payments.views.build_paypal_client", return_value=client
        ), patch("apps.payments.views.schedule_webhook_processing") as schedule:
            self.assertEqual(self.post().status_code, 200)
            self.assertEqual(self.post().status_code, 200)

        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertEqual(schedule.call_count, 2)

    def test_processed_duplicate_is_not_scheduled_again(self):
        WebhookEvent.objects.create(
            paypal_event_id="WH-1",
            event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
            payload=payout_event(),
            signature_verified=True,
            processed_at=timezone.now(),
        )
        client = StubVerifyClient()
        with patch(
            "apps.payments.views.build_paypal_client", return_value=client
        ), patch("apps.payments.views.schedule_webhook_processing") as schedule:
            response = self.post()

        self.assertEqual(response.status_code, 200)
        schedule.assert_not_called()


class WebhookProcessingTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="default")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)
        self.spend = self.spend_request()

    def spend_request(self, **overrides):
        values = {
            "organization": self.organization,
            "agent": self.agent,
            "policy": self.policy,
            "policy_version": self.policy.version,
            "amount_minor": 1_000,
            "currency": "USD",
            "merchant_ref": "acme.com",
            "destination_type": "paypal_email",
            "destination_value": "payee@example.com",
            "decision": SpendRequest.Decision.ALLOW,
            "status": SpendRequest.Status.EXECUTING,
        }
        values.update(overrides)
        return SpendRequest.objects.create(**values)

    def event(
        self,
        *,
        event_id=None,
        event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
        spend_request_id=None,
        batch_id="B-1",
    ):
        payload = payout_event(
            event_id=event_id or str(uuid4()),
            event_type=event_type,
            spend_request_id=spend_request_id or str(self.spend.pk),
            batch_id=batch_id,
        )
        return WebhookEvent.objects.create(
            paypal_event_id=payload["id"],
            event_type=event_type,
            payload=payload,
            signature_verified=True,
        )

    def audit_events(self):
        return list(
            AuditEvent.objects.filter(spend_request=self.spend).order_by("id")
        )

    def test_succeeded_event_completes_the_request(self):
        event = self.event()

        self.assertEqual(apply_webhook_event(event.pk), "applied")
        self.spend.refresh_from_db()
        self.assertEqual(self.spend.status, SpendRequest.Status.SUCCEEDED)
        self.assertEqual(self.spend.paypal_reference, "B-1")
        self.assertEqual(self.spend.paypal_status, "SUCCESS")
        self.assertIsNotNone(self.spend.executed_at)
        self.assertEqual(
            [audit.event_type for audit in self.audit_events()],
            [
                AuditEvent.EventType.PAYMENT_SUCCEEDED,
                AuditEvent.EventType.WEBHOOK_RECEIVED,
            ],
        )
        for audit in self.audit_events():
            self.assertEqual(audit.actor_type, AuditEvent.ActorType.PAYPAL)

    def test_failed_event_fails_the_request(self):
        event = self.event(event_type="PAYMENT.PAYOUTS-ITEM.FAILED")

        self.assertEqual(apply_webhook_event(event.pk), "applied")
        self.spend.refresh_from_db()
        self.assertEqual(self.spend.status, SpendRequest.Status.FAILED)
        self.assertEqual(self.spend.paypal_status, "FAILED")
        self.assertIsNotNone(self.spend.executed_at)

    def test_reversal_is_forward_only(self):
        self.spend.status = SpendRequest.Status.SUCCEEDED
        self.spend.paypal_reference = "B-1"
        self.spend.save(update_fields=["status", "paypal_reference", "updated_at"])
        event = self.event(event_type="PAYMENT.PAYOUTS-ITEM.REFUNDED")

        self.assertEqual(apply_webhook_event(event.pk), "applied")
        self.spend.refresh_from_db()
        self.assertEqual(self.spend.status, SpendRequest.Status.REVERSED)
        self.assertEqual(
            self.audit_events()[0].event_type,
            AuditEvent.EventType.PAYMENT_REVERSED,
        )

    def test_failure_after_success_is_not_applied(self):
        self.spend.status = SpendRequest.Status.SUCCEEDED
        self.spend.paypal_reference = "B-1"
        self.spend.save(update_fields=["status", "paypal_reference", "updated_at"])
        event = self.event(event_type="PAYMENT.PAYOUTS-ITEM.FAILED")

        self.assertEqual(apply_webhook_event(event.pk), "ignored")
        self.spend.refresh_from_db()
        self.assertEqual(self.spend.status, SpendRequest.Status.SUCCEEDED)
        audits = self.audit_events()
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].event_type, AuditEvent.EventType.WEBHOOK_RECEIVED)
        self.assertFalse(audits[0].payload["applied"])
        self.assertEqual(audits[0].payload["reason"], "not_forward")

    def test_reference_mismatch_is_not_applied(self):
        self.spend.paypal_reference = "B-OTHER"
        self.spend.save(update_fields=["paypal_reference", "updated_at"])
        event = self.event(batch_id="B-1")

        self.assertEqual(apply_webhook_event(event.pk), "ignored")
        self.spend.refresh_from_db()
        self.assertEqual(self.spend.status, SpendRequest.Status.EXECUTING)
        audits = self.audit_events()
        self.assertEqual(audits[0].payload["reason"], "reference_mismatch")

    def test_unsupported_event_is_recorded_without_a_status_change(self):
        event = self.event(event_type="PAYMENT.PAYOUTS-ITEM.PENDING")

        self.assertEqual(apply_webhook_event(event.pk), "ignored")
        self.spend.refresh_from_db()
        self.assertEqual(self.spend.status, SpendRequest.Status.EXECUTING)
        audits = self.audit_events()
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].payload["reason"], "unsupported_event")

    def test_event_for_a_request_without_a_payout_is_not_applied(self):
        self.spend.status = SpendRequest.Status.PENDING_APPROVAL
        self.spend.save(update_fields=["status", "updated_at"])
        event = self.event()

        self.assertEqual(apply_webhook_event(event.pk), "ignored")
        self.spend.refresh_from_db()
        self.assertEqual(self.spend.status, SpendRequest.Status.PENDING_APPROVAL)
        audits = self.audit_events()
        self.assertEqual(audits[0].payload["reason"], "unexpected_state")

    def test_unknown_spend_request_is_marked_processed(self):
        event = self.event(spend_request_id=str(uuid4()))

        self.assertEqual(apply_webhook_event(event.pk), "ignored")
        event.refresh_from_db()
        self.assertIsNotNone(event.processed_at)
        self.assertFalse(AuditEvent.objects.exists())

    def test_event_without_a_spend_request_is_marked_processed(self):
        event = WebhookEvent.objects.create(
            paypal_event_id=str(uuid4()),
            event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
            payload={"event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED", "resource": {}},
            signature_verified=True,
        )

        self.assertEqual(apply_webhook_event(event.pk), "ignored")
        event.refresh_from_db()
        self.assertIsNotNone(event.processed_at)

    def test_processing_is_idempotent(self):
        event = self.event()

        self.assertEqual(apply_webhook_event(event.pk), "applied")
        self.assertEqual(apply_webhook_event(event.pk), "already_processed")
        self.assertEqual(len(self.audit_events()), 2)

    def test_unverified_event_is_refused(self):
        event = WebhookEvent.objects.create(
            paypal_event_id=str(uuid4()),
            event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
            payload=payout_event(spend_request_id=str(self.spend.pk)),
            signature_verified=False,
        )

        with self.assertRaises(PermissionError):
            apply_webhook_event(event.pk)
        self.spend.refresh_from_db()
        self.assertEqual(self.spend.status, SpendRequest.Status.EXECUTING)

    def test_task_delegates_to_the_service(self):
        event = self.event()

        self.assertEqual(process_webhook_event(str(event.pk)), "applied")
        self.spend.refresh_from_db()
        self.assertEqual(self.spend.status, SpendRequest.Status.SUCCEEDED)
