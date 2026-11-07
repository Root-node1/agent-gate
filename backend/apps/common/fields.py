"""Serializer fields that reject ambiguous or unsafe input."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.fields import empty

from .currency import minor_unit, normalize_currency
from .money import AMOUNT_ERROR, AMOUNT_PATTERN
from .text import neutralize_text


class DecimalStringField(serializers.CharField):
    """Accept only a decimal string; numbers, signs, exponents, and spaces fail."""

    default_error_messages = {"invalid": AMOUNT_ERROR}

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 32)
        kwargs.setdefault("trim_whitespace", False)
        kwargs.setdefault("allow_blank", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str) or AMOUNT_PATTERN.fullmatch(data) is None:
            self.fail("invalid")
        return super().to_internal_value(data)


class CurrencyDecimalField(serializers.DecimalField):
    """Decimal field that rejects precision the currency cannot represent."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 4)
        super().__init__(**kwargs)

    def _currency(self) -> str | None:
        parent = self.parent
        if parent is None:
            return None

        raw = None
        data = getattr(parent, "initial_data", None)
        if isinstance(data, dict):
            raw = data.get("currency")
        if raw is None:
            raw = parent.context.get("currency")
        if raw is None:
            currency_field = parent.fields.get("currency")
            if currency_field is not None and currency_field.default is not empty:
                raw = currency_field.get_default()
        if not raw:
            return None

        try:
            return normalize_currency(str(raw))
        except DjangoValidationError:
            return None

    def validate_precision(self, value):
        currency = self._currency()
        if currency is not None:
            exponent = minor_unit(currency)
            fractional_digits = max(0, -value.as_tuple().exponent)
            if fractional_digits > exponent:
                self.fail("max_decimal_places", max_decimal_places=exponent)
        return super().validate_precision(value)


class NeutralizedCharField(serializers.CharField):
    """Strip bidi and control characters before length validation and storage."""

    def __init__(self, **kwargs):
        self.allow_newlines = kwargs.pop("allow_newlines", True)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        cleaned = neutralize_text(value, allow_newlines=self.allow_newlines)
        if cleaned == "" and not self.allow_blank:
            self.fail("blank")
        return cleaned
