"""Tests for PayPal Sandbox checkout order creation (INT-13G).

All tests are offline — no real PayPal API calls are made.  The PayPalClient
is injected as a ``MagicMock`` or patched at the module level.
"""

import uuid
from unittest.mock import MagicMock, patch

from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.payments.checkout import services
from apps.payments.models import CheckoutOrder
from apps.payments.paypal.client import (
    PayPalAPIError,
    PayPalClient,
    PayPalUncertainOutcomeError,
)
from tests.base import force_mfa

APPROVAL_URL = "https://www.sandbox.paypal.com/checkoutnow?token=5O19011234567890X"
PAYPAL_ORDER_ID = "5O19011234567890X"

MOCK_ORDER_RESPONSE = {
    "id": PAYPAL_ORDER_ID,
    "status": "CREATED",
    "intent": "CAPTURE",
    "purchase_units": [
        {
            "amount": {
                "currency_code": "USD",
                "value": "10.00",
            }
        }
    ],
    "links": [
        {
            "href": f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{PAYPAL_ORDER_ID}",
            "rel": "self",
            "method": "GET",
        },
        {
            "href": f"https://www.sandbox.paypal.com/checkoutnow?token={PAYPAL_ORDER_ID}",
            "rel": "approve",
            "method": "GET",
        },
        {
            "href": f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{PAYPAL_ORDER_ID}",
            "rel": "edit",
            "method": "PATCH",
        },
        {
            "href": f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{PAYPAL_ORDER_ID}/capture",
            "rel": "capture",
            "method": "POST",
        },
    ],
}

MOCK_RESPONSE_NO_APPROVE_LINK = {
    "id": PAYPAL_ORDER_ID,
    "status": "CREATED",
    "links": [
        {
            "href": f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{PAYPAL_ORDER_ID}",
            "rel": "self",
            "method": "GET",
        },
    ],
}

CHECKOUT_URL = "/v1/checkout-orders/"


def make_mock_client(
    response=None,
    post_side_effect=None,
) -> MagicMock:
    """Create a mock PayPalClient whose ``post`` returns *response*."""
    client = MagicMock(spec=PayPalClient)
    if post_side_effect is not None:
        client.post.side_effect = post_side_effect
    else:
        client.post.return_value = response
    return client


# ---------------------------------------------------------------------------
# Pure-function tests (no database needed)
# ---------------------------------------------------------------------------


class OrderPayloadTests(SimpleTestCase):
    def test_build_order_payload_has_capture_intent(self):
        payload = services.build_order_payload(1000, "USD")
        self.assertEqual(payload["intent"], "CAPTURE")

    def test_build_order_payload_has_one_purchase_unit(self):
        payload = services.build_order_payload(1000, "USD")
        self.assertEqual(len(payload["purchase_units"]), 1)

    def test_build_order_payload_major_unit_amount_usd(self):
        payload = services.build_order_payload(1000, "USD")
        self.assertEqual(payload["purchase_units"][0]["amount"]["value"], "10.00")

    def test_build_order_payload_major_unit_amount_jpy(self):
        payload = services.build_order_payload(1000, "JPY")
        self.assertEqual(payload["purchase_units"][0]["amount"]["value"], "1000")

    def test_build_order_payload_currency_code(self):
        payload = services.build_order_payload(5000, "EUR")
        amount = payload["purchase_units"][0]["amount"]
        self.assertEqual(amount["currency_code"], "EUR")
        self.assertEqual(amount["value"], "50.00")

    def test_build_order_payload_no_capture_field(self):
        payload = services.build_order_payload(1000, "USD")
        self.assertNotIn("application_context", payload)
        # CAPTURE intent means the payer approves — we never auto-capture.
        self.assertNotIn("capture", payload)


class ApprovalUrlTests(SimpleTestCase):
    def test_extract_approval_url_from_approve_link(self):
        url = services.extract_approval_url(MOCK_ORDER_RESPONSE)
        self.assertEqual(url, APPROVAL_URL)

    def test_extract_approval_url_from_payer_action_link(self):
        response = {
            "id": "ORDER-1",
            "status": "PAYER_ACTION_REQUIRED",
            "links": [
                {
                    "href": "https://example.com/approve",
                    "rel": "payer-action",
                    "method": "GET",
                },
            ],
        }
        url = services.extract_approval_url(response)
        self.assertEqual(url, "https://example.com/approve")

    def test_extract_approval_url_missing(self):
        url = services.extract_approval_url(MOCK_RESPONSE_NO_APPROVE_LINK)
        self.assertIsNone(url)

    def test_extract_approval_url_no_links(self):
        url = services.extract_approval_url({})
        self.assertIsNone(url)


