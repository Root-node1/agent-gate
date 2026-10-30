"""DRF serializers for sandbox checkout order creation."""

from decimal import Decimal

from rest_framework import serializers

from apps.common.currency import normalize_currency
from apps.common.money import to_major

from ..models import CheckoutOrder

_CHECKOUT_READ_FIELDS = [
    "id",
    "organization",
    "amount",
    "currency",
    "paypal_order_id",
    "payer_action_url",
    "status",
    "idempotency_key",
    "created_at",
    "updated_at",
]


class CheckoutOrderCreateSerializer(serializers.Serializer):
    """Validate ``POST /v1/checkout-orders/`` input.

    Unknown fields are rejected (matches the strict-validation pattern in
    ``PolicyCreateSerializer`` and ``SpendRequestCreateSerializer``).
    """

    organization = serializers.UUIDField(required=True)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    currency = serializers.CharField(min_length=3, max_length=3)
    idempotency_key = serializers.UUIDField(required=True)

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "Unknown field." for field in sorted(unknown)}
            )
        return super().to_internal_value(data)

    def validate_currency(self, value: str) -> str:
        return normalize_currency(value)


class CheckoutOrderSerializer(serializers.ModelSerializer):
    """Read-only serialisation of a CheckoutOrder, amount in major units."""

    amount = serializers.SerializerMethodField()

    class Meta:
        model = CheckoutOrder
        fields = _CHECKOUT_READ_FIELDS
        read_only_fields = _CHECKOUT_READ_FIELDS

    def get_amount(self, obj) -> str:
        return str(to_major(obj.amount_minor, obj.currency))
