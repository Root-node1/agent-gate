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
    """Optimistic-concurrency conflict on policy versioning (view maps to 409)."""


class PolicyValidationError(ValueError):
    """A supplied or inherited policy field violates a model constraint (view maps to 400)."""


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


def create_policy_update(*, user, policy_id, validated):
    """Create a new immutable policy version from the latest version of an agent's policy.

    ``validated`` is the ``validated_data`` from ``PolicyUpdateSerializer``: it
    carries the caller's ``expected_version`` optimistic-concurrency token plus
    any supplied overrides. The policy referenced by ``policy_id`` must already
    be the agent's current latest version, and ``expected_version`` must match
    that version; otherwise a :class:`PolicyConflictError` (mapped to 409 by the
    view) is raised.

    The agent row is locked with ``select_for_update`` so concurrent creators on
    the same agent serialize and can never produce the same ``(agent, version)``
    pair, which also prevents deadlocks with the spend-service lock order
    (Agent -> Policy -> ... -> Organization). All field values are inherited
    from the latest version unless overridden; money fields are converted from
    major-unit decimals using the resolved currency (inherited or supplied).
    """
    overrides = dict(validated)
    expected_version = overrides.pop("expected_version")
    merchant_rules_supplied = "merchant_rules" in overrides
    supplied_rules = overrides.pop("merchant_rules", None)

    with transaction.atomic():
        target = get_object_or_404(
            Policy.objects.select_related("agent").filter(
                organization__memberships__user=user,
                organization__memberships__role=OrgMembership.Role.ADMIN,
            ),
            pk=policy_id,
        )
        agent = Agent.objects.select_for_update().get(pk=target.agent_id)
        latest = Policy.objects.filter(agent=agent).order_by("-version").first()

        if latest is None or latest.pk != target.pk:
            raise PolicyConflictError(
                "Policy has been updated since you read it; PATCH the latest version."
            )
        if expected_version != latest.version:
            raise PolicyConflictError(
                f"Expected version {latest.version}, but the request carries {expected_version}."
            )

        next_version = latest.version + 1

        currency = overrides.get("currency") or latest.currency
        field_values = {
            "name": overrides.get("name", latest.name),
            "currency": currency,
            "merchant_mode": overrides.get("merchant_mode", latest.merchant_mode),
            "velocity_max_count": overrides.get(
                "velocity_max_count", latest.velocity_max_count
            ),
            "velocity_window_seconds": overrides.get(
                "velocity_window_seconds", latest.velocity_window_seconds
            ),
            "new_payee_cooldown_hours": overrides.get(
                "new_payee_cooldown_hours", latest.new_payee_cooldown_hours
            ),
            "untrusted_source_action": overrides.get(
                "untrusted_source_action", latest.untrusted_source_action
            ),
            "injection_escalate_threshold": overrides.get(
                "injection_escalate_threshold", latest.injection_escalate_threshold
            ),
            "classifier_required": overrides.get(
                "classifier_required", latest.classifier_required
            ),
            "approval_ttl_minutes": overrides.get(
                "approval_ttl_minutes", latest.approval_ttl_minutes
            ),
            "timezone": overrides.get("timezone", latest.timezone),
        }
        for api_name, db_name in POLICY_MONEY_FIELDS:
            if api_name in overrides:
                field_values[db_name] = to_minor(overrides[api_name], currency)
            else:
                field_values[db_name] = getattr(latest, db_name)

        if field_values["approval_threshold_minor"] > field_values["per_transaction_cap_minor"]:
            raise PolicyValidationError(
                "Approval threshold cannot exceed the per-transaction cap."
            )

        new_policy = Policy.objects.create(
            agent=agent, version=next_version, **field_values
        )

        if merchant_rules_supplied:
            for rule in supplied_rules or []:
                MerchantRule.objects.create(
                    policy=new_policy,
                    merchant_ref=normalize_merchant(rule["merchant_ref"]),
                    kind=rule["kind"],
                    note=rule.get("note", ""),
                )
        else:
            for rule in latest.merchant_rules.all():
                MerchantRule.objects.create(
                    policy=new_policy,
                    merchant_ref=rule.merchant_ref,
                    kind=rule.kind,
                    note=rule.note,
                )

        fields_changed = sorted(overrides.keys())
        if merchant_rules_supplied:
            fields_changed.append("merchant_rules")
            fields_changed.sort()

        AuditEvent.record(
            AuditEvent.EventType.POLICY_CHANGED,
            organization=agent.organization,
            agent=agent,
            actor_type=AuditEvent.ActorType.USER,
            actor_id=str(user.id),
            action="updated",
            agent_id=str(agent.id),
            new_version=new_policy.version,
            old_version=latest.version,
            fields_changed=fields_changed,
        )

    return new_policy
