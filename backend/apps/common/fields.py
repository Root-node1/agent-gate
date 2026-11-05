"""Serializer fields that reject ambiguous or unsafe input."""

from rest_framework import serializers

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
