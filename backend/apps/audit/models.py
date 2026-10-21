from django.db import models

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.spend.models import SpendRequest


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
        KEY_CREATED = "key.created", "Key created"
        KEY_REVOKED = "key.revoked", "Key revoked"

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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["organization", "id"], name="audit_org_id_idx")]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.event_type}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Audit events are append-only and cannot be modified.")
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
