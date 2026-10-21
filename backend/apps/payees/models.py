import hashlib
import re
import uuid
from urllib.parse import urlsplit

from django.db import models
from django.utils import timezone

from apps.accounts.models import Organization


class DestinationType(models.TextChoices):
    PAYPAL_EMAIL = "paypal_email", "PayPal email"
    PAYPAL_ID = "paypal_id", "PayPal id"
    PHONE = "phone", "Phone"
    URL = "url", "URL"


def normalize_destination(destination_type: str, value: str) -> str:
    """Return a canonical destination value so fingerprints are stable."""
    raw = value.strip()
    if destination_type == DestinationType.PAYPAL_EMAIL:
        return raw.lower()
    if destination_type == DestinationType.PAYPAL_ID:
        return raw
    if destination_type == DestinationType.PHONE:
        return re.sub(r"[^\d]", "", raw)
    if destination_type == DestinationType.URL:
        if "://" not in raw:
            raw = "https://" + raw
        parts = urlsplit(raw)
        host = parts.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return f"{host}{parts.path.rstrip('/')}"
    return raw


def fingerprint(destination_type: str, value: str) -> str:
    """SHA-256 of the normalized destination, stored beside the display value."""
    canonical = f"{destination_type}:{normalize_destination(destination_type, value)}"
    return hashlib.sha256(canonical.encode()).hexdigest()


class Payee(models.Model):
    """The known destination for a merchant, used to detect payee changes."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="payees")
    merchant_ref = models.CharField(max_length=255)
    display_name = models.CharField(max_length=200, blank=True)
    destination_type = models.CharField(max_length=20, choices=DestinationType.choices)
    destination_value = models.CharField(max_length=500)
    destination_fingerprint = models.CharField(max_length=64, db_index=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_changed_at = models.DateTimeField(default=timezone.now)
    trusted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["merchant_ref"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "merchant_ref"], name="unique_payee_merchant_per_org"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.merchant_ref} -> {self.destination_value}"
