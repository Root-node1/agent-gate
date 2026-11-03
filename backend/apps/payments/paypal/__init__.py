"""PayPal REST boundary. Only the payments app may import this package."""

from .client import PayPalClient
from .exceptions import (
    PayPalAmbiguousResponse,
    PayPalAuthenticationError,
    PayPalConfigurationError,
    PayPalError,
    PayPalResponseError,
    PayPalTimeoutError,
    PayPalTransientError,
)
from .payouts import PayoutResult, create_payout, payout_payload

__all__ = [
    "PayPalAmbiguousResponse",
    "PayPalAuthenticationError",
    "PayPalClient",
    "PayPalConfigurationError",
    "PayPalError",
    "PayPalResponseError",
    "PayPalTimeoutError",
    "PayPalTransientError",
    "PayoutResult",
    "create_payout",
    "payout_payload",
]
