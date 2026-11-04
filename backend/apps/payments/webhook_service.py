"""Apply verified PayPal webhook events to spend requests."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.spend.models import SpendRequest

from .models import WebhookEvent
from .paypal.webhooks import (
    OUTCOME_FAILED,
    OUTCOME_REVERSED,
    OUTCOME_SUCCEEDED,
    parse_payout_event,
)
from .services import lock_agent_and_spend

logger = logging.getLogger(__name__)

OUTCOME_STATUS = {
    OUTCOME_SUCCEEDED: SpendRequest.Status.SUCCEEDED,
    OUTCOME_FAILED: SpendRequest.Status.FAILED,
    OUTCOME_REVERSED: SpendRequest.Status.REVERSED,
}
OUTCOME_AUDIT = {
    OUTCOME_SUCCEEDED: AuditEvent.EventType.PAYMENT_SUCCEEDED,
    OUTCOME_FAILED: AuditEvent.EventType.PAYMENT_FAILED,
    OUTCOME_REVERSED: AuditEvent.EventType.PAYMENT_REVERSED,
}
STATUS_RANK = {
    SpendRequest.Status.PENDING_APPROVAL: 0,
    SpendRequest.Status.DENIED: 0,
    SpendRequest.Status.APPROVED: 1,
    SpendRequest.Status.EXECUTING: 2,
    SpendRequest.Status.SUCCEEDED: 3,
    SpendRequest.Status.FAILED: 3,
    SpendRequest.Status.REJECTED: 3,
    SpendRequest.Status.EXPIRED: 3,
    SpendRequest.Status.REVERSED: 4,
}
TERMINAL_STATUSES = frozenset(
    {
        SpendRequest.Status.SUCCEEDED,
        SpendRequest.Status.FAILED,
        SpendRequest.Status.REVERSED,
    }
)
APPLICABLE_STATUSES = frozenset(
    {
        SpendRequest.Status.APPROVED,
        SpendRequest.Status.EXECUTING,
        SpendRequest.Status.SUCCEEDED,
        SpendRequest.Status.FAILED,
    }
)


def should_apply(current_status: str, target_status: str) -> bool:
    """Return whether a provider status moves the request forward."""
    return STATUS_RANK.get(target_status, -1) > STATUS_RANK.get(current_status, -1)


def apply_webhook_event(webhook_event_id) -> str:
    """Process one stored event once, updating the spend request and audit log."""
    with transaction.atomic():
        event = WebhookEvent.objects.select_for_update().get(pk=webhook_event_id)
        if event.processed_at is not None:
            return "already_processed"
        if not event.signature_verified:
            raise PermissionError(
                "Unverified webhook events cannot be processed."
            )

        parsed = parse_payout_event(event.payload)
        now = timezone.now()
        if parsed.spend_request_id is None:
            _mark_processed(event, now)
            logger.warning(
                "Webhook event %s does not reference a spend request.",
                event.paypal_event_id,
            )
            return "ignored"

        try:
            agent, spend_request = lock_agent_and_spend(parsed.spend_request_id)
        except SpendRequest.DoesNotExist:
            _mark_processed(event, now)
            logger.warning(
                "Webhook event %s references an unknown spend request.",
                event.paypal_event_id,
            )
            return "ignored"

        target_status = OUTCOME_STATUS.get(parsed.outcome or "")
        applied = False
        reason = ""

        if target_status is None:
            reason = "unsupported_event"
        elif spend_request.status not in APPLICABLE_STATUSES:
            reason = "unexpected_state"
        elif (
            parsed.reference
            and spend_request.paypal_reference
            and parsed.reference != spend_request.paypal_reference
        ):
            reason = "reference_mismatch"
        elif not should_apply(spend_request.status, target_status):
            reason = "not_forward"
        else:
            spend_request.status = target_status
            if parsed.reference and not spend_request.paypal_reference:
                spend_request.paypal_reference = parsed.reference
            if parsed.provider_status:
                spend_request.paypal_status = parsed.provider_status
            if spend_request.executed_at is None and target_status in TERMINAL_STATUSES:
                spend_request.executed_at = now
            spend_request.save(
                update_fields=[
                    "status",
                    "paypal_reference",
                    "paypal_status",
                    "executed_at",
                    "updated_at",
                ]
            )
            AuditEvent.record(
                OUTCOME_AUDIT[parsed.outcome],
                organization=spend_request.organization,
                agent=agent,
                spend_request=spend_request,
                actor_type=AuditEvent.ActorType.PAYPAL,
                actor_id=event.paypal_event_id,
                paypal_reference=spend_request.paypal_reference or "",
                paypal_status=spend_request.paypal_status,
                reason=event.event_type,
            )
            applied = True

        AuditEvent.record(
            AuditEvent.EventType.WEBHOOK_RECEIVED,
            organization=spend_request.organization,
            agent=agent,
            spend_request=spend_request,
            actor_type=AuditEvent.ActorType.PAYPAL,
            actor_id=event.paypal_event_id,
            paypal_event_type=event.event_type,
            provider_status=parsed.provider_status,
            applied=applied,
            reason=reason,
        )
        _mark_processed(event, now)
        return "applied" if applied else "ignored"


def _mark_processed(event: WebhookEvent, now) -> None:
    event.processed_at = now
    event.save(update_fields=["processed_at", "updated_at"])
