"""Business logic: gather state, run the rule engine, record the outcome."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from . import rules
from .models import Approval, AuditEvent, MerchantRule, Policy, SpendRequest


class PolicyMissing(Exception):
    """The agent has no policy, so nothing can be decided."""


def build_limits(policy: Policy) -> rules.PolicyLimits:
    merchant_rules = list(policy.merchant_rules.all())
    return rules.PolicyLimits(
        currency=policy.currency,
        per_transaction_cap=policy.per_transaction_cap,
        approval_threshold=policy.approval_threshold,
        daily_budget=policy.daily_budget,
        monthly_budget=policy.monthly_budget,
        allowed_merchants=frozenset(r.merchant for r in merchant_rules if r.action == MerchantRule.Action.ALLOW),
        blocked_merchants=frozenset(r.merchant for r in merchant_rules if r.action == MerchantRule.Action.BLOCK),
    )


def counted_spend(agent, currency: str, since) -> Decimal:
    """Money that counts against budgets: allowed requests plus approvals that are pending or approved.

    Denied requests and rejected approvals do not count. Counting pending approvals stops an agent
    from dodging a budget by queueing many requests that wait for a human.
    """
    counted = Q(decision=SpendRequest.Decision.ALLOW) | Q(
        decision=SpendRequest.Decision.NEEDS_APPROVAL,
        approval__outcome__in=[Approval.Outcome.PENDING, Approval.Outcome.APPROVED],
    )
    total = SpendRequest.objects.filter(
        counted, agent=agent, currency=currency, created_at__gte=since
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


@transaction.atomic
def submit_spend_request(agent, *, amount, currency, merchant, purpose="", source=rules.SOURCE_UNKNOWN):
    try:
        # Locks the policy row on databases that support it, so two requests cannot both pass a budget.
        policy = Policy.objects.select_for_update().get(agent=agent)
    except Policy.DoesNotExist as exc:
        raise PolicyMissing(f"Agent {agent} has no policy.") from exc

    spend_request = SpendRequest.objects.create(
        agent=agent,
        amount=amount,
        currency=currency.upper(),
        merchant=merchant,
        purpose=purpose,
        source=source,
    )
    AuditEvent.record(
        "spend_request.received",
        agent=agent,
        spend_request=spend_request,
        amount=str(amount),
        currency=spend_request.currency,
        merchant=merchant,
        source=source,
    )

    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    spent = rules.Spent(
        today=counted_spend(agent, policy.currency, day_start),
        this_month=counted_spend(agent, policy.currency, month_start),
    )

    decision = rules.evaluate(
        rules.SpendInput(
            amount=amount,
            currency=spend_request.currency,
            merchant=merchant,
            source=source,
        ),
        build_limits(policy),
        spent,
    )

    spend_request.decision = decision.outcome
    spend_request.reasons = [{"code": r.code, "message": r.message} for r in decision.reasons]
    spend_request.matched_rules = decision.matched_rules
    spend_request.save()

    AuditEvent.record(
        "spend_request.decided",
        agent=agent,
        spend_request=spend_request,
        decision=decision.outcome,
        rules=decision.matched_rules,
    )

    if decision.outcome == rules.NEEDS_APPROVAL:
        Approval.objects.create(spend_request=spend_request)
        AuditEvent.record("approval.requested", agent=agent, spend_request=spend_request)

    return spend_request
