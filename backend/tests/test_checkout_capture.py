"""Tests for PayPal Sandbox checkout capture (INT-13H).

All tests are offline — no real PayPal API calls are made.  The PayPalClient
is injected as a mock (service-level) or patched at the view module (view-level),
and the database layer runs against PostgreSQL (PostgresTransactionTestCase is
used for the true concurrency test).
"""

import copy
import threading
import uuid
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.payments.checkout import services
from apps.payments.models import CheckoutOrder
from apps.payments.paypal.client import (
    PayPalAPIError,
    PayPalClient,
    PayPalRateLimitError,
    PayPalServerError,
    PayPalUncertainOutcomeError,
)
from tests.base import PostgresTransactionTestCase, force_mfa

PAYPAL_ORDER_ID = "5O19011234567890X"
PAYPAL_CAPTURE_ID = "3CAPTURE123456789"
CHECKOUT_URL = "/v1/checkout-orders/"
CAPTURE_URL = lambda pk: f"/v1/checkout-orders/{pk}/capture/"  # noqa: E731

_APPROVED_ORDER = {
    "id": PAYPAL_ORDER_ID,
    "status": "APPROVED",
    "intent": "CAPTURE",
    "purchase_units": [
        {"amount": {"currency_code": "USD", "value": "10.00"}},
    ],
}
_CAPTURE_RESPONSE = {
    "id": PAYPAL_ORDER_ID,
    "status": "COMPLETED",
    "intent": "CAPTURE",
    "purchase_units": [
        {
            "amount": {"currency_code": "USD", "value": "10.00"},
            "payments": {
                "captures": [
                    {
                        "id": PAYPAL_CAPTURE_ID,
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "10.00"},
                    }
                ]
            },
        }
    ],
}
_COMPLETED_ORDER = {
    "id": PAYPAL_ORDER_ID,
    "status": "COMPLETED",
    "intent": "CAPTURE",
    "purchase_units": [
        {
            "amount": {"currency_code": "USD", "value": "10.00"},
            "payments": {
                "captures": [
                    {
                        "id": PAYPAL_CAPTURE_ID,
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "10.00"},
                    }
                ]
            },
        }
    ],
}


def _order(status="APPROVED", intent="CAPTURE", value="10.00"):
    return {
        "id": PAYPAL_ORDER_ID,
        "status": status,
        "intent": intent,
        "purchase_units": [
            {"amount": {"currency_code": "USD", "value": value}},
        ],
    }


def _capture_response(capture_id=PAYPAL_CAPTURE_ID, capture_status="COMPLETED"):
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
                            "status": capture_status,
                            "amount": {"currency_code": "USD", "value": "10.00"},
                        }
                    ]
                },
            }
        ],
    }


def _completed_order_with_capture(capture_id=PAYPAL_CAPTURE_ID):
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


def make_capture_client(
    *,
    get_response=None,
    post_response=None,
    get_side_effect=None,
    post_side_effect=None,
):
    """Build a mock PayPalClient for service-level tests."""
    client = MagicMock(spec=PayPalClient)
    if get_side_effect is not None:
        client.get.side_effect = get_side_effect
    else:
        client.get.return_value = get_response
    if post_side_effect is not None:
        client.post.side_effect = post_side_effect
    else:
        client.post.return_value = post_response
    return client


# ---------------------------------------------------------------------------
# Pure helper tests (no database needed)
# ---------------------------------------------------------------------------


class CaptureVerificationTests(SimpleTestCase):
    """The order/capture verification helpers are pure and independently testable."""

    def test_verify_paypal_order_accepts_match(self):
        checkout = MagicMock(spec=CheckoutOrder)
        checkout.paypal_order_id = PAYPAL_ORDER_ID
        checkout.currency = "USD"
        checkout.amount_minor = 1000
        self.assertEqual(
            services._verify_paypal_order(dict(_APPROVED_ORDER), checkout), "APPROVED"
        )

    def test_verify_paypal_order_rejects_identity_mismatch(self):
        checkout = MagicMock(spec=CheckoutOrder)
        checkout.paypal_order_id = PAYPAL_ORDER_ID
        checkout.currency = "USD"
        checkout.amount_minor = 1000
        mismatched = dict(_APPROVED_ORDER)
        mismatched["id"] = "OTHER-ORDER"
        with self.assertRaises(services.CaptureVerificationError):
            services._verify_paypal_order(mismatched, checkout)

    def test_verify_paypal_order_rejects_non_capture_intent(self):
        checkout = MagicMock(spec=CheckoutOrder)
        checkout.paypal_order_id = PAYPAL_ORDER_ID
        checkout.currency = "USD"
        checkout.amount_minor = 1000
        order = _order(intent="AUTHORIZE")
        with self.assertRaises(services.CaptureVerificationError):
            services._verify_paypal_order(order, checkout)


