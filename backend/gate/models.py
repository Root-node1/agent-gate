import hashlib
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


class Agent(models.Model):
    """An AI agent allowed to submit spend requests. Only a hash of its API key is stored."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    name = models.CharField(max_length=100, unique=True)
    api_key_prefix = models.CharField(max_length=8, editable=False)
    api_key_hash = models.CharField(max_length=64, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @classmethod
    def create_with_key(cls, name: str):
        """Create an agent and return (agent, raw_key). The raw key is shown once and never stored."""
        raw_key = "agk_" + secrets.token_urlsafe(32)
        agent = cls.objects.create(
            name=name,
            api_key_prefix=raw_key[:8],
            api_key_hash=hash_key(raw_key),
        )
        return agent, raw_key


class Policy(models.Model):
    """Spending limits for one agent. Enforced in code by the rule engine."""

    agent = models.OneToOneField(Agent, on_delete=models.CASCADE, related_name="policy")
    currency = models.CharField(max_length=3, default="USD")
    per_transaction_cap = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("100.00"))
    approval_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("50.00"))
    daily_budget = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("500.00"))
    monthly_budget = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("5000.00"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "policies"
        constraints = [
            models.CheckConstraint(
                condition=Q(approval_threshold__lte=F("per_transaction_cap")),
                name="policy_threshold_lte_cap",
            ),
        ]

    def __str__(self):
        return f"Policy for {self.agent}"


class MerchantRule(models.Model):
    """Allow or block a specific merchant for a policy."""

    class Action(models.TextChoices):
        ALLOW = "allow", "Allow"
        BLOCK = "block", "Block"

    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name="merchant_rules")
    merchant = models.CharField(max_length=255)
    action = models.CharField(max_length=5, choices=Action.choices)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["policy", "merchant"], name="unique_merchant_per_policy"),
        ]

    def __str__(self):
        return f"{self.action} {self.merchant}"


class SpendRequest(models.Model):
    """One request from an agent to spend money, with the firewall's decision."""

    class Source(models.TextChoices):
        TRUSTED = "trusted", "Trusted (operator or user)"
        UNTRUSTED = "untrusted", "Untrusted (web page, email, invoice)"
        UNKNOWN = "unknown", "Unknown"

    class Decision(models.TextChoices):
        PENDING = "pending", "Pending"
        ALLOW = "allow", "Allow"
        DENY = "deny", "Deny"
        NEEDS_APPROVAL = "needs_approval", "Needs approval"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="spend_requests")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    merchant = models.CharField(max_length=255)
    purpose = models.TextField(blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.UNKNOWN)
    risk_score = models.PositiveSmallIntegerField(default=0)
    decision = models.CharField(max_length=15, choices=Decision.choices, default=Decision.PENDING)
    reasons = models.JSONField(default=list, blank=True)
    matched_rules = models.JSONField(default=list, blank=True)
    paypal_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.amount} {self.currency} to {self.merchant} ({self.decision})"


class Approval(models.Model):
    """A human's decision on a request that needed approval."""

    class Outcome(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    spend_request = models.OneToOneField(SpendRequest, on_delete=models.CASCADE, related_name="approval")
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.PENDING)
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.outcome}: {self.spend_request_id}"


class AuditEvent(models.Model):
    """Append-only record of everything that happens. Never edited, never deleted."""

    event_type = models.CharField(max_length=50)
    agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.PROTECT)
    spend_request = models.ForeignKey(SpendRequest, null=True, blank=True, on_delete=models.PROTECT)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.event_type}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Audit events are append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit events are append-only and cannot be deleted.")

    @classmethod
    def record(cls, event_type, *, agent=None, spend_request=None, **payload):
        return cls.objects.create(
            event_type=event_type, agent=agent, spend_request=spend_request, payload=payload
        )
