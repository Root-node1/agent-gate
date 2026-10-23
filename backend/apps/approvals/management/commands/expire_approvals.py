"""Mark overdue pending approvals as expired. Safe to run from cron every minute."""

from django.core.management.base import BaseCommand, CommandError

from apps.approvals.services import expire_due


class Command(BaseCommand):
    help = "Expire pending approvals whose deadline has passed."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=1_000, help="Maximum approvals per run")

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be at least 1.")
        count = expire_due(limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Expired {count} approval(s)."))
