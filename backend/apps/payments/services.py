"""Execute approved spend requests once, with compare-and-swap on status."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.spend.models import SpendRequest

from .executors import (
    PaymentAmbiguous,
    PaymentNotSent,
    get_executor,
)

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = frozenset({"COMPLETED", "SUCCESS", "SUCCEEDED"})
FAILURE_STATUSES = frozenset(
    {"FAILED", "DENIED", "REJECTED", "RETURNED", "BLOCKED", "CANCELED", "CANCELLED"}
)


class ExecutionOutcome:
    """Possible results of one execution attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXECUTING = "executing"
    AMBIGUOUS = "ambiguous"
    SKIPPED = "skipped"


def lock_agent_and_spend(spend_request_id):
    """Lock the agent before the spend request, matching the documented order."""
    agent_id = (
        SpendRequest.objects.only("agent_id")
        .get(pk=spend_request_id)
        .agent_id
    )
    agent = Agent.objects.select_for_update().get(pk=agent_id)
    spend_request = (
        SpendRequest.objects.select_related("organization", "agent")
        .select_for_update()
        .get(pk=spend_request_id)
    )
    return agent, spend_request


def _mark_executing(spend_request_id) -> SpendRequest | None:
    """Compare-and-swap approved to executing before any provider call."""
    with transaction.atomic():
        agent, spend_request = lock_agent_and_spend(spend_request_id)
        if spend_request.status != SpendRequest.Status.APPROVED:
            return None
        spend_request.status = SpendRequest.Status.EXECUTING
        spend_request.save(update_fields=["status", "updated_at"])
        AuditEvent.record(
            AuditEvent.EventType.PAYMENT_EXECUTING,
            organization=spend_request.organization,
            agent=agent,
            spend_request=spend_request,
            actor_type=AuditEvent.ActorType.SYSTEM,
        )
    return spend_request


def record_provider_state(
    spend_request_id,
    *,
    reference: str,
    provider_status: str,
) -> bool:
    """Store a non-terminal provider response and keep the request executing.

    Returns True when the stored reference or status changed.
    """
    with transaction.atomic():
        agent, spend_request = lock_agent_and_spend(spend_request_id)
        if spend_request.status != SpendRequest.Status.EXECUTING:
            return False
        if (
            spend_request.paypal_reference == reference
            and spend_request.paypal_status == provider_status
        ):
            spend_request.save(update_fields=["updated_at"])
            return False
        spend_request.paypal_reference = reference
        spend_request.paypal_status = provider_status
        spend_request.save(
            update_fields=["paypal_reference", "paypal_status", "updated_at"]
        )
        AuditEvent.record(
            AuditEvent.EventType.PAYMENT_EXECUTING,
            organization=spend_request.organization,
            agent=agent,
            spend_request=spend_request,
            actor_type=AuditEvent.ActorType.SYSTEM,
            paypal_reference=reference,
            paypal_status=provider_status,
        )
        return True


def finish_payment(
    spend_request_id,
    *,
    status: str,
    reference: str | None,
    provider_status: str,
    reason: str = "",
) -> bool:
    """Apply a terminal status and write the matching audit event."""
    with transaction.atomic():
        agent, spend_request = lock_agent_and_spend(spend_request_id)
        if spend_request.status != SpendRequest.Status.EXECUTING:
            return False
        spend_request.status = status
        if reference:
            spend_request.paypal_reference = reference
        spend_request.paypal_status = provider_status
        spend_request.executed_at = timezone.now()
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
            AuditEvent.EventType.PAYMENT_SUCCEEDED
            if status == SpendRequest.Status.SUCCEEDED
            else AuditEvent.EventType.PAYMENT_FAILED,
            organization=spend_request.organization,
            agent=agent,
            spend_request=spend_request,
            actor_type=AuditEvent.ActorType.SYSTEM,
            paypal_reference=reference,
            paypal_status=provider_status,
            reason=reason,
        )
        return True


def reconcile_spend_request(
    spend_request_id,
    *,
    reference: str,
    provider_status: str,
) -> str:
    """Apply a queried provider state without retrying the payment."""
    status = terminal_status(provider_status)
    if status is None:
        record_provider_state(
            spend_request_id,
            reference=reference,
            provider_status=provider_status,
        )
        return ExecutionOutcome.EXECUTING
    applied = finish_payment(
        spend_request_id,
        status=status,
        reference=reference,
        provider_status=provider_status,
        reason="reconciled",
    )
    if not applied:
        return ExecutionOutcome.SKIPPED
    return (
        ExecutionOutcome.SUCCEEDED
        if status == SpendRequest.Status.SUCCEEDED
        else ExecutionOutcome.FAILED
    )


def terminal_status(provider_status: str) -> str | None:
    """Map a provider batch status to a local terminal status, or None."""
    status = (provider_status or "").strip().upper()
    if status in SUCCESS_STATUSES:
        return SpendRequest.Status.SUCCEEDED
    if status in FAILURE_STATUSES:
        return SpendRequest.Status.FAILED
    return None


def execute_spend_request(
    spend_request_id,
    *,
    executor=None,
) -> str:
    """Execute one approved request. Safe to call repeatedly for the same id."""
    spend_request = _mark_executing(spend_request_id)
    if spend_request is None:
        return ExecutionOutcome.SKIPPED

    if executor is None:
        try:
            executor = get_executor()
        except Exception:
            logger.exception(
                "Payment executor is unavailable for request %s.", spend_request_id
            )
            finish_payment(
                spend_request_id,
                status=SpendRequest.Status.FAILED,
                reference=None,
                provider_status="",
                reason="executor_unavailable",
            )
            return ExecutionOutcome.FAILED

    try:
        result = executor.execute(spend_request)
    except PaymentNotSent as exc:
        logger.warning(
            "Payment was not sent for request %s: %s", spend_request_id, exc
        )
        finish_payment(
            spend_request_id,
            status=SpendRequest.Status.FAILED,
            reference=None,
            provider_status="",
            reason="not_sent",
        )
        return ExecutionOutcome.FAILED
    except (PaymentAmbiguous, TimeoutError) as exc:
        logger.warning(
            "Payment outcome is unknown for request %s: %s",
            spend_request_id,
            exc,
        )
        return ExecutionOutcome.AMBIGUOUS
    except Exception:
        logger.exception(
            "Unexpected payment executor failure for request %s.", spend_request_id
        )
        return ExecutionOutcome.AMBIGUOUS

    status = terminal_status(result.status)
    if status is None:
        record_provider_state(
            spend_request_id,
            reference=result.reference,
            provider_status=result.status,
        )
        return ExecutionOutcome.EXECUTING

    finish_payment(
        spend_request_id,
        status=status,
        reference=result.reference,
        provider_status=result.status,
    )
    return (
        ExecutionOutcome.SUCCEEDED
        if status == SpendRequest.Status.SUCCEEDED
        else ExecutionOutcome.FAILED
    )
