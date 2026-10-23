"""Copy rows from the original gate tables into the per-domain apps before they are dropped."""

from django.db import migrations

from apps.common.money import to_minor

SOURCE_MAP = {
    "trusted": "trusted",
    "untrusted": "web_page",
    "unknown": "unknown",
}

STATUS_MAP = {
    "allow": "approved",
    "deny": "denied",
    "needs_approval": "pending_approval",
}


def forwards(apps, schema_editor):
    LegacyAgent = apps.get_model("gate", "Agent")
    if not LegacyAgent.objects.exists():
        return

    Organization = apps.get_model("accounts", "Organization")
    Agent = apps.get_model("agents", "Agent")
    ApiKey = apps.get_model("agents", "ApiKey")
    Policy = apps.get_model("policies", "Policy")
    MerchantRule = apps.get_model("policies", "MerchantRule")
    SpendRequest = apps.get_model("spend", "SpendRequest")
    Approval = apps.get_model("approvals", "Approval")
    AuditEvent = apps.get_model("audit", "AuditEvent")

    organization, _ = Organization.objects.get_or_create(name="Legacy")

    agent_map = {}
    for legacy in LegacyAgent.objects.all():
        agent = Agent.objects.create(
            organization=organization,
            name=legacy.name,
            status=legacy.status,
        )
        # Only the old key hash exists, so the raw secret cannot be reissued as a new-format
        # key. Carry the key over revoked so migrated agents fail closed until a key is rotated.
        ApiKey.objects.create(
            agent=agent,
            prefix=(legacy.api_key_prefix or "legacy")[:16],
            key_hash=legacy.api_key_hash,
            revoked_at=legacy.created_at,
        )
        agent_map[legacy.pk] = agent

    policy_by_agent = {}
    policy_map = {}
    for legacy in apps.get_model("gate", "Policy").objects.all():
        currency = (legacy.currency or "USD").upper()[:3]
        policy = Policy.objects.create(
            organization=organization,
            agent=agent_map[legacy.agent_id],
            currency=currency,
            per_transaction_cap_minor=to_minor(legacy.per_transaction_cap, currency),
            approval_threshold_minor=to_minor(legacy.approval_threshold, currency),
            daily_budget_minor=to_minor(legacy.daily_budget, currency),
            monthly_budget_minor=to_minor(legacy.monthly_budget, currency),
        )
        policy_by_agent[legacy.agent_id] = policy
        policy_map[legacy.pk] = policy

    for legacy in apps.get_model("gate", "MerchantRule").objects.all():
        MerchantRule.objects.create(
            policy=policy_map[legacy.policy_id],
            merchant_ref=legacy.merchant,
            kind=legacy.action,
            note=legacy.note,
        )

    spend_map = {}
    for legacy in apps.get_model("gate", "SpendRequest").objects.all():
        currency = (legacy.currency or "USD").upper()[:3]
        decision = legacy.decision if legacy.decision in STATUS_MAP else "deny"
        policy = policy_by_agent[legacy.agent_id]
        spend = SpendRequest.objects.create(
            organization=organization,
            agent=agent_map[legacy.agent_id],
            policy=policy,
            policy_version=policy.version,
            amount_minor=to_minor(legacy.amount, currency),
            currency=currency,
            merchant_ref=legacy.merchant,
            purpose=legacy.purpose[:2000],
            source_type=SOURCE_MAP.get(legacy.source, "unknown"),
            risk_score=min(legacy.risk_score or 0, 100),
            decision=decision,
            status=STATUS_MAP[decision],
            reasons=legacy.reasons or [],
            matched_rules=legacy.matched_rules or [],
            paypal_reference=legacy.paypal_reference or None,
        )
        spend_map[legacy.pk] = spend

    for legacy in apps.get_model("gate", "Approval").objects.all():
        approval = Approval.objects.create(
            organization=organization,
            spend_request=spend_map[legacy.spend_request_id],
            outcome=legacy.outcome,
            note=legacy.note,
            expires_at=legacy.created_at,
        )
        if legacy.decided_at:
            Approval.objects.filter(pk=approval.pk).update(decided_at=legacy.decided_at)

    for legacy in apps.get_model("gate", "AuditEvent").objects.all():
        AuditEvent.objects.create(
            organization=organization,
            agent=agent_map.get(legacy.agent_id),
            spend_request=spend_map.get(legacy.spend_request_id),
            event_type=legacy.event_type,
            payload=legacy.payload or {},
        )


def backwards(apps, schema_editor):
    """The legacy tables are dropped by the following migration, so there is nothing to restore."""


class Migration(migrations.Migration):

    dependencies = [
        ("gate", "0001_initial"),
        ("accounts", "0001_initial"),
        ("agents", "0001_initial"),
        ("policies", "0001_initial"),
        ("payees", "0001_initial"),
        ("spend", "0001_initial"),
        ("approvals", "0001_initial"),
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
