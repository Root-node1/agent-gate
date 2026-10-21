import uuid

from django.db import models


class WebhookEvent(models.Model):
    """Inbox for PayPal events. The unique event id deduplicates provider retries."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paypal_event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    signature_verified = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.paypal_event_id})"
