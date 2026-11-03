"""State queries used by the spend pipeline and approval rechecks."""

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

import engine
from apps.common.money import to_major
from apps.policies.models import MerchantRule, Policy

from .models import SpendRequest


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
        new_payee_cooldown_hours=policy.new_payee_cooldown_hours,
        injection_escalate_threshold=policy.injection_escalate_threshold,
        classifier_required=policy.classifier_required,
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
