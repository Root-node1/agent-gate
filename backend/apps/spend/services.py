"""Business logic: gather state, run the rule engine, record the outcome."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

import engine
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.common.currency import normalize_currency
from apps.common.money import to_major, to_minor
from apps.payees.models import Payee, fingerprint, normalize_destination
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


def current_policy(agent, *, for_update: bool = False) -> Policy | None:
    """Return the newest policy version for an agent, or None when unset.

    Callers lock the agent row before this lookup. Pass ``for_update=True`` when the
    caller will create or change state that depends on this policy version, so the
    lock order stays agent, then policy.
    """
    policies = Policy.objects.filter(agent=agent).order_by("-version")
    if for_update:
        policies = policies.select_for_update()
    return policies.first()


def build_limits(policy: Policy) -> engine.PolicyLimits:
    merchant_rules = list(policy.merchant_rules.all())
    return engine.PolicyLimits(
        currency=policy.currency,
        per_transaction_cap=to_major(policy.per_transaction_cap_minor, policy.currency),
        approval_threshold=to_major(policy.approval_threshold_minor, policy.currency),
        daily_budget=to_major(policy.daily_budget_minor, policy.currency),
        weekly_budget=to_major(policy.weekly_budget_minor, policy.currency),
        monthly_budget=to_major(policy.monthly_budget_minor, policy.currency),
        merchant_window_cap=to_major(policy.merchant_window_cap_minor, policy.currency),
        velocity_max_count=policy.velocity_max_count,
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


def window_usage(agent, currency: str, merchant_ref: str, since) -> tuple[int, Decimal]:
    """Return budget-consuming request count and merchant spend since a cutoff."""
    usage = SpendRequest.objects.filter(
        agent=agent,
        currency=currency,
        status__in=SpendRequest.BUDGET_STATUSES,
        created_at__gte=since,
    ).aggregate(
        velocity_count=Count("id"),
        merchant_total=Sum("amount_minor", filter=Q(merchant_ref=merchant_ref)),
    )
    return usage["velocity_count"] or 0, to_major(usage["merchant_total"] or 0, currency)


def build_spent(agent, policy: Policy, currency: str, merchant_ref: str, now=None) -> engine.Spent:
    """Collect the budget and window usage used by both submission and recheck."""
    now = now or timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timezone.timedelta(days=day_start.weekday())
    month_start = day_start.replace(day=1)
    velocity_count = 0
    merchant_window_spend = Decimal("0")
    if policy.velocity_max_count or policy.merchant_window_cap_minor:
        window_start = now - timezone.timedelta(seconds=policy.velocity_window_seconds)
        velocity_count, merchant_window_spend = window_usage(
            agent, currency, merchant_ref, window_start
        )
    return engine.Spent(
        today=counted_spend(agent, currency, day_start),
        this_week=counted_spend(agent, currency, week_start),
        this_month=counted_spend(agent, currency, month_start),
        velocity_count=velocity_count,
        merchant_window_spend=merchant_window_spend,
    )


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

    policy = current_policy(agent, for_update=True)
    if policy is None:
        raise PolicyMissing(f"Agent {agent} has no policy.")

    now = timezone.now()
    spent = build_spent(agent, policy, currency, merchant_ref, now)

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

    if destination_type and decision.outcome != engine.DENY:
        defaults = {
            "destination_type": destination_type,
            "destination_value": destination_value,
            "destination_fingerprint": destination_fingerprint,
        }
        payee, created = Payee.objects.get_or_create(
            organization=agent.organization,
            merchant_ref=merchant_ref,
            defaults=defaults,
        )
        if not created and payee.destination_fingerprint != destination_fingerprint:
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
