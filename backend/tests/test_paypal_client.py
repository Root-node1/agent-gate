"""INT-13F: offline tests for the sandbox PayPal OAuth HTTP client.

No PayPal API calls are made. Every HTTP interaction is driven through an
injected mock ``requests.Session`` so the tests are fully deterministic and
network-free.
"""

import base64
import json
from unittest.mock import MagicMock, patch

import requests
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from apps.payments.paypal.client import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    PayPalAPIError,
    PayPalClient,
    PayPalConfigError,
    PayPalConflictError,
    PayPalConnectionError,
    PayPalForbiddenError,
    PayPalNotFoundError,
    PayPalRateLimitError,
    PayPalRedirectError,
    PayPalServerError,
    PayPalTimeoutError,
    PayPalTokenError,
    PayPalUnauthorizedError,
    PayPalUncertainOutcomeError,
)
from apps.payments.paypal.config import SANDBOX_API_BASE_URL

# Deterministic test-only values — never used in production configuration.
CLIENT_ID = "test-client-id-12345"
CLIENT_SECRET = "test-client-secret-67890"


def _make_client(session, **kwargs):
    """Build a PayPalClient with deterministic test credentials and no retries."""
    kwargs.setdefault("max_retries", 0)
    return PayPalClient(
        CLIENT_ID,
        CLIENT_SECRET,
        session=session,
        **kwargs,
    )


def _resp(
    status=200,
    json_data=None,
    *,
    reason="OK",
    headers=None,
    json_side_effect=None,
):
    """Build a stand-in for ``requests.Response``."""
    r = MagicMock()
    r.status_code = status
    r.reason = reason
    r.headers = headers or {}
    if json_side_effect is not None:
        r.json.side_effect = json_side_effect
    elif json_data is not None:
        r.json.return_value = json_data
    else:
        r.json.return_value = {}
    return r


def _token_response(token="ACCESS-TOKEN-abc", expires_in=3600, **extra):
    body = {"access_token": token, "token_type": "Bearer", "expires_in": expires_in}
    body.update(extra)
    return _resp(json_data=body)


class PayPalClientOAuthTests(SimpleTestCase):
    """Tests 1-4 — token endpoint construction, auth, caching, refresh."""

    def test_oauth_token_request_construction(self):
        session = MagicMock()
        session.request.return_value = _token_response()
        client = _make_client(session)
        client.get_token()

        call = session.request.call_args
        self.assertEqual(call.args[0], "POST")
        self.assertEqual(
            call.args[1], f"{SANDBOX_API_BASE_URL}/v1/oauth2/token"
        )
        self.assertEqual(call.kwargs["data"], {"grant_type": "client_credentials"})
        self.assertEqual(call.kwargs["timeout"], (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT))
        self.assertFalse(call.kwargs["allow_redirects"])

    def test_oauth_uses_http_basic_auth(self):
        session = MagicMock()
        session.request.return_value = _token_response()
        client = _make_client(session)
        client.get_token()

        headers = session.request.call_args.kwargs["headers"]
        expected = "Basic " + base64.b64encode(
            f"{CLIENT_ID}:{CLIENT_SECRET}".encode("utf-8")
        ).decode("ascii")
        self.assertEqual(headers["Authorization"], expected)
        self.assertEqual(
            headers["Content-Type"], "application/x-www-form-urlencoded"
        )

    def test_token_is_cached_across_calls(self):
        session = MagicMock()
        session.request.return_value = _token_response(token="T-1")
        client = _make_client(session)

        self.assertEqual(client.get_token(), "T-1")
        self.assertEqual(client.get_token(), "T-1")
        self.assertEqual(session.request.call_count, 1)

    def test_expired_token_is_refreshed(self):
        session = MagicMock()
        session.request.side_effect = [
            _token_response(token="T-OLD", expires_in=0),
            _token_response(token="T-NEW", expires_in=0),
        ]
        client = _make_client(session)

        self.assertEqual(client.get_token(), "T-OLD")
        self.assertEqual(client.get_token(), "T-NEW")
        self.assertEqual(session.request.call_count, 2)

    def test_token_without_access_token_raises(self):
        session = MagicMock()
        session.request.return_value = _resp(json_data={"token_type": "Bearer"})
        client = _make_client(session)
        with self.assertRaises(PayPalTokenError):
            client.get_token()


