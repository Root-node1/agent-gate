from decimal import Decimal

from rest_framework import serializers

from apps.common.currency import normalize_currency
from apps.common.money import to_major

from .models import SpendRequest

SOURCE_CHOICES = [
    *SpendRequest.SourceType.choices,
    ("untrusted", "Untrusted (legacy alias)"),
]
LEGACY_SOURCE_ALIASES = {"untrusted": SpendRequest.SourceType.WEB_PAGE}


class SpendRequestCreateSerializer(serializers.Serializer):
    """Validates a spend request. Unknown fields are rejected rather than ignored."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.CharField(min_length=3, max_length=3)
    merchant = serializers.CharField(max_length=255)
    purpose = serializers.CharField(required=False, allow_blank=True, default="", max_length=2_000)
    source = serializers.ChoiceField(
        choices=SOURCE_CHOICES,
        source="source_type",
        default=SpendRequest.SourceType.UNKNOWN,
    )
    source_ref = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)
    evidence_excerpt = serializers.CharField(required=False, allow_blank=True, default="", max_length=4_096)

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "Unknown field." for field in sorted(unknown)}
            )
        return super().to_internal_value(data)

    def validate_currency(self, value: str) -> str:
        return normalize_currency(value)

    def validate_source(self, value: str) -> str:
        return LEGACY_SOURCE_ALIASES.get(value, value)


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
