"""Conversions between major-unit decimals and integer minor units."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .currency import minor_unit

AMOUNT_ERROR = (
    "Amount must be a positive decimal string with at most 12 digits and no more "
    "decimal places than the currency allows."
)
AMOUNT_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
MAX_AMOUNT_DIGITS = 12


def parse_amount(value: str, currency: str) -> Decimal:
    """Parse a strict decimal string using the currency's minor-unit scale."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(AMOUNT_ERROR)
    match = AMOUNT_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(AMOUNT_ERROR)

    integer, _, fraction = value.partition(".")
    significant_integer = len(integer.lstrip("0"))
    if significant_integer + len(fraction) > MAX_AMOUNT_DIGITS:
        raise ValueError(AMOUNT_ERROR)

    exponent = minor_unit(currency)
    if exponent == 0:
        if fraction:
            raise ValueError(AMOUNT_ERROR)
    elif len(fraction) > exponent:
        raise ValueError(AMOUNT_ERROR)

    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(AMOUNT_ERROR) from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError(AMOUNT_ERROR)
    return amount


def to_minor(amount: Decimal, currency: str) -> int:
    """Convert a major-unit amount to integer minor units."""
    exponent = minor_unit(currency)
    quantized = Decimal(amount).quantize(Decimal(1).scaleb(-exponent), rounding=ROUND_HALF_UP)
    return int(quantized.scaleb(exponent))


def to_major(amount_minor: int, currency: str) -> Decimal:
    """Convert integer minor units to a major-unit decimal."""
    exponent = minor_unit(currency)
    return Decimal(amount_minor).scaleb(-exponent)
