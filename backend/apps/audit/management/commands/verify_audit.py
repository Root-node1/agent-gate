"""Verify the audit hash chain for every organization."""

from django.core.management.base import BaseCommand, CommandError

from apps.audit.services import AuditChainBroken, verify_all


class Command(BaseCommand):
    help = "Recompute the audit hash chain and report the first broken event."

    def handle(self, *args, **options):
        try:
            checked = verify_all()
        except AuditChainBroken as exc:
            raise CommandError(
                f"Audit chain broken at event {exc.event_id} for "
                f"{exc.organization_name}: {exc.reason}."
            ) from None
        self.stdout.write(self.style.SUCCESS(f"Audit chain verified: {checked} event(s)."))
