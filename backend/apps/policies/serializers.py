from rest_framework import serializers

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
