import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.common.currency import normalize_currency, validate_currency
from apps.common.validation import validate_timezone

MONEY_VALIDATORS = [MinValueValidator(0)]


class Policy(models.Model):
    """Versioned spending limits for one agent. Editing a policy inserts a new row."""

    class MerchantMode(models.TextChoices):
        ALLOWLIST_ONLY = "allowlist_only", "Allowlist only"
        BLOCKLIST = "blocklist", "Blocklist"

    class UntrustedSourceAction(models.TextChoices):
        NEEDS_APPROVAL = "needs_approval", "Needs approval"
        DENY = "deny", "Deny"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="policies")
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="policies")
    name = models.CharField(max_length=200, default="Default policy")
    version = models.PositiveIntegerField(default=1)
    currency = models.CharField(max_length=3, default="USD", validators=[validate_currency])

    per_transaction_cap_minor = models.PositiveBigIntegerField(default=10_000, validators=MONEY_VALIDATORS)
    daily_budget_minor = models.PositiveBigIntegerField(default=50_000, validators=MONEY_VALIDATORS)
    weekly_budget_minor = models.PositiveBigIntegerField(default=200_000, validators=MONEY_VALIDATORS)
    monthly_budget_minor = models.PositiveBigIntegerField(default=500_000, validators=MONEY_VALIDATORS)
    approval_threshold_minor = models.PositiveBigIntegerField(default=5_000, validators=MONEY_VALIDATORS)

    merchant_mode = models.CharField(
        max_length=20, choices=MerchantMode.choices, default=MerchantMode.BLOCKLIST
    )
    velocity_max_count = models.PositiveIntegerField(default=0)
    velocity_window_seconds = models.PositiveIntegerField(
        default=3_600, validators=[MinValueValidator(1)]
    )
    merchant_window_cap_minor = models.PositiveBigIntegerField(default=0)
    new_payee_cooldown_hours = models.PositiveIntegerField(default=0)
    untrusted_source_action = models.CharField(
        max_length=20,
        choices=UntrustedSourceAction.choices,
        default=UntrustedSourceAction.NEEDS_APPROVAL,
    )
    injection_escalate_threshold = models.PositiveSmallIntegerField(
        default=60, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    classifier_required = models.BooleanField(default=False)
    approval_ttl_minutes = models.PositiveIntegerField(default=60)
    timezone = models.CharField(max_length=64, default="Africa/Nairobi", validators=[validate_timezone])

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["agent", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["agent", "version"], name="unique_policy_version_per_agent"),
            models.CheckConstraint(
                condition=Q(approval_threshold_minor__lte=F("per_transaction_cap_minor")),
                name="policy_threshold_lte_cap",
            ),
            models.CheckConstraint(
                condition=Q(injection_escalate_threshold__gte=0)
                & Q(injection_escalate_threshold__lte=100),
                name="policy_injection_threshold_range",
            ),
            models.CheckConstraint(
                condition=Q(velocity_window_seconds__gte=1),
                name="policy_velocity_window_positive",
            ),
        ]
        indexes = [models.Index(fields=["organization", "agent"], name="policy_org_agent_idx")]

    def __str__(self) -> str:
        return f"{self.name} v{self.version} for {self.agent}"

    def save(self, *args, **kwargs):
        if self.agent_id and not self.organization_id:
            self.organization_id = self.agent.organization_id
        self.currency = normalize_currency(self.currency)
        validate_timezone(self.timezone)
        super().save(*args, **kwargs)


class MerchantRule(models.Model):
    """Allow or block one merchant for a policy version."""

    class Kind(models.TextChoices):
        ALLOW = "allow", "Allow"
        BLOCK = "block", "Block"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name="merchant_rules")
    merchant_ref = models.CharField(max_length=255)
    kind = models.CharField(max_length=5, choices=Kind.choices)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["merchant_ref"]
        constraints = [
            models.UniqueConstraint(fields=["policy", "merchant_ref"], name="unique_merchant_per_policy"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.merchant_ref}"
