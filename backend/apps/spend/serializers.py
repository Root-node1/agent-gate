from decimal import Decimal

from rest_framework import serializers

from apps.common.currency import normalize_currency
from apps.common.money import to_major
from apps.payees.models import DestinationType, normalize_destination

from .models import SpendRequest


class SpendRequestCreateSerializer(serializers.Serializer):
    """Validates a spend request. Unknown fields are rejected rather than ignored."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.CharField(min_length=3, max_length=3)
    merchant = serializers.CharField(max_length=255)
    purpose = serializers.CharField(required=False, allow_blank=True, default="", max_length=2_000)
    source = serializers.ChoiceField(
        choices=SpendRequest.SourceType.choices,
        source="source_type",
        default=SpendRequest.SourceType.UNTRUSTED,
    )
    source_ref = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)
    evidence_excerpt = serializers.CharField(required=False, allow_blank=True, default="", max_length=4_096)
    destination_type = serializers.ChoiceField(
        choices=DestinationType.choices, required=False, allow_blank=True, default=""
    )
    destination_value = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=500
    )

    def validate(self, attrs):
        destination_type = attrs.get("destination_type", "")
        destination_value = attrs.get("destination_value", "")
        if bool(destination_type) != bool(destination_value):
            raise serializers.ValidationError(
                {"destination_value": "Destination type and value must be provided together."}
            )
        if destination_type:
            attrs["destination_value"] = normalize_destination(destination_type, destination_value)
        return attrs

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "Unknown field." for field in sorted(unknown)}
            )
        return super().to_internal_value(data)

    def validate_currency(self, value: str) -> str:
        return normalize_currency(value)


class SpendRequestSerializer(serializers.ModelSerializer):
    amount = serializers.SerializerMethodField()
    merchant = serializers.CharField(source="merchant_ref", read_only=True)
    source = serializers.CharField(source="source_type", read_only=True)
    approval = serializers.SerializerMethodField()

    class Meta:
        model = SpendRequest
        fields = [
            "id",
            "amount",
            "currency",
            "merchant",
            "purpose",
            "source",
            "risk_score",
            "decision",
            "status",
            "reasons",
            "matched_rules",
            "paypal_reference",
            "created_at",
            "approval",
        ]
        read_only_fields = fields

    def get_amount(self, obj) -> str:
        return str(to_major(obj.amount_minor, obj.currency))

    def get_approval(self, obj) -> str | None:
        approval = getattr(obj, "approval", None)
        return approval.outcome if approval else None
