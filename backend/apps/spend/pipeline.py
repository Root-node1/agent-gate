"""The spend pipeline: normalize, screen, lock, decide, and persist."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

import engine
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.common.currency import normalize_currency
from apps.common.money import to_minor
from apps.payees.models import Payee, fingerprint, normalize_destination
from apps.policies.models import Policy

from . import classifier, services
from .idempotency import request_hash
from .models import SpendRequest

logger = logging.getLogger(__name__)

OUTCOME_STATUS = {
    engine.ALLOW: SpendRequest.Status.APPROVED,
    engine.DENY: SpendRequest.Status.DENIED,
    engine.NEEDS_APPROVAL: SpendRequest.Status.PENDING_APPROVAL,
}


class PolicyMissing(Exception):
    """The agent has no policy, so nothing can be decided."""


class IdempotencyConflict(Exception):
    """The same key was reused with a different request body."""


@dataclass(frozen=True)
class PreparedSpend:
    """A validated request normalized against one currency and destination."""

    amount: Decimal
    amount_minor: int
    currency: str
    merchant_ref: str
    purpose: str
    source_type: str
    source_ref: str
    evidence_excerpt: str
    destination_type: str
    destination_value: str
    destination_fingerprint: str
    body_hash: str
    idempotency_key: str | None


def _prepare(
    *,
    amount: Decimal,
    currency: str,
    merchant: str,
    purpose: str,
    source_type: str,
    source_ref: str,
    evidence_excerpt: str,
    destination_type: str,
    destination_value: str,
    idempotency_key: str | None,
) -> PreparedSpend:
    """Normalize every field that affects the payment or its fingerprint."""
    currency = normalize_currency(currency)
    amount_minor = to_minor(amount, currency)
    merchant_ref = engine.normalize_merchant(merchant)
    if destination_type:
        destination_value = normalize_destination(destination_type, destination_value)
        destination_fingerprint = fingerprint(destination_type, destination_value)
    else:
        destination_value = ""
        destination_fingerprint = ""

    body_hash = request_hash(
        amount_minor=amount_minor,
        currency=currency,
        merchant_ref=merchant_ref,
        purpose=purpose,
        source_type=source_type,
        source_ref=source_ref,
        evidence_excerpt=evidence_excerpt,
        destination_type=destination_type,
        destination_value=destination_value,
    )
    return PreparedSpend(
        amount=amount,
        amount_minor=amount_minor,
        currency=currency,
        merchant_ref=merchant_ref,
        purpose=purpose,
        source_type=source_type,
        source_ref=source_ref,
        evidence_excerpt=evidence_excerpt,
        destination_type=destination_type,
        destination_value=destination_value,
        destination_fingerprint=destination_fingerprint,
        body_hash=body_hash,
        idempotency_key=idempotency_key,
    )


def _replay(agent_id: UUID, idempotency_key: str | None, body_hash: str) -> SpendRequest | None:
    """Return a stored response for the same key and body, or raise on a mismatch."""
    if not idempotency_key:
        return None
    existing = (
        SpendRequest.objects.select_related("approval")
        .filter(agent_id=agent_id, idempotency_key=idempotency_key)
        .first()
    )
    if existing is None:
        return None
    if existing.request_hash != body_hash:
        raise IdempotencyConflict("Idempotency-Key was reused with a different request.")
    return existing


def _payee_state(
    agent: Agent,
    policy: Policy,
    prepared: PreparedSpend,
    now: datetime,
) -> engine.PayeeState | None:
    """Describe the merchant's payee before the request is decided and recorded."""
    if not prepared.destination_fingerprint:
        return None

    payee = (
        Payee.objects.filter(
            organization_id=agent.organization_id,
            merchant_ref=prepared.merchant_ref,
        )
        .only("trusted_at", "first_seen_at", "destination_fingerprint")
        .first()
    )
    if payee is None:
        return engine.PayeeState(
            known=False,
            within_cooldown=policy.new_payee_cooldown_hours > 0,
        )

    within_cooldown = (
        policy.new_payee_cooldown_hours > 0
        and payee.first_seen_at + timedelta(hours=policy.new_payee_cooldown_hours) > now
    )
    return engine.PayeeState(
        known=True,
        trusted=payee.trusted_at is not None,
        within_cooldown=within_cooldown,
        destination_changed=payee.destination_fingerprint
        != prepared.destination_fingerprint,
    )


def _decide(
    prepared: PreparedSpend,
    policy: Policy,
    spent: engine.Spent,
    screening: engine.ScreeningResult,
    payee: engine.PayeeState | None,
    *,
    agent_active: bool,
) -> engine.Decision:
    """Evaluate one request and fail closed if the engine raises."""
    context = engine.EvaluationContext(
        spend=engine.SpendInput(
            amount=prepared.amount,
            currency=prepared.currency,
            merchant=prepared.merchant_ref,
            source=services.rule_source(prepared.source_type),
            purpose=prepared.purpose,
            evidence_excerpt=prepared.evidence_excerpt,
            agent_active=agent_active,
        ),
        limits=services.build_limits(policy),
        spent=spent,
        screening=screening,
        payee=payee,
    )

    try:
        return engine.evaluate_context(context)
    except Exception:
        logger.exception("Policy engine failed for agent %s.", policy.agent_id)
        return engine.Decision(
            outcome=engine.DENY,
            reasons=(
                engine.Reason(
                    "engine_error",
                    "The policy engine could not evaluate the request.",
                    engine.DENY,
                ),
            ),
            risk_score=engine.MAX_RISK_SCORE,
        )


