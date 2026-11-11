"""Execute approved spend requests once, with compare-and-swap on status."""

from __future__ import annotations

import logging

from django.db import DatabaseError, transaction
from django.utils import timezone

import engine
from apps.agents.models import Agent, ApiKey
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
from apps.common.money import to_major
from apps.payees.models import Payee, fingerprint
from apps.policies.models import Policy
from apps.spend import services as spend_services
from apps.spend.idempotency import request_hash
from apps.spend.models import SpendRequest

from .executors import (
    PaymentAmbiguous,
    PaymentNotSent,
    get_executor,
)
from .payouts.models import SpendExecutionClaim

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = frozenset({"COMPLETED", "SUCCESS", "SUCCEEDED"})
FAILURE_STATUSES = frozenset(
    {"FAILED", "DENIED", "REJECTED", "RETURNED", "BLOCKED", "CANCELED", "CANCELLED"}
)


class ExecutionOutcome:
    """Possible results of one execution attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXECUTION_BLOCKED = "execution_blocked"
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


def _update_execution_claim(spend_request, status):
    claim = (
        SpendExecutionClaim.objects.select_for_update()
        .filter(spend_request=spend_request)
        .first()
    )
    if claim is not None and claim.status != status:
        claim.status = status
        claim.save(update_fields=["status", "updated_at"])


def _execution_block_reasons(
    agent: Agent, policy: Policy | None, spend_request: SpendRequest
) -> list[str]:
    """Return safe reason codes when current authoritative state forbids execution."""
    if spend_request.organization_id != agent.organization_id:
        return ["organization_mismatch"]
    if agent.status != Agent.Status.ACTIVE:
        return ["agent_inactive"]
    active_key_ids = list(
        ApiKey.objects.select_for_update()
        .filter(agent=agent, revoked_at__isnull=True)
        .values_list("pk", flat=True)
    )
    if not active_key_ids:
        return ["agent_unauthorized"]
    if spend_request.decision not in (
        SpendRequest.Decision.ALLOW,
        SpendRequest.Decision.NEEDS_APPROVAL,
    ):
        return ["invalid_original_decision"]
    if (
        spend_request.policy.agent_id != agent.pk
        or spend_request.policy_version != spend_request.policy.version
    ):
        return ["invalid_policy_snapshot"]

    expected_hash = request_hash(
        amount_minor=spend_request.amount_minor,
        currency=spend_request.currency,
        merchant_ref=spend_request.merchant_ref,
        purpose=spend_request.purpose,
        source_type=spend_request.source_type,
        source_ref=spend_request.source_ref,
        evidence_excerpt=spend_request.evidence_excerpt,
        destination_type=spend_request.destination_type,
        destination_value=spend_request.destination_value,
    )
    expected_fingerprint = (
        fingerprint(spend_request.destination_type, spend_request.destination_value)
        if spend_request.destination_type and spend_request.destination_value
        else ""
    )
    if (
        not spend_request.request_hash
        or spend_request.request_hash != expected_hash
        or spend_request.destination_fingerprint != expected_fingerprint
        or bool(spend_request.destination_type) != bool(spend_request.destination_value)
    ):
        return ["request_snapshot_mismatch"]

    if policy is None or policy.organization_id != spend_request.organization_id:
        return ["current_policy_missing"]

    payee_state = None
    if spend_request.destination_type:
        payee = (
            Payee.objects.select_for_update()
            .filter(
                organization_id=spend_request.organization_id,
                merchant_ref=spend_request.merchant_ref,
            )
            .first()
        )
        if (
            payee is None
            or payee.status != Payee.Status.ACTIVE
            or payee.destination_type != spend_request.destination_type
            or payee.destination_value != spend_request.destination_value
            or payee.destination_fingerprint != spend_request.destination_fingerprint
        ):
            return ["destination_changed"]

        payee_state = engine.PayeeState(
            known=True,
            trusted=payee.trusted_at is not None,
            within_cooldown=(
                policy.new_payee_cooldown_hours > 0
                and payee.first_seen_at
                + timezone.timedelta(hours=policy.new_payee_cooldown_hours)
                > timezone.now()
            ),
        )

    try:
        spent = spend_services.build_spent(
            agent,
            policy,
            spend_request.currency,
            spend_request.merchant_ref,
            exclude_request_id=spend_request.pk,
        )
        decision = engine.evaluate_context(
            engine.EvaluationContext(
                spend=engine.SpendInput(
                    amount=to_major(spend_request.amount_minor, spend_request.currency),
                    currency=spend_request.currency,
                    merchant=spend_request.merchant_ref,
                    source=spend_services.rule_source(spend_request.source_type),
                    purpose=spend_request.purpose,
                    evidence_excerpt=spend_request.evidence_excerpt,
                    agent_active=agent.status == Agent.Status.ACTIVE,
                ),
                limits=spend_services.build_limits(policy),
                spent=spent,
                payee=payee_state,
            ),
        )
    except DatabaseError:
        raise
    except Exception:
        logger.exception(
            "Execution policy recheck failed for request %s.", spend_request.pk
        )
        return ["policy_recheck_error"]

    approval_required = (
        spend_request.decision == SpendRequest.Decision.NEEDS_APPROVAL
        or decision.outcome == engine.NEEDS_APPROVAL
    )
    if decision.outcome == engine.DENY:
        return ["policy_denied", *sorted({reason.code for reason in decision.reasons})]
    if approval_required:
        approval = (
            Approval.objects.select_for_update()
            .filter(spend_request_id=spend_request.pk)
            .first()
        )
        if (
            approval is None
            or approval.organization_id != spend_request.organization_id
            or approval.outcome != Approval.Outcome.APPROVED
            or approval.approver_id is None
            or approval.decided_at is None
        ):
            return [
                "approval_required",
                *sorted(
                    {
                        reason.code
                        for reason in decision.reasons
                        if reason.outcome == engine.NEEDS_APPROVAL
                    }
                ),
            ]
    return []


def _mark_executing(spend_request_id) -> SpendRequest | None:
    """Revalidate and claim approved work before any provider call."""
    with transaction.atomic():
        agent_id = (
            SpendRequest.objects.only("agent_id")
            .get(pk=spend_request_id)
            .agent_id
        )
        agent = Agent.objects.select_for_update().get(pk=agent_id)
        policy = spend_services.current_policy(agent, for_update=True)
        spend_request = (
            SpendRequest.objects.select_related("organization", "agent", "policy")
            .select_for_update()
            .get(pk=spend_request_id)
        )
        if spend_request.status != SpendRequest.Status.APPROVED:
            return None
        if SpendExecutionClaim.objects.select_for_update().filter(
            spend_request=spend_request
        ).exists():
            return None
        block_reasons = _execution_block_reasons(agent, policy, spend_request)
        if block_reasons:
            spend_request.status = SpendRequest.Status.EXECUTION_BLOCKED
            spend_request.reasons = [
                *spend_request.reasons,
                {
                    "code": "execution_recheck_blocked",
                    "message": "Current controls blocked execution.",
                },
            ]
            spend_request.save(update_fields=["status", "reasons", "updated_at"])
            AuditEvent.record(
                AuditEvent.EventType.EXECUTION_BLOCKED,
                organization=spend_request.organization,
                agent=agent,
                spend_request=spend_request,
                actor_type=AuditEvent.ActorType.SYSTEM,
                reason_codes=block_reasons,
                original_policy_version=spend_request.policy_version,
                current_policy_version=policy.version if policy is not None else None,
            )
            return spend_request

        SpendExecutionClaim.objects.create(
            spend_request=spend_request,
            path=SpendExecutionClaim.Path.AUTOMATIC,
            status=SpendExecutionClaim.Status.CLAIMED,
        )
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
        _update_execution_claim(
            spend_request,
            SpendExecutionClaim.Status.SUCCEEDED
            if status == SpendRequest.Status.SUCCEEDED
            else SpendExecutionClaim.Status.FAILED,
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
    if spend_request.status == SpendRequest.Status.EXECUTION_BLOCKED:
        return ExecutionOutcome.EXECUTION_BLOCKED

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
        with transaction.atomic():
            _agent, current_request = lock_agent_and_spend(spend_request_id)
            if current_request.status == SpendRequest.Status.EXECUTING:
                _update_execution_claim(
                    current_request,
                    SpendExecutionClaim.Status.UNCERTAIN,
                )
        return ExecutionOutcome.AMBIGUOUS
    except Exception:
        logger.exception(
            "Unexpected payment executor failure for request %s.", spend_request_id
        )
        with transaction.atomic():
            _agent, current_request = lock_agent_and_spend(spend_request_id)
            if current_request.status == SpendRequest.Status.EXECUTING:
                _update_execution_claim(
                    current_request,
                    SpendExecutionClaim.Status.UNCERTAIN,
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
