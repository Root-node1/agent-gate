"""Business logic: gather state, run the rule engine, record the outcome."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

import engine
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.common.currency import normalize_currency
from apps.common.money import to_major, to_minor
from apps.payees.models import fingerprint, normalize_destination
from apps.policies.models import MerchantRule, Policy

from .idempotency import request_hash
from .models import SpendRequest

OUTCOME_STATUS = {
    engine.ALLOW: SpendRequest.Status.APPROVED,
    engine.DENY: SpendRequest.Status.DENIED,
    engine.NEEDS_APPROVAL: SpendRequest.Status.PENDING_APPROVAL,
}


class PolicyMissing(Exception):
    """The agent has no policy, so nothing can be decided."""


class IdempotencyConflict(Exception):
    """The same key was reused with a different request body."""


def rule_source(source_type: str) -> str:
    """Map the stored provenance to the engine's three-level trust model."""
    if source_type == SpendRequest.SourceType.TRUSTED:
        return engine.SOURCE_TRUSTED
    if source_type == SpendRequest.SourceType.UNKNOWN:
        return engine.SOURCE_UNKNOWN
    return engine.SOURCE_UNTRUSTED


def current_policy(agent) -> Policy | None:
    """Return the newest policy version for an agent, or None when unset.

    The caller holds the agent row lock, which serializes policy reads and budget
    accounting for that agent.
    """
    return Policy.objects.filter(agent=agent).order_by("-version").first()


def build_limits(policy: Policy) -> engine.PolicyLimits:
    merchant_rules = list(policy.merchant_rules.all())
    return engine.PolicyLimits(
        currency=policy.currency,
        per_transaction_cap=to_major(policy.per_transaction_cap_minor, policy.currency),
        approval_threshold=to_major(policy.approval_threshold_minor, policy.currency),
        daily_budget=to_major(policy.daily_budget_minor, policy.currency),
        monthly_budget=to_major(policy.monthly_budget_minor, policy.currency),
        allowed_merchants=frozenset(
            r.merchant_ref for r in merchant_rules if r.kind == MerchantRule.Kind.ALLOW
        ),
        blocked_merchants=frozenset(
            r.merchant_ref for r in merchant_rules if r.kind == MerchantRule.Kind.BLOCK
        ),
        untrusted_source_action=policy.untrusted_source_action,
    )


def counted_spend(agent, currency: str, since) -> Decimal:
    """Money counted against budgets: requests that are approved, executing, or succeeded."""
    total = (
        SpendRequest.objects.filter(
            agent=agent,
            currency=currency,
            status__in=SpendRequest.BUDGET_STATUSES,
            created_at__gte=since,
        ).aggregate(total=Sum("amount_minor"))["total"]
        or 0
    )
    return to_major(total, currency)


@transaction.atomic
def submit_spend_request(
    agent,
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
):
    agent = Agent.objects.select_for_update().get(pk=agent.pk)

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
    if idempotency_key:
        existing = SpendRequest.objects.filter(
            agent=agent, idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            if existing.request_hash != body_hash:
                raise IdempotencyConflict("Idempotency-Key was reused with a different request.")
            return existing, True

    policy = current_policy(agent)
    if policy is None:
        raise PolicyMissing(f"Agent {agent} has no policy.")

    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    spent = engine.Spent(
        today=counted_spend(agent, currency, day_start),
        this_month=counted_spend(agent, currency, month_start),
    )

    decision = engine.evaluate(
        engine.SpendInput(
            amount=amount,
            currency=currency,
            merchant=merchant_ref,
            source=rule_source(source_type),
            purpose=purpose,
            evidence_excerpt=evidence_excerpt,
            agent_active=agent.status == Agent.Status.ACTIVE,
        ),
        build_limits(policy),
        spent,
    )

    spend_request = SpendRequest.objects.create(
        organization=agent.organization,
        agent=agent,
        policy=policy,
        policy_version=policy.version,
        idempotency_key=idempotency_key,
        request_hash=body_hash,
        amount_minor=amount_minor,
        currency=currency,
        merchant_ref=merchant_ref,
        destination_type=destination_type,
        destination_value=destination_value,
        destination_fingerprint=destination_fingerprint,
        purpose=purpose,
        source_type=source_type,
        source_ref=source_ref,
        evidence_excerpt=evidence_excerpt,
        risk_score=0,
        decision=decision.outcome,
        status=OUTCOME_STATUS[decision.outcome],
        reasons=[{"code": r.code, "message": r.message} for r in decision.reasons],
        matched_rules=decision.matched_rules,
        decided_at=now,
    )

    AuditEvent.record(
        AuditEvent.EventType.REQUEST_RECEIVED,
        organization=agent.organization,
        agent=agent,
        spend_request=spend_request,
        actor_type=AuditEvent.ActorType.AGENT,
        actor_id=str(agent.id),
        amount=str(amount),
        currency=currency,
        merchant=merchant_ref,
        source_type=source_type,
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

    return spend_request, False