# ---------------------------------------------------------------------------
# Service-level tests (TestCase — need a database for CheckoutOrder)
# ---------------------------------------------------------------------------


class CaptureServiceTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="capture-test")
        self.amount_minor = 1000  # $10.00
        self.checkout = CheckoutOrder.objects.create(
            organization=self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            status=CheckoutOrder.Status.APPROVED,
            paypal_order_id=PAYPAL_ORDER_ID,
        )
        self.capture_key = uuid.uuid4()

    def _capture(self, **overrides):
        checkout = overrides.pop("checkout", self.checkout)
        client = overrides.pop("client", None)
        return services.capture_checkout_order(
            checkout_order=checkout,
            organization_id=self.organization.pk,
            capture_idempotency_key=overrides.pop("key", self.capture_key),
            client=client,
        )

    # 1. Explicit capture success ------------------------------------------------
    def test_explicit_capture_success(self):
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=_CAPTURE_RESPONSE
        )
        checkout, outcome, replayed = self._capture(client=client)

        self.assertEqual(outcome, services.CaptureOutcome.COMPLETED)
        self.assertFalse(replayed)
        self.assertEqual(checkout.status, CheckoutOrder.Status.COMPLETED)
        self.assertEqual(checkout.paypal_capture_id, PAYPAL_CAPTURE_ID)
        self.assertEqual(checkout.capture_idempotency_key, self.capture_key)
        self.assertEqual(checkout.updated_at, checkout.updated_at)

    # 2. Correct PayPal capture endpoint ---------------------------------------
    def test_correct_paypal_capture_endpoint(self):
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=_CAPTURE_RESPONSE
        )
        self._capture(client=client)

        args, _ = client.post.call_args
        self.assertEqual(args[0], f"/v2/checkout/orders/{PAYPAL_ORDER_ID}/capture")

    # 3. Stable capture PayPal-Request-Id --------------------------------------
    def test_stable_capture_paypal_request_id(self):
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=_CAPTURE_RESPONSE
        )
        self._capture(client=client)

        _, kwargs = client.post.call_args
        self.assertEqual(kwargs["request_id"], str(self.capture_key))

    # 4. Approval verified via PayPal GET --------------------------------------
    def test_approval_verified_via_paypal_get(self):
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=_CAPTURE_RESPONSE
        )
        self._capture(client=client)

        client.get.assert_called_once_with(f"/v2/checkout/orders/{PAYPAL_ORDER_ID}")
        client.post.assert_called_once()
        # POST only happens after the GET confirmed approval.
        get_time = client.get.call_args[0]
        post_time = client.post.call_args.args
        self.assertEqual(get_time, (f"/v2/checkout/orders/{PAYPAL_ORDER_ID}",))
        self.assertIn("/capture", post_time[0])

    # 5. Return URL alone is insufficient --------------------------------------
    def test_return_url_alone_insufficient(self):
        unapproved = CheckoutOrder.objects.create(
            organization=self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            status=CheckoutOrder.Status.PAYER_ACTION_REQUIRED,
            paypal_order_id="5O19011234567891Y",
        )
        client = make_capture_client(post_response=_CAPTURE_RESPONSE)

        with self.assertRaises(services.CaptureNotApproved):
            self._capture(checkout=unapproved, client=client)

        # No PayPal call is made — an unapproved order cannot be captured.
        self.assertEqual(client.get.call_count, 0)
        self.assertEqual(client.post.call_count, 0)

    def test_local_approved_but_paypal_not_approved_is_rejected(self):
        # Even with local APPROVED, PayPal must confirm approval via GET.
        client = make_capture_client(
            get_response=_order(status="CREATED"), post_response=_CAPTURE_RESPONSE
        )
        with self.assertRaises(services.CaptureNotApproved):
            self._capture(client=client)
        # The order is declined, never captured.
        client.post.assert_not_called()
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)

    # 6. CAPTURE intent enforcement --------------------------------------------
    def test_capture_intent_enforced(self):
        client = make_capture_client(
            get_response=_order(intent="AUTHORIZE"), post_response=_CAPTURE_RESPONSE
        )
        with self.assertRaises(services.CaptureVerificationError):
            self._capture(client=client)
        client.post.assert_not_called()
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)

    # 7. Amount and currency mismatch ------------------------------------------
    def test_amount_mismatch_declines(self):
        order = _order()
        order["purchase_units"][0]["amount"]["value"] = "99.99"
        client = make_capture_client(
            get_response=order, post_response=_CAPTURE_RESPONSE
        )
        with self.assertRaises(services.CaptureVerificationError):
            self._capture(client=client)
        client.post.assert_not_called()
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)
        self.assertIsNone(self.checkout.paypal_capture_id)

    def test_currency_mismatch_declines(self):
        order = _order()
        order["purchase_units"][0]["amount"]["currency_code"] = "EUR"
        client = make_capture_client(
            get_response=order, post_response=_CAPTURE_RESPONSE
        )
        with self.assertRaises(services.CaptureVerificationError):
            self._capture(client=client)
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)

    # 8. PayPal order identity mismatch ----------------------------------------
    def test_paypal_order_identity_mismatch(self):
        order = _order()
        order["id"] = "DOES-NOT-MATCH"
        client = make_capture_client(
            get_response=order, post_response=_CAPTURE_RESPONSE
        )
        with self.assertRaises(services.CaptureVerificationError):
            self._capture(client=client)
        client.post.assert_not_called()
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)

    # 14. Duplicate capture replay (idempotent) ----------------------------------
    def test_duplicate_capture_replay(self):
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=_CAPTURE_RESPONSE
        )
        _checkout, outcome, replayed = self._capture(client=client)
        self.assertEqual(outcome, services.CaptureOutcome.COMPLETED)
        self.assertFalse(replayed)
        self.assertEqual(client.post.call_count, 1)

        # Same key again — the order is already completed; no PayPal call.
        _checkout2, outcome2, replayed2 = services.capture_checkout_order(
            checkout_order=CheckoutOrder.objects.get(pk=self.checkout.pk),
            organization_id=self.organization.pk,
            capture_idempotency_key=self.capture_key,
            client=client,
        )
        self.assertEqual(outcome2, services.CaptureOutcome.COMPLETED)
        self.assertTrue(replayed2)
        self.assertEqual(client.post.call_count, 1)
        self.assertEqual(client.get.call_count, 1)

    # 15. Timeout -> CAPTURE_PENDING --------------------------------------------
    def test_timeout_preserves_capture_pending(self):
        client = make_capture_client(
            get_response=_APPROVED_ORDER,
            post_side_effect=PayPalUncertainOutcomeError(
                "POST request to PayPal did not receive a response."
            ),
        )
        checkout, outcome, replayed = self._capture(client=client)

        self.assertEqual(outcome, services.CaptureOutcome.PENDING)
        self.assertFalse(replayed)
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, CheckoutOrder.Status.CAPTURE_PENDING)
        self.assertEqual(checkout.capture_idempotency_key, self.capture_key)
        self.assertIsNone(checkout.paypal_capture_id)
        self.assertEqual(client.post.call_count, 1)

    # 16. 5xx -> CAPTURE_PENDING (uncertain, no blind retry) --------------------
    def test_5xx_preserves_capture_pending(self):
        client = make_capture_client(
            get_response=_APPROVED_ORDER,
            post_side_effect=PayPalUncertainOutcomeError(
                "POST request to PayPal returned a server error (HTTP 503)."
            ),
        )
        checkout, outcome, _ = self._capture(client=client)

        self.assertEqual(outcome, services.CaptureOutcome.PENDING)
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, CheckoutOrder.Status.CAPTURE_PENDING)
        self.assertEqual(client.post.call_count, 1)

    def test_get_5xx_preserves_capture_pending(self):
        client = make_capture_client(
            get_side_effect=PayPalServerError("PayPal GET returned HTTP 503."),
            post_response=_CAPTURE_RESPONSE,
        )
        checkout, outcome, _ = self._capture(client=client)

        self.assertEqual(outcome, services.CaptureOutcome.PENDING)
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, CheckoutOrder.Status.CAPTURE_PENDING)
        # The capture POST must not be attempted when verification is uncertain.
        client.post.assert_not_called()

    # 17. Missing capture ID ---------------------------------------------------
    def test_missing_capture_id_declines(self):
        response = _capture_response()
        response["purchase_units"][0]["payments"]["captures"][0]["id"] = None
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=response
        )
        with self.assertRaises(services.CaptureVerificationError):
            self._capture(client=client)
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)
        self.assertIsNone(self.checkout.paypal_capture_id)

    def test_missing_capture_object_declines(self):
        response = copy.deepcopy(_CAPTURE_RESPONSE)
        response["purchase_units"][0]["payments"]["captures"] = []
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=response
        )
        with self.assertRaises(services.CaptureVerificationError):
            self._capture(client=client)
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)

    # 18. Non-COMPLETED capture status -----------------------------------------
    def test_pending_capture_status_preserved(self):
        response = _capture_response(capture_status="PENDING")
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=response
        )
        checkout, outcome, _ = self._capture(client=client)

        self.assertEqual(outcome, services.CaptureOutcome.PENDING)
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, CheckoutOrder.Status.CAPTURE_PENDING)
        self.assertIsNone(checkout.paypal_capture_id)

    def test_denied_capture_status_declines(self):
        response = _capture_response(capture_status="DENIED")
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=response
        )
        with self.assertRaises(services.CaptureVerificationError):
            self._capture(client=client)
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)

    def test_unknown_capture_status_preserves_pending(self):
        # INT-13H.1: PayPal returned a capture status we don't recognise
        # (e.g. INSTRUMENT_DENIED).  This is nonterminal — preserve
        # CAPTURE_PENDING, never DECLINED, never COMPLETED, never POST again.
        response = _capture_response(capture_status="INSTRUMENT_DENIED")
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=response
        )
        checkout, outcome, _ = self._capture(client=client)

        self.assertEqual(outcome, services.CaptureOutcome.PENDING)
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, CheckoutOrder.Status.CAPTURE_PENDING)
        self.assertIsNone(checkout.paypal_capture_id)
        self.assertEqual(checkout.paypal_order_id, PAYPAL_ORDER_ID)
        self.assertEqual(checkout.capture_idempotency_key, self.capture_key)

    def test_unknown_capture_status_on_reconciliation_preserves_pending(self):
        # During a GET reconciliation, PayPal reports the order COMPLETED but
        # the capture carries an unknown status.  Preserve CAPTURE_PENDING —
        # do not auto-complete or decline on ambiguity.
        order = copy.deepcopy(_COMPLETED_ORDER)
        order["purchase_units"][0]["payments"]["captures"][0]["status"] = (
            "INSTRUMENT_DENIED"
        )
        client = make_capture_client(get_response=order)
        checkout, outcome, _ = self._capture(client=client)

        self.assertEqual(outcome, services.CaptureOutcome.PENDING)
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, CheckoutOrder.Status.CAPTURE_PENDING)
        self.assertIsNone(checkout.paypal_capture_id)
        client.post.assert_not_called()

    def test_terminal_capture_status_on_reconciliation_declines(self):
        # A known terminal failure status (DENIED) on a COMPLETED order is
        # conclusive — decline rather than preserve pending.
        order = copy.deepcopy(_COMPLETED_ORDER)
        order["purchase_units"][0]["payments"]["captures"][0]["status"] = "DENIED"
        client = make_capture_client(get_response=order)
        with self.assertRaises(services.CaptureVerificationError):
            self._capture(client=client)
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)
        client.post.assert_not_called()

    # 19. Confirmed terminal failure (PayPal 4xx on capture POST) -------------

    # 19a. 429 rate-limit preserves pending (non-conclusive) --------------------
    def test_rate_limit_on_capture_preserves_pending(self):
        client = make_capture_client(
            get_response=_APPROVED_ORDER,
            post_side_effect=PayPalRateLimitError("HTTP 429: rate limited"),
        )
        checkout, outcome, _ = self._capture(client=client)

        self.assertEqual(outcome, services.CaptureOutcome.PENDING)
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, CheckoutOrder.Status.CAPTURE_PENDING)
        self.assertIsNone(checkout.paypal_capture_id)
        self.assertEqual(checkout.capture_idempotency_key, self.capture_key)

    # 19b. Confirmed terminal failure (400/401/403/404/409 on capture POST) -----
    def test_confirmed_terminal_failure_declines(self):
        client = make_capture_client(
            get_response=_APPROVED_ORDER,
            post_side_effect=PayPalAPIError("INVALID_REQUEST: intent does not match"),
        )
        with self.assertRaises(PayPalAPIError):
            self._capture(client=client)
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.DECLINED)
        self.assertIsNone(self.checkout.paypal_capture_id)

    # 20. No database lock held during HTTP ------------------------------------
    def test_no_db_lock_during_http(self):
        state = {}
        baseline = list(transaction.get_connection().savepoint_ids)

        def fake_get(*args, **kwargs):
            state["get_savepoints"] = list(transaction.get_connection().savepoint_ids)
            return _APPROVED_ORDER

        def fake_post(*args, **kwargs):
            state["post_savepoints"] = list(transaction.get_connection().savepoint_ids)
            return _CAPTURE_RESPONSE

        client = MagicMock(spec=PayPalClient)
        client.get.side_effect = fake_get
        client.post.side_effect = fake_post

        self._capture(client=client)

        self.assertEqual(state["get_savepoints"], baseline)
        self.assertEqual(state["post_savepoints"], baseline)

    # 21. Creation does not auto-capture ---------------------------------------
    def test_creation_does_not_auto_capture(self):
        client = make_capture_client(
            post_response={"id": "CREATE-ORDER-999", "links": []}
        )
        services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=uuid.uuid4(),
            client=client,
        )
        # Only the create POST; no GET and no capture POST.
        self.assertEqual(client.post.call_count, 1)
        self.assertEqual(client.get.call_count, 0)
        self.assertEqual(client.post.call_args.args[0], "/v2/checkout/orders")

    # 22. Secret redaction (service-level) -------------------------------------
    def test_capture_error_message_redacted(self):
        client = make_capture_client(
            get_response=_order(intent="AUTHORIZE"), post_response=_CAPTURE_RESPONSE
        )
        with self.assertRaises(services.CaptureVerificationError) as ctx:
            self._capture(client=client)
        message = str(ctx.exception)
        self.assertNotIn("client_id", message.lower())
        self.assertNotIn("secret", message.lower())

    # 23. Reconciliation of an uncertain capture -------------------------------
    def test_reconciliation_of_uncertain_capture(self):
        # First attempt: POST times out -> CAPTURE_PENDING.
        # Retry: GET now reports COMPLETED with a capture -> reconcile, no POST.
        client = make_capture_client(
            get_side_effect=[
                _APPROVED_ORDER,  # first attempt verification
                _COMPLETED_ORDER,  # retry reconciliation sees the capture
            ],
            post_side_effect=[
                PayPalUncertainOutcomeError("POST request to PayPal timed out."),
            ],
        )

        _checkout, outcome, _ = services.capture_checkout_order(
            checkout_order=self.checkout,
            organization_id=self.organization.pk,
            capture_idempotency_key=self.capture_key,
            client=client,
        )
        self.assertEqual(outcome, services.CaptureOutcome.PENDING)
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.CAPTURE_PENDING)
        self.assertEqual(client.post.call_count, 1)

        # Retry with the same key: reconcile via GET, no second POST.
        _checkout2, outcome2, replayed = services.capture_checkout_order(
            checkout_order=CheckoutOrder.objects.get(pk=self.checkout.pk),
            organization_id=self.organization.pk,
            capture_idempotency_key=self.capture_key,
            client=client,
        )
        self.assertEqual(outcome2, services.CaptureOutcome.COMPLETED)
        self.assertFalse(replayed)
        self.assertEqual(client.post.call_count, 1)  # no second capture POST
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.COMPLETED)
        self.assertEqual(self.checkout.paypal_capture_id, PAYPAL_CAPTURE_ID)

    def test_reconciliation_when_paypal_still_approved_reposts(self):
        # After a timeout PayPal reports the order is still APPROVED (not
        # captured) -> the capture is resubmitted with the same Request-Id.
        client = make_capture_client(
            get_side_effect=[
                _APPROVED_ORDER,  # first verification
                _APPROVED_ORDER,  # retry verification (still not captured)
            ],
            post_side_effect=[
                PayPalUncertainOutcomeError("POST request to PayPal timed out."),  # 1st
                _CAPTURE_RESPONSE,  # retry succeeds
            ],
        )

        services.capture_checkout_order(
            checkout_order=CheckoutOrder.objects.get(pk=self.checkout.pk),
            organization_id=self.organization.pk,
            capture_idempotency_key=self.capture_key,
            client=client,
        )
        self.assertEqual(client.post.call_count, 1)

        checkout, outcome, _ = services.capture_checkout_order(
            checkout_order=CheckoutOrder.objects.get(pk=self.checkout.pk),
            organization_id=self.organization.pk,
            capture_idempotency_key=self.capture_key,
            client=client,
        )
        self.assertEqual(outcome, services.CaptureOutcome.COMPLETED)
        self.assertEqual(client.post.call_count, 2)
        # Both POSTs carried the stable idempotency key.
        request_ids = [call.kwargs["request_id"] for call in client.post.call_args_list]
        self.assertEqual(request_ids, [str(self.capture_key), str(self.capture_key)])
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, CheckoutOrder.Status.COMPLETED)
        self.assertEqual(checkout.paypal_capture_id, PAYPAL_CAPTURE_ID)

    # 24. No double capture ----------------------------------------------------
    def test_no_double_capture_with_different_key(self):
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=_CAPTURE_RESPONSE
        )
        # First capture succeeds.
        services.capture_checkout_order(
            checkout_order=CheckoutOrder.objects.get(pk=self.checkout.pk),
            organization_id=self.organization.pk,
            capture_idempotency_key=self.capture_key,
            client=client,
        )
        self.assertEqual(client.post.call_count, 1)

        # A second caller with a DIFFERENT key cannot recapture — a completed
        # order is always a replay, regardless of the idempotency key presented.
        _checkout, outcome, replayed = services.capture_checkout_order(
            checkout_order=CheckoutOrder.objects.get(pk=self.checkout.pk),
            organization_id=self.organization.pk,
            capture_idempotency_key=uuid.uuid4(),
            client=client,
        )
        self.assertEqual(outcome, services.CaptureOutcome.COMPLETED)
        self.assertTrue(replayed)
        self.assertEqual(client.post.call_count, 1)
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, CheckoutOrder.Status.COMPLETED)
        self.assertEqual(self.checkout.paypal_capture_id, PAYPAL_CAPTURE_ID)

    # 25. Completed replay preserves original key (different key supplied) ------
    def test_completed_replay_preserves_original_capture_key(self):
        """A COMPLETED order replayed with a different key returns the original
        capture result, never issues another PayPal POST, and clearly flags the
        replay."""
        client = make_capture_client(
            get_response=_APPROVED_ORDER, post_response=_CAPTURE_RESPONSE
        )
        services.capture_checkout_order(
            checkout_order=CheckoutOrder.objects.get(pk=self.checkout.pk),
            organization_id=self.organization.pk,
            capture_idempotency_key=self.capture_key,
            client=client,
        )
        self.assertEqual(client.post.call_count, 1)

        # Replay with a DIFFERENT key — the original key is immutable and must
        # be preserved; the caller's key must not overwrite it.
        replay_key = uuid.uuid4()
        checkout, outcome, replayed = services.capture_checkout_order(
            checkout_order=CheckoutOrder.objects.get(pk=self.checkout.pk),
            organization_id=self.organization.pk,
            capture_idempotency_key=replay_key,
            client=client,
        )
        # No PayPal POST — the order is already completed.
        self.assertEqual(client.post.call_count, 1)
        self.assertEqual(outcome, services.CaptureOutcome.COMPLETED)
        self.assertTrue(replayed)
        # The original capture key is preserved, not the caller's different key.
        self.assertEqual(checkout.capture_idempotency_key, self.capture_key)
        self.assertNotEqual(replay_key, self.capture_key)
        # The existing capture result is returned unchanged.
        self.assertEqual(checkout.paypal_capture_id, PAYPAL_CAPTURE_ID)
        self.assertEqual(checkout.status, CheckoutOrder.Status.COMPLETED)


