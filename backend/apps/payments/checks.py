"""Django system checks for payment execution configuration."""

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def check_paypal_configuration(app_configs, **kwargs):
    """Fail closed when PayPal is selected without usable, non-live credentials."""
    errors = []
    executor = getattr(settings, "PAYMENT_EXECUTOR", "fake")
    mode = getattr(settings, "PAYPAL_MODE", "sandbox")

    if executor not in {"fake", "paypal"}:
        errors.append(
            Error(
                f"PAYMENT_EXECUTOR must be 'fake' or 'paypal', not {executor!r}.",
                id="payments.E001",
            )
        )

    if mode not in {"sandbox", "live"}:
        errors.append(
            Error(
                f"PAYPAL_MODE must be 'sandbox' or 'live', not {mode!r}.",
                id="payments.E002",
            )
        )

    if mode == "live" and not getattr(settings, "PAYPAL_ALLOW_LIVE", False):
        errors.append(
            Error(
                "Live PayPal credentials are disabled; set PAYPAL_ALLOW_LIVE=1 "
                "only when live movement is intentional.",
                id="payments.E003",
            )
        )

    if executor == "paypal":
        missing = [
            name
            for name in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET")
            if not getattr(settings, name, "")
        ]
        if missing:
            errors.append(
                Error(
                    f"PAYMENT_EXECUTOR=paypal requires {', '.join(missing)}.",
                    id="payments.E004",
                )
            )
        if not getattr(settings, "PAYPAL_WEBHOOK_ID", ""):
            errors.append(
                Error(
                    "PAYMENT_EXECUTOR=paypal requires PAYPAL_WEBHOOK_ID for "
                    "signature verification.",
                    id="payments.E005",
                )
            )

    if getattr(settings, "WEBHOOK_RETENTION_DAYS", 0) < 1:
        errors.append(
            Error(
                "WEBHOOK_RETENTION_DAYS must be at least 1.",
                id="payments.E006",
            )
        )

    return errors


# Backwards-compatible alias used by tests.
check_paypal_config = check_paypal_configuration