class PayPalClientTransportTests(SimpleTestCase):
    """Tests 5-10, 14, 16-17 — authenticated transport, errors, redirects."""

    def test_get_sends_bearer_token_and_returns_json(self):
        session = MagicMock()
        session.request.return_value = _resp(json_data={"order_id": "123"})
        client = _make_client(session)
        client.get_token = MagicMock(return_value="BEARER-TOKEN")

        result = client.get("/v2/checkout/orders/123")

        self.assertEqual(result, {"order_id": "123"})
        call = session.request.call_args
        self.assertEqual(call.args[0], "GET")
        self.assertEqual(call.args[1], f"{SANDBOX_API_BASE_URL}/v2/checkout/orders/123")
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer BEARER-TOKEN")
        self.assertNotIn("PayPal-Request-Id", call.kwargs["headers"])

    def test_post_sends_bearer_token_and_json_body(self):
        session = MagicMock()
        session.request.return_value = _resp(status=201, json_data={"order_id": "NEW"})
        client = _make_client(session)
        client.get_token = MagicMock(return_value="BEARER-TOKEN")

        result = client.post(
            "/v2/checkout/orders", json={"intent": "CAPTURE"}, request_id="REQ-1"
        )

        self.assertEqual(result, {"order_id": "NEW"})
        call = session.request.call_args
        self.assertEqual(call.args[0], "POST")
        self.assertEqual(call.args[1], f"{SANDBOX_API_BASE_URL}/v2/checkout/orders")
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer BEARER-TOKEN")
        self.assertEqual(call.kwargs["headers"]["PayPal-Request-Id"], "REQ-1")
        self.assertEqual(call.kwargs["json"], {"intent": "CAPTURE"})

    def test_timeout_raises_timeout_error(self):
        session = MagicMock()
        session.request.side_effect = requests.exceptions.ConnectTimeout("boom")
        client = _make_client(session)
        client.get_token = MagicMock(return_value="T")

        with self.assertRaises(PayPalTimeoutError):
            client.get("/v2/checkout/orders")

    def test_connection_failure_raises_connection_error(self):
        session = MagicMock()
        session.request.side_effect = requests.exceptions.ConnectionError("boom")
        client = _make_client(session)
        client.get_token = MagicMock(return_value="T")

        with self.assertRaises(PayPalConnectionError):
            client.get("/v2/checkout/orders")

    def test_status_code_mapping(self):
        cases = [
            (400, PayPalAPIError),
            (401, PayPalUnauthorizedError),
            (403, PayPalForbiddenError),
            (404, PayPalNotFoundError),
            (409, PayPalConflictError),
            (429, PayPalRateLimitError),
            (500, PayPalServerError),
        ]
        for status, expected in cases:
            with self.subTest(status=status):
                session = MagicMock()
                session.request.return_value = _resp(
                    status=status,
                    json_data={"name": "ERR", "message": "msg", "debug_id": "dbg"},
                )
                client = _make_client(session)
                client.get_token = MagicMock(return_value="T")
                with self.assertRaises(expected):
                    client.get("/v2/checkout/orders")

    def test_invalid_json_response_raises_api_error(self):
        session = MagicMock()
        session.request.return_value = _resp(
            json_side_effect=json.JSONDecodeError("err", "doc", 0)
        )
        client = _make_client(session)
        client.get_token = MagicMock(return_value="T")
        with self.assertRaises(PayPalAPIError) as ctx:
            client.get("/v2/checkout/orders")
        self.assertIn("200", str(ctx.exception))

    def test_redirect_to_other_host_rejected(self):
        session = MagicMock()
        session.request.return_value = _resp(
            status=302, headers={"Location": "https://evil.example.com/x"}
        )
        client = _make_client(session)
        client.get_token = MagicMock(return_value="T")
        with self.assertRaises(PayPalRedirectError):
            client.get("/v2/checkout/orders")
        self.assertEqual(session.request.call_count, 1)