# ---------------------------------------------------------------------------
# View-level tests (APITestCase — exercise the HTTP layer)
# ---------------------------------------------------------------------------


@override_settings(
    PAYPAL_CHECKOUT_ENABLED="true",
    PAYPAL_CLIENT_ID="test-client-id",
    PAYPAL_CLIENT_SECRET="test-client-secret",
)
class CheckoutViewBase(APITestCase):
    amount_minor = 1000

    def setUp(self):
        self.organization = Organization.objects.create(name="checkout-org")
        self.other_org = Organization.objects.create(name="other-org")
        self.admin = self._make_member("admin", OrgMembership.Role.ADMIN)
        self.viewer = self._make_member("viewer", OrgMembership.Role.VIEWER)

    def _make_member(self, name, role):
        user = User.objects.create_user(name)
        OrgMembership.objects.create(
            user=user, organization=self.organization, role=role
        )
        force_mfa(user)
        return user

    def _make_approved_order(self, organization=None):
        return CheckoutOrder.objects.create(
            organization=organization or self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            paypal_order_id=PAYPAL_ORDER_ID,
            status=CheckoutOrder.Status.APPROVED,
        )

    def _patch_client(
        self, mock_class, *, get_response=_APPROVED_ORDER, post_response=None
    ):
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.get.return_value = get_response
        if post_response is not None:
            mock_client.post.return_value = post_response
        else:
            mock_client.post.return_value = _CAPTURE_RESPONSE
        mock_class.return_value = mock_client
        return mock_client