def _record_decision(
    *,
    agent: Agent,
    policy: Policy,
    prepared: PreparedSpend,
    decision: engine.Decision,
    now: datetime,
) -> SpendRequest:
    """Persist the request, destination snapshot, audit events, and approval."""
    spend_request = SpendRequest.objects.create(
        organization=agent.organization,
        agent=agent,
        policy=policy,
        policy_version=policy.version,
        idempotency_key=prepared.idempotency_key,
        request_hash=prepared.body_hash,
        amount_minor=prepared.amount_minor,
        currency=prepared.currency,
        merchant_ref=prepared.merchant_ref,
        destination_type=prepared.destination_type,
        destination_value=prepared.destination_value,
        destination_fingerprint=prepared.destination_fingerprint,
        purpose=prepared.purpose,
        source_type=prepared.source_type,
        source_ref=prepared.source_ref,
        evidence_excerpt=prepared.evidence_excerpt,
        risk_score=decision.risk_score,
        decision=decision.outcome,
        status=OUTCOME_STATUS[decision.outcome],
        reasons=[{"code": r.code, "message": r.message} for r in decision.reasons],
        matched_rules=decision.matched_rules,
        decided_at=now,
    )

    if prepared.destination_type and decision.outcome != engine.DENY:
        defaults = {
            "destination_type": prepared.destination_type,
            "destination_value": prepared.destination_value,
            "destination_fingerprint": prepared.destination_fingerprint,
        }
        payee, created = Payee.objects.get_or_create(
            organization=agent.organization,
            merchant_ref=prepared.merchant_ref,
            defaults=defaults,
        )
        payee = Payee.objects.select_for_update().get(pk=payee.pk)
        if not created and payee.destination_fingerprint != prepared.destination_fingerprint:
            for field, value in defaults.items():
                setattr(payee, field, value)
            payee.last_changed_at = now
            payee.save(
                update_fields=[
                    "destination_type",
                    "destination_value",
                    "destination_fingerprint",
                    "last_changed_at",
                    "updated_at",
                ]
            )

    AuditEvent.record(
        AuditEvent.EventType.REQUEST_RECEIVED,
        organization=agent.organization,
        agent=agent,
        spend_request=spend_request,
        actor_type=AuditEvent.ActorType.AGENT,
        actor_id=str(agent.id),
        amount=str(prepared.amount),
        currency=prepared.currency,
        merchant=prepared.merchant_ref,
        source_type=prepared.source_type,
    )
    AuditEvent.record(
        AuditEvent.EventType.DECISION_MADE,
        organization=agent.organization,
        agent=agent,
        spend_request=spend_request,
        actor_type=AuditEvent.ActorType.SYSTEM,
        decision=decision.outcome,
        rules=decision.matched_rules,
    )

    if decision.outcome == engine.NEEDS_APPROVAL:
        from apps.approvals.models import Approval

        Approval.objects.create(
            organization=agent.organization,
            spend_request=spend_request,
            requested_at=now,
            expires_at=now + timezone.timedelta(minutes=policy.approval_ttl_minutes),
        )
        AuditEvent.record(
            AuditEvent.EventType.APPROVAL_REQUESTED,
            organization=agent.organization,
            agent=agent,
            spend_request=spend_request,
            actor_type=AuditEvent.ActorType.SYSTEM,
        )

    return spend_request


def submit_spend_request(
    agent: Agent,
    *,
    amount: Decimal,
    currency: str,
    merchant: str,
    purpose: str = "",
    source_type: str = SpendRequest.SourceType.UNTRUSTED,
    source_ref: str = "",
    evidence_excerpt: str = "",
    destination_type: str = "",
    destination_value: str = "",
    idempotency_key: str | None = None,
) -> tuple[SpendRequest, bool]:
    """Run one request through the pipeline and return (request, replayed)."""
    prepared = _prepare(
        amount=amount,
        currency=currency,
        merchant=merchant,
        purpose=purpose,
        source_type=source_type,
        source_ref=source_ref,
        evidence_excerpt=evidence_excerpt,
        destination_type=destination_type,
        destination_value=destination_value,
        idempotency_key=idempotency_key,
    )

    replay = _replay(agent.pk, idempotency_key, prepared.body_hash)
    if replay is not None:
        return replay, True

    screening = engine.screen_text(
        prepared.purpose, prepared.evidence_excerpt
    ).with_classifier(classifier.classify(prepared.purpose, prepared.evidence_excerpt))

    with transaction.atomic():
        agent = Agent.objects.select_for_update().get(pk=agent.pk)
        replay = _replay(agent.pk, idempotency_key, prepared.body_hash)
        if replay is not None:
            return replay, True

        policy = services.current_policy(agent, for_update=True)
        if policy is None:
            raise PolicyMissing(f"Agent {agent} has no policy.")

        now = timezone.now()
        spent = services.build_spent(agent, policy, prepared.currency, prepared.merchant_ref, now)
        payee = _payee_state(agent, policy, prepared, now)
        decision = _decide(
            prepared,
            policy,
            spent,
            screening,
            payee,
            agent_active=agent.status == Agent.Status.ACTIVE,
        )
        spend_request = _record_decision(
            agent=agent,
            policy=policy,
            prepared=prepared,
            decision=decision,
            now=now,
        )

    if spend_request.status == SpendRequest.Status.APPROVED:
        from apps.payments.dispatch import schedule_execution

        schedule_execution(spend_request.pk)

    return spend_request, False
