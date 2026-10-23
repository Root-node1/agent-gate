"""Conversions between major-unit decimals and integer minor units."""

from decimal import ROUND_HALF_UP, Decimal

from .currency import minor_unit


def to_minor(amount: Decimal, currency: str) -> int:
    """Convert a major-unit amount to integer minor units."""
    exponent = minor_unit(currency)
    quantized = Decimal(amount).quantize(Decimal(1).scaleb(-exponent), rounding=ROUND_HALF_UP)
    return int(quantized.scaleb(exponent))


def to_major(amount_minor: int, currency: str) -> Decimal:
    """Convert integer minor units to a major-unit decimal."""
    exponent = minor_unit(currency)
    return Decimal(amount_minor).scaleb(-exponent)
