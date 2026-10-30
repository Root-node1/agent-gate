"""Django system checks for PayPal sandbox configuration (INT-13D).

Registered via ``apps/payments/apps.py`` → ``ready()`` so the check runs in
every context that invokes the Django check framework:

- ``manage.py check`` — all checks, including this one.
- ``manage.py runserver`` — Django calls ``run_checks()`` before booting.
- ``manage.py migrate``, ``manage.py test``, and other management commands
  that invoke ``check()``.

Validation rules:

- Only the ``"sandbox"`` environment is permitted.  ``"production"`` and any
  other value are rejected with a blocking ``Error``.
- Feature flags (``PAYPAL_CHECKOUT_ENABLED`` / ``PAYPAL_PAYOUTS_ENABLED``)
  must be valid boolean strings; malformed values are rejected.
- When a feature is enabled, its required credentials must be present.
- When both features are disabled, credentials are not required.
- No credential values appear in error messages.
"""

from django.core.checks import Error, register

from apps.payments.paypal.config import PayPalConfigError, get_paypal_config


@register()
def check_paypal_config(app_configs, **kwargs):
    """Validate PayPal sandbox configuration at startup.

    Delegates to :func:`apps.payments.paypal.config.get_paypal_config`,
    which raises :class:`PayPalConfigError` on the first violation found.
    The error message never includes credential values.
    """
    from django.conf import settings

    errors = []

    try:
        get_paypal_config(settings)
    except PayPalConfigError as exc:
        errors.append(Error(str(exc), id="payments.E001"))

    return errors