class PayPalClientSecurityTests(SimpleTestCase):
    """Tests 11-13, 15, 18 — config validation, secrets, import safety."""

    def test_missing_credentials_rejected(self):
        with self.assertRaises(PayPalConfigError):
            PayPalClient("", CLIENT_SECRET, session=MagicMock(), max_retries=0)
        with self.assertRaises(PayPalConfigError):
            PayPalClient(CLIENT_ID, "", session=MagicMock(), max_retries=0)

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="",
        PAYPAL_CLIENT_SECRET="",
        PAYPAL_WEBHOOK_ID="",
        PAYPAL_CHECKOUT_ENABLED="false",
        PAYPAL_PAYOUTS_ENABLED="false",
    )
    def test_disabled_feature_rejects_without_network(self):
        session = MagicMock()
        with self.assertRaises(PayPalConfigError):
            PayPalClient.from_settings(settings, session=session)
        self.assertEqual(session.request.call_count, 0)

    def test_production_base_url_rejected(self):
        for bad in [
            "https://api.paypal.com",
            "https://api-m.paypal.com",
            "http://api.sandbox.paypal.com",
            "https://example.com",
        ]:
            with self.subTest(base_url=bad):
                with self.assertRaises(PayPalConfigError):
                    PayPalClient(
                        CLIENT_ID,
                        CLIENT_SECRET,
                        base_url=bad,
                        session=MagicMock(),
                        max_retries=0,
                    )

    def test_absolute_and_traversal_paths_rejected(self):
        client = _make_client(MagicMock())
        with self.assertRaises(PayPalConfigError):
            client._build_url("https://evil.com/x")
        with self.assertRaises(PayPalConfigError):
            client._build_url("/v2/../etc/passwd")
        with self.assertRaises(PayPalConfigError):
            client._build_url("//evil.com/x")

    def test_secrets_never_leak_into_errors_or_repr(self):
        secret = "TOPSECRET-DO-NOT-LEAK"
        token = "ACCESS-TOKEN-DO-NOT-LEAK"
        session = MagicMock()
        session.request.return_value = _resp(
            status=401,
            json_data={"name": "AUTHENTICATION_FAILURE", "message": "invalid", "debug_id": "d"},
        )
        client = PayPalClient(
            CLIENT_ID, secret, session=session, max_retries=0
        )
        client.get_token = MagicMock(return_value=token)

        with self.assertRaises(PayPalAPIError) as ctx:
            client.get("/v2/checkout/orders")
        message = str(ctx.exception)
        self.assertNotIn(secret, message)
        self.assertNotIn(token, message)
        self.assertNotIn(secret, repr(client))
        self.assertNotIn(token, repr(client))
        # The wire header must encode the secret, never carry it in plaintext.
        header = client._basic_auth_header()
        self.assertNotIn(secret, header)
        self.assertNotIn(token, header)

    def test_no_network_at_construction_or_disabled_entry(self):
        session = MagicMock()
        client = _make_client(session)
        self.assertIsNone(client._access_token)
        self.assertEqual(session.request.call_count, 0)
        # repr works and reveals no token state beyond set/unset.
        self.assertIn("unset", repr(client))


class PayPalClientRetryTests(SimpleTestCase):
    """Tests 16-17 plus safe-op retry and ambiguous POST outcome (req. 6)."""

    def test_post_not_retried_on_server_error(self):
        session = MagicMock()
        session.request.return_value = _resp(
            status=500, json_data={"name": "INTERNAL_ERROR", "message": "x"}
        )
        client = _make_client(session)
        client.get_token = MagicMock(return_value="T")

        with self.assertRaises(PayPalUncertainOutcomeError):
            client.post("/v2/checkout/orders", json={})
        self.assertEqual(session.request.call_count, 1)

    def test_post_timeout_is_uncertain_outcome(self):
        session = MagicMock()
        session.request.side_effect = requests.exceptions.ReadTimeout("boom")
        client = _make_client(session)
        client.get_token = MagicMock(return_value="T")

        with self.assertRaises(PayPalUncertainOutcomeError):
            client.post("/v2/checkout/orders", json={})
        self.assertEqual(session.request.call_count, 1)

    def test_request_id_header_preserved_and_absent_by_default(self):
        session = MagicMock()
        session.request.return_value = _resp(status=201, json_data={})
        client = _make_client(session)
        client.get_token = MagicMock(return_value="T")

        client.post("/v2/checkout/orders", json={}, request_id="IDEM-999")
        headers = session.request.call_args.kwargs["headers"]
        self.assertEqual(headers["PayPal-Request-Id"], "IDEM-999")

        client.post("/v2/checkout/orders", json={})
        headers = session.request.call_args.kwargs["headers"]
        self.assertNotIn("PayPal-Request-Id", headers)

    def test_get_retries_on_server_error_with_bounded_backoff(self):
        session = MagicMock()
        session.request.side_effect = [
            _resp(status=500, json_data={"name": "E", "message": "m"}),
            _resp(status=500, json_data={"name": "E", "message": "m"}),
            _resp(status=200, json_data={"ok": True}),
        ]
        client = _make_client(session, max_retries=2)
        client.get_token = MagicMock(return_value="T")

        with patch("apps.payments.paypal.client.time.sleep") as sleep_mock:
            result = client.get("/v2/checkout/orders")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(session.request.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_get_does_not_retry_4xx(self):
        session = MagicMock()
        session.request.return_value = _resp(
            status=400, json_data={"name": "BAD", "message": "no"}
        )
        client = _make_client(session, max_retries=3)
        client.get_token = MagicMock(return_value="T")

        with self.assertRaises(PayPalAPIError):
            client.get("/v2/checkout/orders")
        self.assertEqual(session.request.call_count, 1)
