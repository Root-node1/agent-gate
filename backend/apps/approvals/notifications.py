"""Approval-created signal for plugging in SMS, email, or chat notifications."""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from .models import Approval

logger = logging.getLogger(__name__)

approval_created = Signal()


def _emit_approval_created(approval):
    logger.info(
        "Approval %s created for spend request %s.",
        approval.pk,
        approval.spend_request_id,
    )
    approval_created.send(sender=Approval, approval=approval)


@receiver(post_save, sender=Approval, dispatch_uid="approvals.notify_created")
def notify_approval_created(sender, instance, created, **kwargs):
    """Emit the public signal once per new approval after its transaction commits."""
    if not created:
        return
    transaction.on_commit(lambda: _emit_approval_created(instance))
