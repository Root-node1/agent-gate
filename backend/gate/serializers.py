from decimal import Decimal

from rest_framework import serializers

from .models import SpendRequest


class SpendRequestCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.CharField(min_length=3, max_length=3)
    merchant = serializers.CharField(max_length=255)
    purpose = serializers.CharField(required=False, allow_blank=True, default="")
    source = serializers.ChoiceField(choices=SpendRequest.Source.choices, default=SpendRequest.Source.UNKNOWN)


class SpendRequestSerializer(serializers.ModelSerializer):
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
            "reasons",
            "matched_rules",
            "paypal_reference",
            "created_at",
            "approval",
        ]
        read_only_fields = fields

    def get_approval(self, obj) -> str | None:
        approval = getattr(obj, "approval", None)
        return approval.outcome if approval else None
