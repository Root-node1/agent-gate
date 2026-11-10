"""Django system checks for payment execution configuration.

Validates the PayPal sandbox configuration contract
(``PAYPAL_ENV``, ``PAYPAL_CHECKOUT_ENABLED``, ``PAYPAL_PAYOUTS_ENABLED``)
through :func:`apps.payments.paypal.config.get_paypal_config`.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register

from apps.payments.paypal.config import PayPalConfigError, get_paypal_config


@register(Tags.security)
def check_paypal_configuration(app_configs, **kwargs):
    """Fail closed when PayPal is selected without usable, non-live credentials."""
    errors = []
    try:
        get_paypal_config(settings)
    except PayPalConfigError as exc:
        errors.append(Error(str(exc), id="payments.E001"))
        return errors

    # Webhook ID is required when either PayPal feature is enabled, for
    # signature verification of incoming webhook events.
    checkout_enabled = _parse_bool(
        getattr(settings, "PAYPAL_CHECKOUT_ENABLED", "false"),
        "PAYPAL_CHECKOUT_ENABLED",
    )
    payouts_enabled = _parse_bool(
        getattr(settings, "PAYPAL_PAYOUTS_ENABLED", "false"),
        "PAYPAL_PAYOUTS_ENABLED",
    )
    if (checkout_enabled or payouts_enabled) and not getattr(
        settings, "PAYPAL_WEBHOOK_ID", ""
    ):
        errors.append(
            Error(
                "PayPal execution requires PAYPAL_WEBHOOK_ID for signature "
                "verification.",
                id="payments.E001",
            )
        )

    return errors


def _parse_bool(raw_value, label):
    """Parse a feature-flag value from raw string input."""
    if raw_value is None:
        return False
    normalized = str(raw_value).strip().lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0", ""}:
        return False
    return False


# Backwards-compatible alias used by tests.
check_paypal_config = check_paypal_configuration