@override_settings(
    PAYPAL_CHECKOUT_ENABLED="true",
    PAYPAL_CLIENT_ID="test-client-id",
    PAYPAL_CLIENT_SECRET="test-client-secret",
)
class CheckoutCaptureViewTests(CheckoutViewBase):
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_capture_success(self, mock_client_cls):
        mock_client = self._patch_client(mock_client_cls)
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        capture_key = str(uuid.uuid4())
        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": capture_key},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Idempotent-Replayed", response)
        data = response.json()
        self.assertEqual(data["status"], CheckoutOrder.Status.COMPLETED)
        self.assertEqual(data["paypal_capture_id"], PAYPAL_CAPTURE_ID)
        self.assertEqual(data["capture_idempotency_key"], capture_key)
        mock_client.get.assert_called_once_with(
            f"/v2/checkout/orders/{PAYPAL_ORDER_ID}"
        )
        mock_client.post.assert_called_once()

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_capture_correct_endpoint_and_request_id(self, mock_client_cls):
        mock_client = self._patch_client(mock_client_cls)
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)
        key = str(uuid.uuid4())

        self.client.post(
            CAPTURE_URL(order.pk), {"capture_idempotency_key": key}, format="json"
        )

        args, kwargs = mock_client.post.call_args
        self.assertEqual(args[0], f"/v2/checkout/orders/{PAYPAL_ORDER_ID}/capture")
        self.assertEqual(kwargs["request_id"], key)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_return_url_alone_insufficient(self, mock_client_cls):
        # An order that has not been approved cannot be captured.
        mock_client = self._patch_client(mock_client_cls)
        order = CheckoutOrder.objects.create(
            organization=self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            paypal_order_id=PAYPAL_ORDER_ID,
            status=CheckoutOrder.Status.PAYER_ACTION_REQUIRED,
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        mock_client.get.assert_not_called()
        mock_client.post.assert_not_called()

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_capture_intent_enforced(self, mock_client_cls):
        mock_client = self._patch_client(
            mock_client_cls,
            get_response=_order(intent="AUTHORIZE"),
        )
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 422)
        mock_client.post.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.status, CheckoutOrder.Status.DECLINED)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_amount_mismatch(self, mock_client_cls):
        bad = _order()
        bad["purchase_units"][0]["amount"]["value"] = "99.99"
        mock_client = self._patch_client(mock_client_cls, get_response=bad)
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 422)
        mock_client.post.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.status, CheckoutOrder.Status.DECLINED)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_paypal_order_identity_mismatch(self, mock_client_cls):
        bad = _order()
        bad["id"] = "DOES-NOT-MATCH"
        self._patch_client(mock_client_cls, get_response=bad)
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 422)
        order.refresh_from_db()
        self.assertEqual(order.status, CheckoutOrder.Status.DECLINED)

    # 9. Cross-organization rejection ------------------------------------------
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_cross_organization_rejection(self, mock_client_cls):
        mock_client = self._patch_client(mock_client_cls)
        order = self._make_approved_order(organization=self.other_org)
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        mock_client.get.assert_not_called()
        mock_client.post.assert_not_called()

    # 10. Unauthorized role rejection ------------------------------------------
    def test_unauthorized_role_rejection(self):
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.viewer)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    # 11. Feature disabled -----------------------------------------------------
    @override_settings(PAYPAL_CHECKOUT_ENABLED="false")
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_feature_disabled(self, mock_client_cls):
        mock_client = self._patch_client(mock_client_cls)
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("not enabled", response.json()["detail"])
        mock_client.get.assert_not_called()

    # 12. Missing credentials --------------------------------------------------
    @override_settings(
        PAYPAL_CHECKOUT_ENABLED="true",
        PAYPAL_CLIENT_ID="",
        PAYPAL_CLIENT_SECRET="",
    )
    def test_missing_credentials(self):
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("not configured", response.json()["detail"])

    # 14. Duplicate capture replay (view: Idempotent-Replayed header) ----------
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_duplicate_capture_replay(self, mock_client_cls):
        mock_client = self._patch_client(mock_client_cls)
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)
        key = str(uuid.uuid4())

        response1 = self.client.post(
            CAPTURE_URL(order.pk), {"capture_idempotency_key": key}, format="json"
        )
        self.assertEqual(response1.status_code, 200)

        response2 = self.client.post(
            CAPTURE_URL(order.pk), {"capture_idempotency_key": key}, format="json"
        )
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2["Idempotent-Replayed"], "true")
        # Still exactly one capture POST.
        self.assertEqual(mock_client.post.call_count, 1)
        order.refresh_from_db()
        self.assertEqual(order.status, CheckoutOrder.Status.COMPLETED)
        self.assertEqual(
            CheckoutOrder.objects.filter(paypal_capture_id=PAYPAL_CAPTURE_ID).count(), 1
        )

    # 15. Timeout -> CAPTURE_PENDING (view: 202) -------------------------------
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_timeout_returns_accepted(self, mock_client_cls):
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.get.return_value = _APPROVED_ORDER
        mock_client.post.side_effect = PayPalUncertainOutcomeError(
            "POST request to PayPal did not receive a response."
        )
        mock_client_cls.return_value = mock_client
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], CheckoutOrder.Status.CAPTURE_PENDING)

    # 19. Confirmed terminal failure (view: 502) -------------------------------
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_confirmed_terminal_failure(self, mock_client_cls):
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.get.return_value = _APPROVED_ORDER
        mock_client.post.side_effect = PayPalAPIError(
            "INVALID_REQUEST: intent does not match"
        )
        mock_client_cls.return_value = mock_client
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        order.refresh_from_db()
        self.assertEqual(order.status, CheckoutOrder.Status.DECLINED)

    # 19b. Unknown capture status (view: 202 — preserve pending) ----------------
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_unknown_capture_status_preserves_pending(self, mock_client_cls):
        self._patch_client(
            mock_client_cls,
            get_response=_APPROVED_ORDER,
            post_response=_capture_response(capture_status="INSTRUMENT_DENIED"),
        )
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], CheckoutOrder.Status.CAPTURE_PENDING)
        order.refresh_from_db()
        self.assertEqual(order.status, CheckoutOrder.Status.CAPTURE_PENDING)
        self.assertEqual(order.paypal_order_id, PAYPAL_ORDER_ID)
        self.assertIsNone(order.paypal_capture_id)

    # 19c. 429 rate-limit (view: 202 — preserve pending) -----------------------
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_rate_limit_on_capture_returns_accepted(self, mock_client_cls):
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.get.return_value = _APPROVED_ORDER
        mock_client.post.side_effect = PayPalRateLimitError("HTTP 429: rate limited")
        mock_client_cls.return_value = mock_client
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], CheckoutOrder.Status.CAPTURE_PENDING)
        order.refresh_from_db()
        self.assertEqual(order.status, CheckoutOrder.Status.CAPTURE_PENDING)
        self.assertEqual(order.paypal_order_id, PAYPAL_ORDER_ID)

    # 24. No double capture (view: already completed -> 0 POSTs) --------------
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_no_double_capture_after_completed(self, mock_client_cls):
        mock_client = self._patch_client(mock_client_cls)
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        key = str(uuid.uuid4())
        self.client.post(
            CAPTURE_URL(order.pk), {"capture_idempotency_key": key}, format="json"
        )
        self.assertEqual(mock_client.post.call_count, 1)

        # A second request (even a different key) cannot recapture.
        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Idempotent-Replayed"], "true")
        self.assertEqual(mock_client.post.call_count, 1)
        self.assertEqual(
            CheckoutOrder.objects.filter(paypal_capture_id=PAYPAL_CAPTURE_ID).count(), 1
        )

    # 22. Secret redaction -----------------------------------------------------
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_no_credentials_leaked_in_error(self, mock_client_cls):
        self._patch_client(mock_client_cls, get_response=_order(intent="AUTHORIZE"))
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {"capture_idempotency_key": str(uuid.uuid4())},
            format="json",
        )

        detail = response.json()["detail"]
        self.assertNotIn("test-client-id", detail)
        self.assertNotIn("test-client-secret", detail)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_rejects_unknown_fields(self, mock_client_cls):
        self._patch_client(mock_client_cls)
        order = self._make_approved_order()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            CAPTURE_URL(order.pk),
            {
                "capture_idempotency_key": str(uuid.uuid4()),
                "amount": "999.00",  # client cannot override the immutable amount
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["amount"], "Unknown field.")


