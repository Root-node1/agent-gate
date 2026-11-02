from decimal import Decimal

from rest_framework import serializers

from apps.common.currency import normalize_currency
from engine import normalize_merchant

from .models import MerchantRule, Policy


class MerchantRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantRule
        fields = ["id", "merchant_ref", "kind", "note"]
        read_only_fields = fields


class PolicySerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.name", read_only=True)
    merchant_rules = MerchantRuleSerializer(many=True, read_only=True)

    class Meta:
        model = Policy
        fields = [
            "id",
            "organization",
            "agent",
            "agent_name",
            "name",
            "version",
            "currency",
            "per_transaction_cap_minor",
            "daily_budget_minor",
            "weekly_budget_minor",
            "monthly_budget_minor",
            "approval_threshold_minor",
            "merchant_mode",
            "velocity_max_count",
            "velocity_window_seconds",
            "merchant_window_cap_minor",
            "new_payee_cooldown_hours",
            "untrusted_source_action",
            "injection_escalate_threshold",
            "classifier_required",
            "approval_ttl_minutes",
            "timezone",
            "merchant_rules",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class MerchantRuleCreateSerializer(serializers.Serializer):
    """Input for POST /v1/policies/{id}/merchant-rules/.

    Carries the caller's ``expected_version`` optimistic-concurrency token
    alongside a single merchant rule to append.  Unknown fields are rejected
    with 400, matching the existing strict-validation pattern.
    """

    expected_version = serializers.IntegerField(min_value=1, required=True)
    merchant_ref = serializers.CharField(max_length=255)
    kind = serializers.ChoiceField(choices=MerchantRule.Kind.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def to_internal_value(self, data):
        _reject_unknown(data, self.fields)
        return super().to_internal_value(data)

    def validate_merchant_ref(self, value):
        return normalize_merchant(value)


class MerchantRuleInputSerializer(serializers.Serializer):
    """Input shape for a single merchant rule in a policy write."""

    merchant_ref = serializers.CharField(max_length=255)
    kind = serializers.ChoiceField(choices=MerchantRule.Kind.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "Unknown field." for field in sorted(unknown)}
            )
        return super().to_internal_value(data)


class PolicyCreateSerializer(serializers.Serializer):
    """Input validation for POST /v1/policies/. Rejects unknown fields."""

    agent = serializers.UUIDField()
    currency = serializers.CharField(min_length=3, max_length=3, default="USD")
    name = serializers.CharField(max_length=200, default="Default policy")
    per_transaction_cap = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    daily_budget = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    weekly_budget = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    monthly_budget = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    approval_threshold = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    merchant_window_cap = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    merchant_mode = serializers.ChoiceField(
        choices=Policy.MerchantMode.choices, default=Policy.MerchantMode.BLOCKLIST
    )
    velocity_max_count = serializers.IntegerField(min_value=0, default=0)
    velocity_window_seconds = serializers.IntegerField(min_value=1, default=3600)
    new_payee_cooldown_hours = serializers.IntegerField(min_value=0, default=0)
    untrusted_source_action = serializers.ChoiceField(
        choices=Policy.UntrustedSourceAction.choices,
        default=Policy.UntrustedSourceAction.NEEDS_APPROVAL,
    )
    injection_escalate_threshold = serializers.IntegerField(
        min_value=0, max_value=100, default=60
    )
    classifier_required = serializers.BooleanField(default=False)
    approval_ttl_minutes = serializers.IntegerField(min_value=0, default=60)
    timezone = serializers.CharField(max_length=64, default="Africa/Nairobi")
    merchant_rules = MerchantRuleInputSerializer(many=True, required=False)

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "Unknown field." for field in sorted(unknown)}
            )
        return super().to_internal_value(data)

    def validate_currency(self, value):
        return normalize_currency(value)

    def validate_timezone(self, value):
        from apps.common.validation import validate_timezone

        validate_timezone(value)
        return value

    def validate(self, attrs):
        rules = attrs.get("merchant_rules") or []
        allowed = set()
        blocked = set()
        for rule in rules:
            ref = normalize_merchant(rule["merchant_ref"])
            if ref in allowed or ref in blocked:
                raise serializers.ValidationError(
                    {"merchant_rules": f"Duplicate merchant rule for {ref!r}."}
                )
            if rule["kind"] == MerchantRule.Kind.ALLOW:
                if ref in blocked:
                    raise serializers.ValidationError(
                        {"merchant_rules": f"Merchant {ref!r} cannot be both allowed and blocked."}
                    )
                allowed.add(ref)
            else:
                if ref in allowed:
                    raise serializers.ValidationError(
                        {"merchant_rules": f"Merchant {ref!r} cannot be both allowed and blocked."}
                    )
                blocked.add(ref)

        cap = attrs.get("per_transaction_cap")
        threshold = attrs.get("approval_threshold")
        if cap is not None and threshold is not None and threshold > cap:
            raise serializers.ValidationError(
                {"approval_threshold": "Approval threshold cannot exceed the per-transaction cap."}
            )
        return attrs


