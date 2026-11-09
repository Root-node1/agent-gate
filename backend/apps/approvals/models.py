import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.accounts.models import Organization
from apps.spend.models import SpendRequest


class Approval(models.Model):
    """A human decision on a request that needed approval, with an expiry deadline."""

    class Outcome(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="approvals")
    spend_request = models.OneToOneField(
        SpendRequest, on_delete=models.CASCADE, related_name="approval"
    )
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.PENDING)
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    note = models.CharField(max_length=255, blank=True)
    requested_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [models.Index(fields=["outcome", "expires_at"], name="approval_outcome_expiry_idx")]

    def __str__(self) -> str:
        return f"{self.outcome}: {self.spend_request_id}"

    def save(self, *args, **kwargs):
        if self.spend_request_id is None:
            raise ValidationError({"spend_request": "An approval requires a spend request."})
        spend_organization_id = self.spend_request.organization_id
        if (
            self.organization_id is not None
            and self.organization_id != spend_organization_id
        ):
            raise ValidationError(
                {
                    "organization": (
                        "The approval organization must match its spend request's organization."
                    )
                }
            )
        self.organization_id = spend_organization_id
        super().save(*args, **kwargs)
