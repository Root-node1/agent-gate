"""Enqueue execution jobs after the decision or approval commits."""

import logging

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def enqueue_execution(spend_request_id) -> bool:
    """Defer one execution job, deduplicated by the spend request id."""
    if not getattr(settings, "PAYMENTS_EXECUTION_ENABLED", False):
        return False

    from . import tasks

    try:
        tasks.execute_payment.configure(
            queueing_lock=f"payment:{spend_request_id}"
        ).defer(str(spend_request_id))
    except Exception:
        # The decision is already committed; a failed enqueue must not roll it
        # back. An operator can re-enqueue the request by id.
        logger.exception(
            "Could not enqueue payment execution for request %s.",
            spend_request_id,
        )
        return False
    return True


def schedule_execution(spend_request_id) -> None:
    """Enqueue after the surrounding transaction commits."""
    transaction.on_commit(lambda: enqueue_execution(spend_request_id))
