from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.common.currency import normalize_currency
from apps.common.fields import DecimalStringField, NeutralizedCharField
from apps.common.money import parse_amount, to_major
from apps.payees.models import DestinationType, normalize_destination

from .models import SpendRequest


class SpendRequestCreateSerializer(serializers.Serializer):
    """Validates a spend request. Unknown fields are rejected rather than ignored."""

    amount = DecimalStringField()
    currency = serializers.CharField(min_length=3, max_length=3)
    merchant = NeutralizedCharField(max_length=255, allow_newlines=False)
    purpose = NeutralizedCharField(required=False, allow_blank=True, default="", max_length=2_000)
    source = serializers.ChoiceField(
        choices=SpendRequest.SourceType.choices,
        source="source_type",
        default=SpendRequest.SourceType.UNTRUSTED,
        error_messages={"invalid_choice": "Select a valid choice."},
    )
    source_ref = NeutralizedCharField(
        required=False, allow_blank=True, default="", max_length=500, allow_newlines=False
    )
    evidence_excerpt = NeutralizedCharField(
        required=False, allow_blank=True, default="", max_length=4_096
    )
    destination_type = serializers.ChoiceField(
        choices=DestinationType.choices,
        required=False,
        allow_blank=True,
        default="",
        error_messages={"invalid_choice": "Select a valid choice."},
    )
    destination_value = NeutralizedCharField(
        required=False, allow_blank=True, default="", max_length=500, allow_newlines=False
    )

    def validate_currency(self, value):
        try:
            return normalize_currency(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                "Enter a valid ISO-4217 currency code."
            ) from exc

    def validate(self, attrs):
        amount = attrs.get("amount")
        currency = attrs.get("currency")
        if amount is not None and currency:
            try:
                attrs["amount"] = parse_amount(amount, currency)
            except ValueError as exc:
                raise serializers.ValidationError({"amount": [str(exc)]}) from exc

        destination_type = attrs.get("destination_type", "")
        destination_value = attrs.get("destination_value", "")
        if bool(destination_type) != bool(destination_value):
            raise serializers.ValidationError(
                {"destination_value": "Destination type and value must be provided together."}
            )
        if destination_type:
            normalized = normalize_destination(destination_type, destination_value)
            if not normalized:
                raise serializers.ValidationError(
                    {"destination_value": "Destination value must not be blank."}
                )
            attrs["destination_value"] = normalized
        return attrs

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "Unknown field." for field in sorted(unknown)}
            )
        return super().to_internal_value(data)

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
