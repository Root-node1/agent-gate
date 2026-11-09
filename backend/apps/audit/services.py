"""Recompute audit hashes and maintain external head anchors."""

from django.utils import timezone

from apps.accounts.models import Organization

from .anchors import AuditAnchor, AuditAnchorStore, AuditAnchorStoreError
from .chain import GENESIS_HASH, event_hash
from .models import AuditEvent


class AuditChainBroken(Exception):
    """The stored chain does not match its recomputed hashes or its anchor."""

    def __init__(self, *, organization, event_id: int, reason: str):
        super().__init__(f"Audit chain broken at event {event_id}: {reason}.")
        self.organization_id = organization.pk
        self.organization_name = organization.name
        self.event_id = event_id
        self.reason = reason


def _verify_anchor(organization, anchor_store: AuditAnchorStore) -> None:
    head = (
        AuditEvent.objects.filter(organization=organization)
        .order_by("-id")
        .only("id", "hash")
        .first()
    )
    try:
        anchor = anchor_store.latest(str(organization.pk))
    except AuditAnchorStoreError as exc:
        raise AuditChainBroken(
            organization=organization,
            event_id=head.pk if head else 0,
            reason=f"anchor store error: {exc}",
        ) from exc

    if anchor is None:
        if head is None:
            return
        raise AuditChainBroken(
            organization=organization,
            event_id=head.pk,
            reason="no anchor found",
        )

    anchored = (
        AuditEvent.objects.filter(
            organization=organization, pk=anchor.head_event_id
        )
        .only("id", "hash")
        .first()
    )
    if anchored is None:
        raise AuditChainBroken(
            organization=organization,
            event_id=anchor.head_event_id,
            reason="anchored event is missing",
        )
    if anchored.hash != anchor.head_hash:
        raise AuditChainBroken(
            organization=organization,
            event_id=anchor.head_event_id,
            reason="anchored hash does not match",
        )
    if head is not None and head.pk < anchor.head_event_id:
        raise AuditChainBroken(
            organization=organization,
            event_id=anchor.head_event_id,
            reason="anchored event is missing",
        )


def anchor_organization(
    organization, anchor_store: AuditAnchorStore
) -> AuditAnchor | None:
    """Record the organization's current head in the external store."""
    head = (
        AuditEvent.objects.filter(organization=organization)
        .order_by("-id")
        .only("id", "hash")
        .first()
    )
    if head is None:
        return None
    anchor = AuditAnchor(
        organization_id=str(organization.pk),
        head_event_id=head.pk,
        head_hash=head.hash,
        anchored_at=timezone.now(),
    )
    anchor_store.append(anchor)
    return anchor


def anchor_organizations(organizations, anchor_store: AuditAnchorStore) -> int:
    """Anchor every organization that has at least one audit event."""
    anchored = 0
    for organization in organizations:
        if anchor_organization(organization, anchor_store) is not None:
            anchored += 1
    return anchored


def anchor_all(anchor_store: AuditAnchorStore) -> int:
    return anchor_organizations(Organization.objects.order_by("id"), anchor_store)


def verify_organizations(
    organizations, anchor_store: AuditAnchorStore | None = None
) -> int:
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
        if anchor_store is not None:
            _verify_anchor(organization, anchor_store)
    return checked


def verify_all(anchor_store: AuditAnchorStore | None = None) -> int:
    return verify_organizations(Organization.objects.order_by("id"), anchor_store)
