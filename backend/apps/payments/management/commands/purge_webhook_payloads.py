"""Clear stored payloads for processed webhook events past retention."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.payments.retention import DEFAULT_BATCH_SIZE, purge_processed_webhook_payloads


class Command(BaseCommand):
    help = (
        "Clear stored payloads for processed PayPal webhook events older than the "
        "retention window. Unprocessed events and audit events are never changed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Retention window in days; defaults to WEBHOOK_RETENTION_DAYS.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help="Number of events updated per batch.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count eligible events without clearing any payload.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = settings.WEBHOOK_RETENTION_DAYS

        try:
            purged = purge_processed_webhook_payloads(
                retention_days=days,
                batch_size=options["batch_size"],
                dry_run=options["dry_run"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from None

        if options["dry_run"]:
            self.stdout.write(
                f"Would purge payloads for {purged} processed webhook event(s)."
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Purged payloads for {purged} processed webhook event(s)."
            )
        )
