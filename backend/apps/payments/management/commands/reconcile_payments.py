"""Reconcile stale executing payments against PayPal without retrying them."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.payments.paypal import PayPalError
from apps.payments.reconciliation import (
    DEFAULT_LIMIT,
    DEFAULT_OLDER_THAN_MINUTES,
    reconcile_payments,
)


class Command(BaseCommand):
    help = (
        "Query PayPal for executing payments older than the threshold and apply "
        "terminal results. Payments without a provider reference are reported only."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
        parser.add_argument(
            "--older-than-minutes",
            type=int,
            default=DEFAULT_OLDER_THAN_MINUTES,
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List how many payments would be checked without calling PayPal.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        older_than_minutes = options["older_than_minutes"]
        if limit < 1:
            raise CommandError("--limit must be at least 1.")
        if older_than_minutes < 0:
            raise CommandError("--older-than-minutes must not be negative.")

        try:
            summary = reconcile_payments(
                limit=limit,
                older_than_minutes=older_than_minutes,
                dry_run=options["dry_run"],
            )
        except PayPalError as exc:
            raise CommandError(str(exc)) from None

        if summary.skipped_reason == "executor_not_paypal":
            self.stdout.write("PAYMENT_EXECUTOR is not paypal; nothing to reconcile.")
            return
        if summary.dry_run:
            self.stdout.write(
                f"Would check {summary.candidates} payment(s); "
                f"{summary.unreferenced} executing payment(s) have no provider reference."
            )
            return

        self.stdout.write(
            "Reconciled payments: "
            f"checked={summary.checked} "
            f"succeeded={summary.succeeded} "
            f"failed={summary.failed} "
            f"still_executing={summary.still_executing} "
            f"skipped={summary.skipped} "
            f"errors={summary.errors} "
            f"unreferenced={summary.unreferenced}"
        )
        if summary.errors or summary.unreferenced:
            raise CommandError(
                "Some payments need operator attention; see the output above."
            )
