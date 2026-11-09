"""Payout reservation serializers (INT-13I)."""

from rest_framework import serializers

from apps.payments.payouts.models import PayoutReservation


class PayoutReservationCreateSerializer(serializers.Serializer):
    """Validate ``POST /v1/payout-reservations/`` input.

    Only the SpendRequest and the caller-supplied idempotency key are
    accepted.  Amount, currency, and destination are taken from the immutable
    SpendRequest snapshot; the client may not override them.
    """

    spend_request = serializers.UUIDField(required=True)
    idempotency_key = serializers.UUIDField(required=True)

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "Unknown field." for field in sorted(unknown)}
            )
        return super().to_internal_value(data)


class PayoutReservationSerializer(serializers.ModelSerializer):
    """Read-only serialisation of a PayoutReservation, amount in major units."""

    from apps.common.money import to_major

    amount = serializers.SerializerMethodField()

    class Meta:
        model = PayoutReservation
        fields = [
            "id",
            "organization",
            "spend_request",
            "payee",
            "amount",
            "currency",
            "destination_type",
            "destination_value",
            "destination_fingerprint",
            "status",
            "idempotency_key",
            "paypal_payout_batch_id",
            "paypal_payout_item_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_amount(self, obj) -> str:
        from apps.common.money import to_major

        return str(to_major(obj.amount_minor, obj.currency))