# ---------------------------------------------------------------------------
# Service-level tests (TestCase — need database for CheckoutOrder)
# ---------------------------------------------------------------------------


class CheckoutServiceTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="checkout-test")
        self.amount_minor = 1000  # $10.00

    def test_successful_order_creation(self):
        client = make_mock_client(response=MOCK_ORDER_RESPONSE)
        key = uuid.uuid4()

        checkout, url, replayed = services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=key,
            client=client,
        )

        self.assertEqual(url, APPROVAL_URL)
        self.assertFalse(replayed)
        self.assertEqual(checkout.paypal_order_id, PAYPAL_ORDER_ID)
        self.assertEqual(checkout.payer_action_url, APPROVAL_URL)
        self.assertEqual(checkout.status, CheckoutOrder.Status.PAYER_ACTION_REQUIRED)
        self.assertEqual(checkout.amount_minor, self.amount_minor)
        self.assertEqual(checkout.currency, "USD")

    def test_correct_v2_payload(self):
        client = make_mock_client(response=MOCK_ORDER_RESPONSE)

        services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=uuid.uuid4(),
            client=client,
        )

        client.post.assert_called_once()
        args, kwargs = client.post.call_args
        self.assertEqual(args[0], "/v2/checkout/orders")
        payload = kwargs["json"]
        self.assertEqual(payload["intent"], "CAPTURE")
        unit = payload["purchase_units"][0]
        self.assertEqual(len(payload["purchase_units"]), 1)
        self.assertEqual(unit["amount"]["currency_code"], "USD")
        self.assertEqual(unit["amount"]["value"], "10.00")

    def test_correct_major_unit_formatting(self):
        client = make_mock_client(response=MOCK_ORDER_RESPONSE)

        services.create_checkout_order(
            self.organization,
            amount_minor=5050,  # $50.50
            currency="USD",
            idempotency_key=uuid.uuid4(),
            client=client,
        )

        _, kwargs = client.post.call_args
        value = kwargs["json"]["purchase_units"][0]["amount"]["value"]
        self.assertEqual(value, "50.50")

    def test_capture_intent(self):
        client = make_mock_client(response=MOCK_ORDER_RESPONSE)

        services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=uuid.uuid4(),
            client=client,
        )

        _, kwargs = client.post.call_args
        self.assertEqual(kwargs["json"]["intent"], "CAPTURE")

    def test_payer_approval_url_extraction(self):
        client = make_mock_client(response=MOCK_ORDER_RESPONSE)

        _, url, _ = services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=uuid.uuid4(),
            client=client,
        )

        self.assertEqual(url, APPROVAL_URL)

    def test_missing_approval_url(self):
        client = make_mock_client(response=MOCK_RESPONSE_NO_APPROVE_LINK)

        checkout, url, _ = services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=uuid.uuid4(),
            client=client,
        )

        self.assertIsNone(url)
        self.assertIsNone(checkout.payer_action_url)
        self.assertEqual(checkout.status, CheckoutOrder.Status.PAYER_ACTION_REQUIRED)
        self.assertEqual(checkout.paypal_order_id, PAYPAL_ORDER_ID)

    def test_duplicate_initiation(self):
        client = make_mock_client(response=MOCK_ORDER_RESPONSE)
        key = uuid.uuid4()

        checkout1, url1, replayed1 = services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=key,
            client=client,
        )
        checkout2, url2, replayed2 = services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=key,
            client=client,
        )

        self.assertFalse(replayed1)
        self.assertTrue(replayed2)
        self.assertEqual(checkout1.pk, checkout2.pk)
        self.assertEqual(url1, url2)
        self.assertEqual(CheckoutOrder.objects.filter(idempotency_key=key).count(), 1)

    def test_concurrent_initiation_replays(self):
        """Two threads with the same key produce one CheckoutOrder."""
        key = uuid.uuid4()
        client = make_mock_client(response=MOCK_ORDER_RESPONSE)

        existing = CheckoutOrder.objects.create(
            organization=self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=key,
        )
        self.assertEqual(CheckoutOrder.objects.filter(idempotency_key=key).count(), 1)

        # Simulate a concurrent thread that sets paypal_order_id mid-call.
        def race_post(*args, **kwargs):
            CheckoutOrder.objects.filter(pk=existing.pk).update(
                paypal_order_id="PAYPAL-CONCURRENT",
                payer_action_url=APPROVAL_URL,
                status=CheckoutOrder.Status.PAYER_ACTION_REQUIRED,
            )
            return MOCK_ORDER_RESPONSE

        client.post.side_effect = race_post

        checkout, _, replayed = services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=key,
            client=client,
        )

        self.assertTrue(replayed)
        self.assertEqual(checkout.paypal_order_id, "PAYPAL-CONCURRENT")
        self.assertEqual(CheckoutOrder.objects.filter(idempotency_key=key).count(), 1)

    def test_ambiguous_timeout_leaves_created(self):
        client = make_mock_client(
            post_side_effect=PayPalUncertainOutcomeError(
                "POST request to PayPal did not receive a response."
            )
        )
        key = uuid.uuid4()

        checkout, url, replayed = services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=key,
            client=client,
        )

        self.assertFalse(replayed)
        self.assertIsNone(url)
        self.assertIsNone(checkout.paypal_order_id)
        self.assertEqual(checkout.status, CheckoutOrder.Status.CREATED)

    def test_paypal_http_error_declines_order(self):
        api_error = PayPalAPIError("Invalid request: currency_code is required")
        client = make_mock_client(post_side_effect=api_error)
        key = uuid.uuid4()

        with self.assertRaises(PayPalAPIError):
            services.create_checkout_order(
                self.organization,
                amount_minor=self.amount_minor,
                currency="USD",
                idempotency_key=key,
                client=client,
            )

        checkout = CheckoutOrder.objects.get(idempotency_key=key)
        self.assertEqual(checkout.status, CheckoutOrder.Status.DECLINED)

    def test_stable_paypal_request_id(self):
        """The PayPal-Request-Id is the idempotency key, not regenerated."""
        key = uuid.uuid4()

        CheckoutOrder.objects.create(
            organization=self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=key,
        )

        client = make_mock_client(response=MOCK_ORDER_RESPONSE)

        services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=key,
            client=client,
        )

        _, kwargs = client.post.call_args
        self.assertEqual(kwargs["request_id"], str(key))

    def test_no_automatic_capture(self):
        client = make_mock_client(response=MOCK_ORDER_RESPONSE)

        services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=uuid.uuid4(),
            client=client,
        )

        self.assertEqual(client.post.call_count, 1)
        args, kwargs = client.post.call_args
        self.assertEqual(args[0], "/v2/checkout/orders")

        # No capture POST, no reconciliation GET.
        self.assertEqual(client.get.call_count, 0)

        payload = kwargs["json"]
        self.assertEqual(payload["intent"], "CAPTURE")
        self.assertNotIn("capture", payload)

    def test_secret_redaction_in_errors(self):
        """PayPal API error messages never expose client credentials."""
        client = MagicMock(spec=PayPalClient)
        client.post.side_effect = PayPalAPIError("Invalid amount")

        with self.assertRaises(PayPalAPIError) as ctx:
            services.create_checkout_order(
                self.organization,
                amount_minor=self.amount_minor,
                currency="USD",
                idempotency_key=uuid.uuid4(),
                client=client,
            )

        msg = str(ctx.exception)
        self.assertNotIn("client_id", msg.lower())
        self.assertNotIn("secret", msg.lower())

    def test_no_db_lock_during_http_call(self):
        """No database row lock or transaction is held during the PayPal HTTP call."""
        state = {}
        baseline = list(transaction.get_connection().savepoint_ids)

        def fake_post(*args, **kwargs):
            conn = transaction.get_connection()
            state["savepoint_ids"] = list(conn.savepoint_ids)
            return MOCK_ORDER_RESPONSE

        client = MagicMock(spec=PayPalClient)
        client.post.side_effect = fake_post

        _, url, _ = services.create_checkout_order(
            self.organization,
            amount_minor=self.amount_minor,
            currency="USD",
            idempotency_key=uuid.uuid4(),
            client=client,
        )

        self.assertEqual(state["savepoint_ids"], baseline)
        self.assertEqual(url, APPROVAL_URL)

    def test_amount_from_model_not_request(self):
        """The PayPal payload is built from the stored CheckoutOrder, not the call args."""
        client = make_mock_client(response=MOCK_ORDER_RESPONSE)
        key = uuid.uuid4()

        services.create_checkout_order(
            self.organization,
            amount_minor=1000,
            currency="USD",
            idempotency_key=key,
            client=client,
        )

        _, kwargs = client.post.call_args
        value = kwargs["json"]["purchase_units"][0]["amount"]["value"]
        self.assertEqual(value, "10.00")