def _reject_unknown(data, known_fields):
    unknown = set(data) - set(known_fields)
    if unknown:
        raise serializers.ValidationError(
            {field: "Unknown field." for field in sorted(unknown)}
        )


class PolicyUpdateSerializer(serializers.Serializer):
    """Partial update for ``PATCH /v1/policies/{id}/``.

    ``expected_version`` is the caller's optimistic-concurrency token: it must
    equal the agent's current latest policy version, otherwise the service
    returns 409 Conflict. Money fields arrive as major-unit decimals; any money
    or scalar field that is omitted is inherited from the latest version by the
    service layer, preserving its stored minor-unit value exactly. Supplying
    ``merchant_rules`` replaces the rule set on the new version; omitting it
    copies the latest version's rules verbatim. Unknown fields are rejected
    with 400 (as for ``PolicyCreateSerializer``).
    """

    expected_version = serializers.IntegerField(min_value=1, required=True)
    name = serializers.CharField(max_length=200, required=False)
    currency = serializers.CharField(min_length=3, max_length=3, required=False)
    per_transaction_cap = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    daily_budget = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    weekly_budget = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    monthly_budget = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    approval_threshold = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    merchant_window_cap = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    merchant_mode = serializers.ChoiceField(
        choices=Policy.MerchantMode.choices, required=False
    )
    velocity_max_count = serializers.IntegerField(min_value=0, required=False)
    velocity_window_seconds = serializers.IntegerField(min_value=1, required=False)
    new_payee_cooldown_hours = serializers.IntegerField(min_value=0, required=False)
    untrusted_source_action = serializers.ChoiceField(
        choices=Policy.UntrustedSourceAction.choices, required=False
    )
    injection_escalate_threshold = serializers.IntegerField(
        min_value=0, max_value=100, required=False
    )
    classifier_required = serializers.BooleanField(required=False)
    approval_ttl_minutes = serializers.IntegerField(min_value=0, required=False)
    timezone = serializers.CharField(max_length=64, required=False)
    merchant_rules = MerchantRuleInputSerializer(many=True, required=False)

    def to_internal_value(self, data):
        _reject_unknown(data, self.fields)
        return super().to_internal_value(data)

    def validate_currency(self, value):
        return normalize_currency(value)

    def validate_timezone(self, value):
        from apps.common.validation import validate_timezone

        validate_timezone(value)
        return value

    def validate(self, attrs):
        rules = attrs.get("merchant_rules") or []
        allowed = set()
        blocked = set()
        for rule in rules:
            ref = normalize_merchant(rule["merchant_ref"])
            if rule["kind"] == MerchantRule.Kind.ALLOW:
                if ref in blocked:
                    raise serializers.ValidationError(
                        {"merchant_rules": f"Merchant {ref!r} cannot be both allowed and blocked."}
                    )
                allowed.add(ref)
            else:
                if ref in allowed:
                    raise serializers.ValidationError(
                        {"merchant_rules": f"Merchant {ref!r} cannot be both allowed and blocked."}
                    )
                blocked.add(ref)

        cap = attrs.get("per_transaction_cap")
        threshold = attrs.get("approval_threshold")
        if cap is not None and threshold is not None and threshold > cap:
            raise serializers.ValidationError(
                {"approval_threshold": "Approval threshold cannot exceed the per-transaction cap."}
            )
        return attrs
