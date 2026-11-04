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
from .webhooks import (
    PayoutEvent,
    WebhookSignature,
    parse_payout_event,
    read_signature,
    verify_webhook_signature,
)

__all__ = [
    "PayPalAmbiguousResponse",
    "PayPalAuthenticationError",
    "PayPalClient",
    "PayPalConfigurationError",
    "PayPalError",
    "PayPalResponseError",
    "PayPalTimeoutError",
    "PayPalTransientError",
    "PayoutEvent",
    "PayoutResult",
    "WebhookSignature",
    "create_payout",
    "parse_payout_event",
    "payout_payload",
    "read_signature",
    "verify_webhook_signature",
]
