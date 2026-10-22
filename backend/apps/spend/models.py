import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.common.currency import normalize_currency, validate_currency
from apps.payees.models import DestinationType, Payee
from apps.policies.models import Policy


class SpendRequest(models.Model):
    """One agent request and the firewall's immutable decision about it."""

    class SourceType(models.TextChoices):
        TRUSTED = "trusted", "Trusted (operator or user)"
        UNTRUSTED = "untrusted", "Untrusted"
        WEB_PAGE = "web_page", "Web page"
        EMAIL = "email", "Email"
        INVOICE = "invoice", "Invoice"
        TOOL_OUTPUT = "tool_output", "Tool output"
        UNKNOWN = "unknown", "Unknown"

    class Decision(models.TextChoices):
        ALLOW = "allow", "Allow"
        DENY = "deny", "Deny"
        NEEDS_APPROVAL = "needs_approval", "Needs approval"

    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        DENIED = "denied", "Denied"
        APPROVED = "approved", "Approved"
        EXECUTING = "executing", "Executing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        REVERSED = "reversed", "Reversed"

    BUDGET_STATUSES = (Status.APPROVED, Status.EXECUTING, Status.SUCCEEDED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="spend_requests")
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="spend_requests")
    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, related_name="spend_requests")
    policy_version = models.PositiveIntegerField()

    idempotency_key = models.CharField(max_length=255, null=True, blank=True)
    request_hash = models.CharField(max_length=64, blank=True)

    amount_minor = models.PositiveBigIntegerField(validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="USD", validators=[validate_currency])
    merchant_ref = models.CharField(max_length=255)

    payee = models.ForeignKey(Payee, null=True, blank=True, on_delete=models.SET_NULL, related_name="spend_requests")
    destination_type = models.CharField(max_length=20, choices=DestinationType.choices, blank=True)
    destination_value = models.CharField(max_length=500, blank=True)
    destination_fingerprint = models.CharField(max_length=64, blank=True)

    purpose = models.CharField(max_length=2_000, blank=True)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.UNTRUSTED)
    source_ref = models.CharField(max_length=500, blank=True)
    evidence_excerpt = models.CharField(max_length=4_096, blank=True)
    evidence_hash = models.CharField(max_length=64, blank=True)

    risk_score = models.PositiveSmallIntegerField(default=0)
    decision = models.CharField(max_length=15, choices=Decision.choices)
    status = models.CharField(max_length=20, choices=Status.choices)
    reasons = models.JSONField(default=list, blank=True)
    matched_rules = models.JSONField(default=list, blank=True)

    paypal_reference = models.CharField(max_length=100, null=True, blank=True)
    paypal_status = models.CharField(max_length=50, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["agent", "idempotency_key"], name="unique_idempotency_key_per_agent"
            ),
            models.UniqueConstraint(
                fields=["paypal_reference"],
                condition=Q(paypal_reference__isnull=False),
                name="unique_paypal_reference",
            ),
            models.CheckConstraint(condition=Q(amount_minor__gt=0), name="spend_amount_positive"),
            models.CheckConstraint(
                condition=Q(risk_score__gte=0) & Q(risk_score__lte=100), name="spend_risk_score_range"
            ),
        ]
        indexes = [
            models.Index(fields=["agent", "created_at"], name="spend_agent_created_idx"),
            models.Index(fields=["status"], name="spend_status_idx"),
            models.Index(fields=["agent", "merchant_ref", "created_at"], name="spend_agent_merchant_idx"),
            models.Index(
                fields=["agent", "currency", "status", "created_at"], name="spend_budget_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.amount_minor} {self.currency} to {self.merchant_ref} ({self.decision})"

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._original_decision = instance.decision
        return instance

    def save(self, *args, **kwargs):
        self.currency = normalize_currency(self.currency)
        original = getattr(self, "_original_decision", None)
        if not self._state.adding and original is not None and original != self.decision:
            raise ValueError("A spend request decision is immutable once written.")
        super().save(*args, **kwargs)
        self._original_decision = self.decision
