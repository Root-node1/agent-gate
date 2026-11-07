"""ISO-4217 currency validation and normalization."""

from django.core.exceptions import ValidationError

ISO_4217 = frozenset(
    {
        "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
        "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BOV",
        "BRL", "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHE", "CHF",
        "CHW", "CLF", "CLP", "CNY", "COP", "COU", "CRC", "CUC", "CUP", "CVE",
        "CZK", "DJF", "DKK", "DOP", "DZD", "EGP", "ERN", "ETB", "EUR", "FJD",
        "FKP", "GBP", "GEL", "GHS", "GIP", "GMD", "GNF", "GTQ", "GYD", "HKD",
        "HNL", "HRK", "HTG", "HUF", "IDR", "ILS", "INR", "IQD", "IRR", "ISK",
        "JMD", "JOD", "JPY", "KES", "KGS", "KHR", "KMF", "KPW", "KRW", "KWD",
        "KYD", "KZT", "LAK", "LBP", "LKR", "LRD", "LSL", "LYD", "MAD", "MDL",
        "MGA", "MKD", "MMK", "MNT", "MOP", "MRU", "MUR", "MVR", "MWK", "MXN",
        "MXV", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK", "NPR", "NZD", "OMR",
        "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG", "QAR", "RON", "RSD",
        "RUB", "RWF", "SAR", "SBD", "SCR", "SDG", "SEK", "SGD", "SHP", "SLE",
        "SLL", "SOS", "SRD", "SSP", "STN", "SVC", "SYP", "SZL", "THB", "TJS",
        "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX", "USD",
        "USN", "UYI", "UYU", "UYW", "UZS", "VED", "VES", "VND", "VUV", "WST",
        "XAF", "XAG", "XAU", "XBA", "XBB", "XBC", "XBD", "XCD", "XDR", "XOF",
        "XPD", "XPF", "XPT", "XSU", "XTS", "XUA", "XXX", "YER", "ZAR", "ZMW",
        "ZWL",
    }
)

ZERO_DECIMAL = frozenset(
    {
        "BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF",
        "UGX", "UYI", "VND", "VUV", "XAF", "XOF", "XPF",
    }
)
THREE_DECIMAL = frozenset({"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"})
FOUR_DECIMAL = frozenset({"CLF", "UYW"})

MINOR_UNIT_EXPONENTS = {
    code: (
        0
        if code in ZERO_DECIMAL
        else 3
        if code in THREE_DECIMAL
        else 4
        if code in FOUR_DECIMAL
        else 2
    )
    for code in ISO_4217
}


def normalize_currency(value: str) -> str:
    """Return the canonical uppercase code or raise ValidationError."""
    code = value.strip().upper()
    if code not in ISO_4217:
        raise ValidationError("Enter a valid ISO-4217 currency code.")
    return code


def minor_unit(currency: str) -> int:
    """Return the ISO-4217 decimal exponent for a currency."""
    return MINOR_UNIT_EXPONENTS.get(currency.upper(), 2)


def validate_currency(value: str) -> None:
    """Django field validator that accepts only ISO-4217 codes."""
    normalize_currency(value)
