"""Recompute audit hashes for one or more organizations."""

from apps.accounts.models import Organization

from .chain import GENESIS_HASH, event_hash
from .models import AuditEvent


class AuditChainBroken(Exception):
    """The stored chain does not match its recomputed hashes."""

    def __init__(self, *, organization, event_id: int, reason: str):
        super().__init__(f"Audit chain broken at event {event_id}: {reason}.")
        self.organization_id = organization.pk
        self.organization_name = organization.name
        self.event_id = event_id
        self.reason = reason


def verify_organizations(organizations) -> int:
    checked = 0
    for organization in organizations:
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
                raise AuditChainBroken(
                    organization=organization,
                    event_id=event.pk,
                    reason="prev_hash does not match",
                )
            if event.hash != expected:
                raise AuditChainBroken(
                    organization=organization,
                    event_id=event.pk,
                    reason="hash does not match",
                )
            previous_hash = event.hash
            checked += 1
    return checked


def verify_all() -> int:
    return verify_organizations(Organization.objects.order_by("id"))
