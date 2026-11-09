"""Retention for stored PayPal webhook payloads."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from .models import WebhookEvent

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 1_000


def purge_processed_webhook_payloads(
    *,
    retention_days: int | None = None,
    now: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
) -> int:
    """Clear payloads for processed events older than the retention window."""
    days = (
        getattr(settings, "WEBHOOK_RETENTION_DAYS", 30)
        if retention_days is None
        else retention_days
    )
    if days < 1:
        raise ValueError("Webhook retention must be at least one day.")
    if batch_size < 1:
        raise ValueError("Batch size must be at least one.")

    purged_at = now or timezone.now()
    cutoff = purged_at - timedelta(days=days)
    eligible = WebhookEvent.objects.filter(
        processed_at__isnull=False,
        processed_at__lt=cutoff,
        payload_purged_at__isnull=True,
    )
    if dry_run:
        return eligible.count()

    total = 0
    while True:
        event_ids = list(
            eligible.order_by("processed_at", "pk").values_list("pk", flat=True)[
                :batch_size
            ]
        )
        if not event_ids:
            break

        updated = WebhookEvent.objects.filter(
            pk__in=event_ids,
            payload_purged_at__isnull=True,
        ).update(
            payload={},
            payload_purged_at=purged_at,
            updated_at=purged_at,
        )
        total += updated
        for event_id in event_ids:
            logger.info("Purged webhook payload for event %s.", event_id)

        if len(event_ids) < batch_size:
            break

    return total
