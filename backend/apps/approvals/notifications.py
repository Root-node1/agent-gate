"""Approval-created signal for plugging in SMS, email, or chat notifications."""

import logging

from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from .models import Approval

logger = logging.getLogger(__name__)

approval_created = Signal()


@receiver(post_save, sender=Approval, dispatch_uid="approvals.notify_created")
def notify_approval_created(sender, instance, created, **kwargs):
    """Emit the public signal once per new approval without touching the request row."""
    if not created:
        return
    logger.info(
        "Approval %s created for spend request %s.",
        instance.pk,
        instance.spend_request_id,
    )
    approval_created.send(sender=Approval, approval=instance)