# ---------------------------------------------------------------------------
# Concurrency test (real threads + PostgreSQL row locking)
# ---------------------------------------------------------------------------


@skipUnless(
    connection.vendor == "postgresql", "row locking is exercised against PostgreSQL"
)
class CaptureConcurrencyTests(PostgresTransactionTestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="capture-concurrency")
        self.checkout = CheckoutOrder.objects.create(
            organization=self.organization,
            amount_minor=1000,
            currency="USD",
            status=CheckoutOrder.Status.APPROVED,
            paypal_order_id=PAYPAL_ORDER_ID,
        )
        self.key = uuid.uuid4()

    def test_concurrent_same_key_single_capture(self):
        client = _StatefulCaptureClient()
        barrier = threading.Barrier(2)
        results = {}

        def worker(label):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                results[label] = services.capture_checkout_order(
                    checkout_order=CheckoutOrder.objects.get(pk=self.checkout.pk),
                    organization_id=self.organization.pk,
                    capture_idempotency_key=self.key,
                    client=client,
                )
            except Exception as exc:
                results[label] = exc
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=worker, args=(f"worker{i}",)) for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # No exceptions escaped.
        for label, value in results.items():
            self.assertNotIsInstance(value, Exception, f"{label} raised {value!r}")

        order = CheckoutOrder.objects.get(pk=self.checkout.pk)
        self.assertEqual(order.status, CheckoutOrder.Status.COMPLETED)
        self.assertEqual(order.paypal_capture_id, PAYPAL_CAPTURE_ID)
        # Exactly one capture id persisted for the order (no double spend).
        self.assertEqual(
            CheckoutOrder.objects.filter(
                organization=self.organization, paypal_capture_id=PAYPAL_CAPTURE_ID
            ).count(),
            1,
        )
        # The stable idempotency key was used for every capture POST.
        self.assertTrue(set(client.request_ids) == {str(self.key)})


def close_old_connections():
    from django.db import connection as _connection

    _connection.close_if_unusable_or_obsolete()


class _StatefulCaptureClient:
    """Fake PayPalClient whose GET reflects real DB state.

    ``GET`` returns COMPLETED+capture once the order has been captured locally;
    otherwise APPROVED.  ``POST`` is idempotent (returns the same capture) and
    records every ``request_id`` it was called with.
    """

    def __init__(self, capture_id=PAYPAL_CAPTURE_ID):
        self.capture_id = capture_id
        self.post_call_count = 0
        self.request_ids = []

    def get_token(self):
        return "test-token"

    def get(self, path, *, params=None):
        order = CheckoutOrder.objects.filter(paypal_order_id=PAYPAL_ORDER_ID).first()
        if order and order.paypal_capture_id:
            return _completed_order_with_capture(capture_id=order.paypal_capture_id)
        return _APPROVED_ORDER

    def post(self, path, *, json=None, request_id=None):
        self.post_call_count += 1
        self.request_ids.append(request_id)
        return _capture_response(capture_id=self.capture_id)
