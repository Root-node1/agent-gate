"""Policy creation with immutable versioning, normalization, and atomic audit.

Lock order follows the contract documented in ``docs/backend-crud-contract.html``:
Agent (select_for_update) -> Organization (acquired implicitly by AuditEvent).
This is a subsequence of the spend-service order Agent -> Policy -> Organization,
so it cannot deadlock with budget accounting on the same agent/organization.
"""

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404

from apps.accounts.models import OrgMembership
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.common.money import to_minor
from engine import normalize_merchant

from .models import MerchantRule, Policy

# (API major-unit field name, model minor-unit field name)
POLICY_MONEY_FIELDS = [
    ("per_transaction_cap", "per_transaction_cap_minor"),
    ("daily_budget", "daily_budget_minor"),
    ("weekly_budget", "weekly_budget_minor"),
    ("monthly_budget", "monthly_budget_minor"),
    ("approval_threshold", "approval_threshold_minor"),
    ("merchant_window_cap", "merchant_window_cap_minor"),
]


class PolicyConflictError(ValueError):
    """Surface a database constraint violation from policy creation to the view."""


def agent_owned_by_admin(user, agent_id):
    """Return the agent locked for update, or 404 if foreign/unknown to the caller.

    Scoping the lookup to admin memberships of the caller means a foreign-organization
    agent resolves to 404 (rather than 403) to avoid resource enumeration, matching
    the pattern used by AgentDetailView and AgentUpdateView.
    """
    return get_object_or_404(
        Agent.objects.select_for_update().filter(
            organization__memberships__user=user,
            organization__memberships__role=OrgMembership.Role.ADMIN,
        ),
        pk=agent_id,
    )


def next_policy_version(agent):
    """Highest existing version for the agent plus one (1 when none exist)."""
    latest = Policy.objects.filter(agent=agent).order_by("-version").first()
    return (latest.version if latest else 0) + 1


def build_policy_kwargs(validated):
    """Map validated major-unit input into model keyword arguments."""
    currency = validated["currency"]
    kwargs = {
        "currency": currency,
        "name": validated["name"],
        "merchant_mode": validated["merchant_mode"],
        "velocity_max_count": validated["velocity_max_count"],
        "velocity_window_seconds": validated["velocity_window_seconds"],
        "new_payee_cooldown_hours": validated["new_payee_cooldown_hours"],
        "untrusted_source_action": validated["untrusted_source_action"],
        "injection_escalate_threshold": validated["injection_escalate_threshold"],
        "classifier_required": validated["classifier_required"],
        "approval_ttl_minutes": validated["approval_ttl_minutes"],
        "timezone": validated["timezone"],
    }
    for api_name, db_name in POLICY_MONEY_FIELDS:
        value = validated.get(api_name)
        if value is not None:
            kwargs[db_name] = to_minor(value, currency)
    return kwargs


def create_policy_version(*, user, validated):
    """Create a new immutable policy version for an agent.

    ``validated`` is the ``validated_data`` from ``PolicyCreateSerializer``. The
    agent is looked up scoped to the caller's admin memberships (foreign agents
    404) and locked for update so concurrent creators serialize and the next
    version is monotonic. The policy row, its merchant rules and the
    ``policy.changed`` audit event are all written in one transaction; any
    failure rolls the whole operation back.
    """
    agent_id = validated["agent"]
    currency = validated["currency"]
    rules = validated.get("merchant_rules") or []
    fields_changed = sorted(
        name for name in validated if name not in ("agent", "currency", "merchant_rules")
    )

    policy_kwargs = build_policy_kwargs(validated)

    with transaction.atomic():
        agent = agent_owned_by_admin(user, agent_id)
        policy_kwargs["agent"] = agent
        policy_kwargs["version"] = next_policy_version(agent)

        try:
            policy = Policy.objects.create(**policy_kwargs)
        except IntegrityError as exc:
            raise PolicyConflictError("Policy could not be created.") from exc

        for rule in rules:
            MerchantRule.objects.create(
                policy=policy,
                merchant_ref=normalize_merchant(rule["merchant_ref"]),
                kind=rule["kind"],
                note=rule.get("note", ""),
            )

        AuditEvent.record(
            AuditEvent.EventType.POLICY_CHANGED,
            organization=agent.organization,
            agent=agent,
            actor_type=AuditEvent.ActorType.USER,
            actor_id=str(user.id),
            action="created",
            agent_id=str(agent.id),
            version=policy.version,
            name=policy.name,
            currency=currency,
            fields_changed=fields_changed,
        )

    return policy