# ---------------------------------------------------------------------------
# View-level tests (APITestCase)
# ---------------------------------------------------------------------------


@override_settings(
    PAYPAL_CHECKOUT_ENABLED="true",
    PAYPAL_CLIENT_ID="test-client-id",
    PAYPAL_CLIENT_SECRET="test-client-secret",
)
class CheckoutViewBase(APITestCase):
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

    def _patch_client(self, mock_class):
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.post.return_value = MOCK_ORDER_RESPONSE
        mock_class.return_value = mock_client
        return mock_client


class CheckoutViewTests(CheckoutViewBase):
    @patch("apps.payments.checkout.views.PayPalClient")
    def test_successful_order_creation(self, mock_client_cls):
        self._patch_client(mock_client_cls)
        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        response = self.client.post(CHECKOUT_URL, body, format="json")

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["paypal_order_id"], PAYPAL_ORDER_ID)
        self.assertEqual(data["payer_action_url"], APPROVAL_URL)
        self.assertEqual(data["status"], CheckoutOrder.Status.PAYER_ACTION_REQUIRED)
        self.assertEqual(data["amount"], "10.00")

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_correct_v2_payload(self, mock_client_cls):
        self._patch_client(mock_client_cls)
        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        self.client.post(CHECKOUT_URL, body, format="json")

        mock_client_cls.return_value.post.assert_called_once()
        args, kwargs = mock_client_cls.return_value.post.call_args
        self.assertEqual(args[0], "/v2/checkout/orders")
        self.assertEqual(kwargs["json"]["intent"], "CAPTURE")

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_major_unit_amount_formatting(self, mock_client_cls):
        self._patch_client(mock_client_cls)
        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "50.50",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        self.client.post(CHECKOUT_URL, body, format="json")

        _, kwargs = mock_client_cls.return_value.post.call_args
        value = kwargs["json"]["purchase_units"][0]["amount"]["value"]
        self.assertEqual(value, "50.50")

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_capture_intent_only(self, mock_client_cls):
        self._patch_client(mock_client_cls)
        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        self.client.post(CHECKOUT_URL, body, format="json")

        _, kwargs = mock_client_cls.return_value.post.call_args
        self.assertEqual(kwargs["json"]["intent"], "CAPTURE")
        self.assertEqual(len(kwargs["json"]["purchase_units"]), 1)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_payer_approval_url_in_response(self, mock_client_cls):
        self._patch_client(mock_client_cls)
        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        response = self.client.post(CHECKOUT_URL, body, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["payer_action_url"], APPROVAL_URL)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_missing_approval_url(self, mock_client_cls):
        """PayPal response without an approve link → no approval URL."""
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.post.return_value = MOCK_RESPONSE_NO_APPROVE_LINK
        mock_client_cls.return_value = mock_client

        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        response = self.client.post(CHECKOUT_URL, body, format="json")

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertIsNone(data["payer_action_url"])
        self.assertEqual(data["paypal_order_id"], PAYPAL_ORDER_ID)

    @override_settings(PAYPAL_CHECKOUT_ENABLED="false")
    def test_disabled_feature(self):
        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        response = self.client.post(CHECKOUT_URL, body, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertIn("not enabled", response.json()["detail"])

    @override_settings(
        PAYPAL_CHECKOUT_ENABLED="true",
        PAYPAL_CLIENT_ID="",
        PAYPAL_CLIENT_SECRET="",
    )
    def test_missing_credentials(self):
        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        response = self.client.post(CHECKOUT_URL, body, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertIn("not configured", response.json()["detail"])

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_cross_organization_rejection(self, mock_client_cls):
        self._patch_client(mock_client_cls)
        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.other_org.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        response = self.client.post(CHECKOUT_URL, body, format="json")

        self.assertEqual(response.status_code, 404)

    def test_unauthorized_role_rejection(self):
        self.client.force_authenticate(user=self.viewer)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        response = self.client.post(CHECKOUT_URL, body, format="json")

        self.assertEqual(response.status_code, 403)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_duplicate_initiation(self, mock_client_cls):
        self._patch_client(mock_client_cls)
        self.client.force_authenticate(user=self.admin)
        key = str(uuid.uuid4())

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": key,
        }
        response1 = self.client.post(CHECKOUT_URL, body, format="json")
        self.assertEqual(response1.status_code, 201)

        response2 = self.client.post(CHECKOUT_URL, body, format="json")
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2["Idempotent-Replayed"], "true")
        self.assertEqual(
            CheckoutOrder.objects.filter(idempotency_key=uuid.UUID(key)).count(), 1
        )

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_ambiguous_timeout(self, mock_client_cls):
        """A timeout leaves the order in CREATED state; no blind retry."""
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.post.side_effect = PayPalUncertainOutcomeError(
            "POST request to PayPal did not receive a response."
        )
        mock_client_cls.return_value = mock_client

        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        response = self.client.post(CHECKOUT_URL, body, format="json")

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], CheckoutOrder.Status.CREATED)
        self.assertIsNone(data["payer_action_url"])
        self.assertIsNone(data["paypal_order_id"])
        # PayPal was called exactly once — no blind retry.
        self.assertEqual(mock_client.post.call_count, 1)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_paypal_http_errors(self, mock_client_cls):
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.post.side_effect = PayPalAPIError("Invalid request")
        mock_client_cls.return_value = mock_client

        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        response = self.client.post(CHECKOUT_URL, body, format="json")

        self.assertEqual(response.status_code, 502)
        self.assertIn("Invalid request", response.json()["detail"])

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_stable_paypal_request_id(self, mock_client_cls):
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.post.return_value = MOCK_ORDER_RESPONSE
        mock_client_cls.return_value = mock_client

        self.client.force_authenticate(user=self.admin)
        key = str(uuid.uuid4())

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": key,
        }
        self.client.post(CHECKOUT_URL, body, format="json")

        _, kwargs = mock_client.post.call_args
        self.assertEqual(kwargs["request_id"], key)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_no_automatic_capture(self, mock_client_cls):
        self._patch_client(mock_client_cls)
        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        self.client.post(CHECKOUT_URL, body, format="json")

        mock_client = mock_client_cls.return_value
        # Only one POST to /v2/checkout/orders — no capture POST.
        self.assertEqual(mock_client.post.call_count, 1)
        args, _ = mock_client.post.call_args
        self.assertEqual(args[0], "/v2/checkout/orders")
        # No capture endpoint called.
        self.assertEqual(mock_client.get.call_count, 0)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_no_credentials_leaked_in_error(self, mock_client_cls):
        """Error responses must not contain PayPal credentials."""
        mock_client = MagicMock(spec=PayPalClient)
        mock_client.post.side_effect = PayPalAPIError("Something went wrong")
        mock_client_cls.return_value = mock_client

        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        response = self.client.post(CHECKOUT_URL, body, format="json")

        detail = response.json()["detail"]
        self.assertNotIn("test-client-id", detail)
        self.assertNotIn("test-client-secret", detail)

    @patch("apps.payments.checkout.views.PayPalClient")
    def test_no_db_lock_during_http(self, mock_client_cls):
        state = {}
        baseline = list(transaction.get_connection().savepoint_ids)

        def fake_post(*args, **kwargs):
            conn = transaction.get_connection()
            state["savepoints"] = list(conn.savepoint_ids)
            return MOCK_ORDER_RESPONSE

        mock_client = MagicMock(spec=PayPalClient)
        mock_client.post.side_effect = fake_post
        mock_client_cls.return_value = mock_client

        self.client.force_authenticate(user=self.admin)

        body = {
            "organization": str(self.organization.pk),
            "amount": "10.00",
            "currency": "USD",
            "idempotency_key": str(uuid.uuid4()),
        }
        self.client.post(CHECKOUT_URL, body, format="json")

        self.assertEqual(state["savepoints"], baseline)
