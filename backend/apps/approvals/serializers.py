"""Dashboard representations of approvals and the pending spend request."""

from rest_framework import serializers

from apps.common.money import to_major

from .models import Approval


class ApprovalSerializer(serializers.ModelSerializer):
    spend_request = serializers.UUIDField(source="spend_request_id", read_only=True)
    agent = serializers.UUIDField(source="spend_request.agent_id", read_only=True)
    agent_name = serializers.CharField(source="spend_request.agent.name", read_only=True)
    amount = serializers.SerializerMethodField()
    currency = serializers.CharField(source="spend_request.currency", read_only=True)
    merchant = serializers.CharField(source="spend_request.merchant_ref", read_only=True)
    purpose = serializers.CharField(source="spend_request.purpose", read_only=True)
    source = serializers.CharField(source="spend_request.source_type", read_only=True)
    decision = serializers.CharField(source="spend_request.decision", read_only=True)
    status = serializers.CharField(source="spend_request.status", read_only=True)
    matched_rules = serializers.JSONField(source="spend_request.matched_rules", read_only=True)
    reasons = serializers.JSONField(source="spend_request.reasons", read_only=True)
    approver = serializers.UUIDField(source="approver_id", read_only=True, allow_null=True)

    class Meta:
        model = Approval
        fields = [
            "id",
            "organization",
            "spend_request",
            "agent",
            "agent_name",
            "amount",
            "currency",
            "merchant",
            "purpose",
            "source",
            "decision",
            "status",
            "matched_rules",
            "reasons",
            "outcome",
            "approver",
            "note",
            "requested_at",
            "expires_at",
            "decided_at",
        ]
        read_only_fields = fields

    def get_amount(self, obj) -> str:
        return str(to_major(obj.spend_request.amount_minor, obj.spend_request.currency))


class DecisionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)
