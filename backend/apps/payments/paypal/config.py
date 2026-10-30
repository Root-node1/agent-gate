"""PayPal sandbox configuration helpers and endpoint constants.

This module is intentionally minimal.  It exposes:

- Sandbox endpoint constants (``SANDBOX_API_BASE_URL``, ``SANDBOX_WEB_BASE_URL``).
- A parser (``get_paypal_config``) that validates PayPal settings read from
  Django's configuration object.

It does **NOT** implement OAuth token fetching, HTTP requests, checkout order
creation, capture, payout submission, webhook verification, or any PayPal
API calls.  Those belong to later tasks.
"""

from dataclasses import dataclass

#: The only permitted PayPal environment.
SUPPORTED_ENVIRONMENTS = ("sandbox",)

#: PayPal sandbox REST API base URL.
SANDBOX_API_BASE_URL = "https://api.sandbox.paypal.com"

#: PayPal sandbox web login base URL (for redirect-based checkout).
SANDBOX_WEB_BASE_URL = "https://www.sandbox.paypal.com"

_TRUE_VALUES = frozenset({"true", "yes", "1"})
_FALSE_VALUES = frozenset({"false", "no", "0", ""})


class PayPalConfigError(Exception):
    """Raised when PayPal configuration fails validation.

    Error messages never include credential values.
    """


@dataclass(frozen=True)
class PayPalConfig:
    """Immutable, validated PayPal configuration."""

    env: str
    client_id: str
    client_secret: str
    webhook_id: str
    checkout_enabled: bool
    payouts_enabled: bool


def _parse_bool(raw_value, label):
    """Parse a feature-flag value from raw string input.

    Accepts case-insensitive ``true``/``yes``/``1`` and ``false``/``no``/``0``
    /``""``.  Any other value raises :class:`PayPalConfigError`.
    """
    if raw_value is None:
        return False
    normalized = str(raw_value).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise PayPalConfigError(
        f"{label} must be a boolean string ('true' or 'false')."
    )


def get_paypal_config(settings):
    """Parse and validate PayPal configuration from a Django settings object.

    Returns a frozen :class:`PayPalConfig` on success.

    Raises :class:`PayPalConfigError` when:

    - ``PAYPAL_ENV`` is not ``"sandbox"`` (production and other values rejected).
    - ``PAYPAL_CHECKOUT_ENABLED`` or ``PAYPAL_PAYOUTS_ENABLED`` is not a valid
      boolean string.
    - A feature flag is enabled but the required credentials
      (``PAYPAL_CLIENT_ID`` / ``PAYPAL_CLIENT_SECRET``) are missing.

    No credential values (``client_id``, ``client_secret``, ``webhook_id``)
    are ever included in error messages.
    """
    env = getattr(settings, "PAYPAL_ENV", "sandbox")
    client_id = getattr(settings, "PAYPAL_CLIENT_ID", "")
    client_secret = getattr(settings, "PAYPAL_CLIENT_SECRET", "")
    webhook_id = getattr(settings, "PAYPAL_WEBHOOK_ID", "")

    checkout_enabled = _parse_bool(
        getattr(settings, "PAYPAL_CHECKOUT_ENABLED", "false"),
        "PAYPAL_CHECKOUT_ENABLED",
    )
    payouts_enabled = _parse_bool(
        getattr(settings, "PAYPAL_PAYOUTS_ENABLED", "false"),
        "PAYPAL_PAYOUTS_ENABLED",
    )

    if env not in SUPPORTED_ENVIRONMENTS:
        raise PayPalConfigError(
            f'PAYPAL_ENV must be "sandbox", got {env!r}.'
        )

    if checkout_enabled and not (client_id and client_secret):
        raise PayPalConfigError(
            "PAYPAL_CHECKOUT_ENABLED is enabled but PAYPAL_CLIENT_ID and/or "
            "PAYPAL_CLIENT_SECRET are not set."
        )

    if payouts_enabled and not (client_id and client_secret):
        raise PayPalConfigError(
            "PAYPAL_PAYOUTS_ENABLED is enabled but PAYPAL_CLIENT_ID and/or "
            "PAYPAL_CLIENT_SECRET are not set."
        )

    return PayPalConfig(
        env=env,
        client_id=client_id,
        client_secret=client_secret,
        webhook_id=webhook_id,
        checkout_enabled=checkout_enabled,
        payouts_enabled=payouts_enabled,
    )
