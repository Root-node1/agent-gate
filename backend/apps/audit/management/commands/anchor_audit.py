"""Append each organization's current audit head to the external anchor store."""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Organization
from apps.audit.anchors import get_anchor_store
from apps.audit.services import anchor_organizations


class Command(BaseCommand):
    help = "Record the current audit head hash per organization in the external store."

    def add_arguments(self, parser):
        parser.add_argument(
            "--organization",
            dest="organization_id",
            help="Only anchor the organization with this UUID.",
        )

    def handle(self, *args, **options):
        anchor_store = get_anchor_store()
        if anchor_store is None:
            raise CommandError("AUDIT_ANCHOR_PATH is not configured.")

        organizations = Organization.objects.order_by("id")
        organization_id = options.get("organization_id")
        if organization_id:
            organizations = organizations.filter(pk=organization_id)
            if not organizations.exists():
                raise CommandError(f"Organization {organization_id} does not exist.")

        anchored = anchor_organizations(organizations, anchor_store)
        self.stdout.write(
            self.style.SUCCESS(f"Anchored {anchored} organization(s).")
        )
