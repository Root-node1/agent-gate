"""Send one sandbox Payouts request to verify credentials and connectivity.

Nothing is stored in the database. The command builds the same payload the
executor uses and calls PayPal directly, so it cannot disturb spend state or
the audit log.
"""

from __future__ import annotations

import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.common.currency import normalize_currency
from apps.common.money import parse_amount, to_minor
from apps.payees.models import DestinationType
from apps.payments.executors import build_paypal_client
from apps.payments.paypal import (
    PayPalAmbiguousResponse,
    PayPalAuthenticationError,
    PayPalConfigurationError,
    PayPalError,
    PayPalResponseError,
    PayPalTimeoutError,
    PayPalTransientError,
    create_payout,
    payout_payload,
)
from apps.spend.models import SpendRequest


class Command(BaseCommand):
    help = (
        "Send one sandbox Payouts request, or a rejected probe with --failure. "
        "Run without --confirm to print the payload only."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--receiver",
            required=True,
            help="Sandbox email, phone, or PayPal id that receives the payout.",
        )
        parser.add_argument(
            "--receiver-type",
            choices=[value for value in DestinationType.values if value != DestinationType.URL],
            default=DestinationType.PAYPAL_EMAIL,
        )
        parser.add_argument("--amount", default="0.01", help="Positive decimal string.")
        parser.add_argument("--currency", default="USD")
        parser.add_argument(
            "--purpose",
            default="AgentGate sandbox smoke test",
            help="Payout note shown to the receiver.",
        )
        parser.add_argument(
            "--failure",
            action="store_true",
            help="Expect PayPal to reject the request; exit non-zero if it is accepted.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually call PayPal. Without it, only the payload is printed.",
        )

    def handle(self, *args, **options):
        if settings.PAYPAL_MODE != "sandbox":
            raise CommandError("paypal_smoke only runs with PAYPAL_MODE=sandbox.")
        if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
            raise CommandError("PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are required.")

        try:
            currency = normalize_currency(options["currency"])
        except ValidationError as exc:
            raise CommandError(exc.messages[0]) from None

        try:
            amount = parse_amount(options["amount"], currency)
        except ValueError as exc:
            raise CommandError(str(exc)) from None

        spend_request = SpendRequest(
            amount_minor=to_minor(amount, currency),
            currency=currency,
            merchant_ref="paypal-smoke",
            destination_type=options["receiver_type"],
            destination_value=options["receiver"],
            purpose=options["purpose"],
        )

        try:
            payload = payout_payload(spend_request)
        except PayPalConfigurationError as exc:
            raise CommandError(str(exc)) from None

        if not options["confirm"]:
            self.stdout.write("Dry run; add --confirm to call PayPal.")
            self.stdout.write(json.dumps(payload, indent=2))
            return

        try:
            client = build_paypal_client()
        except PayPalConfigurationError as exc:
            raise CommandError(f"PayPal configuration is invalid ({exc}).") from None

        try:
            result = create_payout(client, spend_request)
        except PayPalResponseError as exc:
            if options["failure"] and exc.status_code not in {401, 403}:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"PayPal rejected the probe as expected "
                        f"({exc.status_code}: {exc.code or 'error'})."
                    )
                )
                return
            raise CommandError(
                f"PayPal rejected the payout "
                f"({exc.status_code}: {exc.code or 'error'})."
            ) from None
        except (PayPalTimeoutError, PayPalTransientError, PayPalAmbiguousResponse) as exc:
            raise CommandError(
                f"The payout outcome is unknown ({exc}). Do not retry blindly; "
                f"reconcile by sender_batch_id {spend_request.id}."
            ) from None
        except PayPalAuthenticationError as exc:
            raise CommandError(f"PayPal authentication failed ({exc}).") from None
        except PayPalConfigurationError as exc:
            raise CommandError(f"PayPal configuration is invalid ({exc}).") from None
        except PayPalError as exc:
            raise CommandError(f"PayPal request failed ({exc}).") from None
        finally:
            client.close()

        if options["failure"]:
            raise CommandError(
                f"The failure probe was accepted unexpectedly "
                f"(batch {result.reference}, status {result.status}); "
                "money may have moved."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Sandbox payout accepted: {result.reference} ({result.status})."
            )
        )
