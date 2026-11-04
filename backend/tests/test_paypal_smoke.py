from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from apps.payments.paypal import (
    PayPalAuthenticationError,
    PayPalResponseError,
    PayPalTimeoutError,
)

SANDBOX = {
    "PAYPAL_MODE": "sandbox",
    "PAYPAL_CLIENT_ID": "client-id",
    "PAYPAL_CLIENT_SECRET": "secret",
}
COMMAND = "apps.payments.management.commands.paypal_smoke"


class StubClient:
    def __init__(self, *, error=None, batch_id="B-1", status="SUCCESS"):
        self.error = error
        self.batch_id = batch_id
        self.status = status
        self.closed = False
        self.calls = []

    def post_json(self, path, *, body, request_id):
        self.calls.append((path, body, request_id))
        if self.error is not None:
            raise self.error
        return {
            "batch_header": {
                "payout_batch_id": self.batch_id,
                "batch_status": self.status,
            }
        }

    def close(self):
        self.closed = True


@override_settings(**SANDBOX)
class PayPalSmokeCommandTests(SimpleTestCase):
    def run_command(self, **options):
        output = StringIO()
        options.setdefault("receiver", "payee@example.com")
        options.setdefault("stdout", output)
        call_command("paypal_smoke", **options)
        return output.getvalue()

    def test_dry_run_prints_the_payload_without_calling_paypal(self):
        with patch(f"{COMMAND}.build_paypal_client") as build:
            output = self.run_command()

        build.assert_not_called()
        self.assertIn("Dry run", output)
        self.assertIn('"sender_batch_id"', output)
        self.assertIn("payee@example.com", output)

    def test_live_mode_is_refused(self):
        with override_settings(PAYPAL_MODE="live"):
            with self.assertRaises(CommandError) as raised:
                self.run_command()
        self.assertIn("sandbox", str(raised.exception))

    def test_missing_credentials_are_refused(self):
        with override_settings(PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET=""):
            with self.assertRaises(CommandError):
                self.run_command()

    def test_invalid_amount_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_command(amount="0")

    def test_successful_probe_prints_the_batch(self):
        client = StubClient(batch_id="B-99", status="SUCCESS")
        with patch(f"{COMMAND}.build_paypal_client", return_value=client):
            output = self.run_command(confirm=True, amount="1.23")

        self.assertTrue(client.closed)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][0], "/v1/payments/payouts")
        self.assertEqual(
            client.calls[0][1]["items"][0]["amount"],
            {"value": "1.23", "currency": "USD"},
        )
        self.assertIn("B-99", output)

    def test_failure_probe_accepts_a_rejection(self):
        client = StubClient(
            error=PayPalResponseError("bad", status_code=422, code="BAD_RECEIVER")
        )
        with patch(f"{COMMAND}.build_paypal_client", return_value=client):
            output = self.run_command(confirm=True, failure=True, receiver="invalid")

        self.assertTrue(client.closed)
        self.assertIn("rejected the probe as expected", output)

    def test_failure_probe_does_not_treat_auth_errors_as_expected(self):
        client = StubClient(
            error=PayPalResponseError("bad", status_code=401, code="AUTH")
        )
        with patch(f"{COMMAND}.build_paypal_client", return_value=client):
            with self.assertRaises(CommandError):
                self.run_command(confirm=True, failure=True, receiver="invalid")

    def test_failure_probe_errors_if_paypal_accepts(self):
        client = StubClient(batch_id="B-1", status="SUCCESS")
        with patch(f"{COMMAND}.build_paypal_client", return_value=client):
            with self.assertRaises(CommandError) as raised:
                self.run_command(confirm=True, failure=True, receiver="invalid")

        self.assertIn("accepted unexpectedly", str(raised.exception))

    def test_ambiguous_outcome_is_not_retried(self):
        client = StubClient(error=PayPalTimeoutError("slow"))
        with patch(f"{COMMAND}.build_paypal_client", return_value=client):
            with self.assertRaises(CommandError) as raised:
                self.run_command(confirm=True)

        self.assertIn("Do not retry blindly", str(raised.exception))

    def test_authentication_failure_is_reported(self):
        client = StubClient(error=PayPalAuthenticationError("bad credentials"))
        with patch(f"{COMMAND}.build_paypal_client", return_value=client):
            with self.assertRaises(CommandError):
                self.run_command(confirm=True)
