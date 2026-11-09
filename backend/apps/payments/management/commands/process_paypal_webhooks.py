"""Process verified PayPal webhook inbox events."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.payments.webhook_processing import process_webhook_events


class Command(BaseCommand):
    help = "Process verified PayPal Sandbox webhook inbox events."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100, help="Maximum events per run")

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be at least 1.")
        results = process_webhook_events(limit=limit, django_settings=settings)
        self.stdout.write(self.style.SUCCESS(f"Processed {len(results)} event(s)."))
