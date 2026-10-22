"""Verify the audit hash chain for every organization."""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Organization
from apps.audit.chain import GENESIS_HASH, event_hash
from apps.audit.models import AuditEvent


class Command(BaseCommand):
    help = "Recompute the audit hash chain and report the first broken event."

    def handle(self, *args, **options):
        checked = 0
        for organization in Organization.objects.order_by("id"):
            previous_hash = GENESIS_HASH
            events = AuditEvent.objects.filter(organization=organization).order_by("id")
            for event in events.iterator():
                expected = event_hash(
                    prev_hash=previous_hash,
                    created_at=event.created_at,
                    event_type=event.event_type,
                    actor_type=event.actor_type,
                    actor_id=event.actor_id,
                    organization_id=event.organization_id,
                    agent_id=event.agent_id,
                    spend_request_id=event.spend_request_id,
                    payload=event.payload,
                )
                if event.prev_hash != previous_hash:
                    raise CommandError(
                        f"Audit chain broken at event {event.pk} for {organization.name}: "
                        "prev_hash does not match."
                    )
                if event.hash != expected:
                    raise CommandError(
                        f"Audit chain broken at event {event.pk} for {organization.name}: "
                        "hash does not match."
                    )
                previous_hash = event.hash
                checked += 1
        self.stdout.write(self.style.SUCCESS(f"Audit chain verified: {checked} event(s)."))
