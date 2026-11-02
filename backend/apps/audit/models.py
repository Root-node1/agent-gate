from datetime import timezone as datetime_timezone

from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.spend.models import SpendRequest

from .chain import GENESIS_HASH, canonical_payload, event_hash


class AuditEvent(models.Model):
    """Append-only record of everything that happens. Never edited, never deleted."""

    class EventType(models.TextChoices):
        REQUEST_RECEIVED = "request.received", "Request received"
        DECISION_MADE = "decision.made", "Decision made"
        APPROVAL_REQUESTED = "approval.requested", "Approval requested"
        APPROVAL_APPROVED = "approval.approved", "Approval approved"
        APPROVAL_DENIED = "approval.denied", "Approval denied"
        APPROVAL_EXPIRED = "approval.expired", "Approval expired"
        PAYMENT_EXECUTING = "payment.executing", "Payment executing"
        PAYMENT_SUCCEEDED = "payment.succeeded", "Payment succeeded"
        PAYMENT_FAILED = "payment.failed", "Payment failed"
        WEBHOOK_RECEIVED = "webhook.received", "Webhook received"
        POLICY_CHANGED = "policy.changed", "Policy changed"
        AGENT_CREATED = "agent.created", "Agent created"
        AGENT_UPDATED = "agent.updated", "Agent updated"
        AGENT_SUSPENDED = "agent.suspended", "Agent suspended"
        KEY_CREATED = "key.created", "Key created"
        KEY_REVOKED = "key.revoked", "Key revoked"
        DEMO_RESET = "demo.reset", "Demo reset"

    class ActorType(models.TextChoices):
        AGENT = "agent", "Agent"
        USER = "user", "User"
        SYSTEM = "system", "System"
        PAYPAL = "paypal", "PayPal"

    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="audit_events")
    agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events")
    spend_request = models.ForeignKey(
        SpendRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events"
    )
    event_type = models.CharField(max_length=50, choices=EventType.choices)
    actor_type = models.CharField(
        max_length=10, choices=ActorType.choices, default=ActorType.SYSTEM
    )
    actor_id = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    prev_hash = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["organization", "id"], name="audit_org_id_idx")]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.event_type}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Audit events are append-only and cannot be modified.")
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=self.organization_id)
            previous = (
                AuditEvent.objects.filter(organization_id=self.organization_id)
                .order_by("-id")
                .only("hash")
                .first()
            )
            self.prev_hash = previous.hash if previous and previous.hash else GENESIS_HASH
            if self.created_at is None:
                self.created_at = timezone.now()
            if timezone.is_naive(self.created_at):
                self.created_at = self.created_at.replace(tzinfo=datetime_timezone.utc)
            self.created_at = self.created_at.astimezone(datetime_timezone.utc)
            self.payload = canonical_payload(self.payload)
            self.hash = event_hash(
                prev_hash=self.prev_hash,
                created_at=self.created_at,
                event_type=self.event_type,
                actor_type=self.actor_type,
                actor_id=self.actor_id,
                organization_id=self.organization_id,
                agent_id=self.agent_id,
                spend_request_id=self.spend_request_id,
                payload=self.payload,
            )
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit events are append-only and cannot be deleted.")

    @classmethod
    def record(
        cls,
        event_type: str,
        *,
        organization: Organization,
        agent: Agent | None = None,
        spend_request: SpendRequest | None = None,
        actor_type: str = ActorType.SYSTEM,
        actor_id: str = "",
        **payload,
    ):
        """Append one event. Callers write it in the same transaction as the state change."""
        return cls.objects.create(
            organization=organization,
            event_type=event_type,
            agent=agent,
            spend_request=spend_request,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=payload,
        )
