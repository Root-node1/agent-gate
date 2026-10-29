"""Django system checks for MFA encryption-key validation (AUTH-05B.2D).

Registered via ``apps/accounts/apps.py`` → ``ready()`` so it runs in every
context that invokes the Django check framework:

- ``manage.py check`` — all checks, including this one.
- ``manage.py runserver`` — Django calls ``run_checks()`` before booting.
- ``manage.py migrate``, ``manage.py test``, and other management commands
  that invoke ``check()``.

In production (DEBUG=False) the check is also called **directly** from
``config/wsgi.py`` / ``config/asgi.py`` (outside the ``run_checks()`` path)
to guarantee fail-closed startup: a missing or malformed MFA encryption key
raises ``SystemExit`` before the server accepts its first request.

Design notes
------------
- ``run_checks()`` is NOT called at WSGI/ASGI boot — it returns a list of
  issues but never raises, and the previous code silently discarded the
  return value.  Instead, only this specific check is invoked, its return
  value is inspected for ``Error`` instances, and a blocking ``SystemExit``
  is raised on failure.
- The direct call is guarded by ``not settings.DEBUG`` so development
  ``runserver`` does not duplicate the full check suite.
"""

from django.core.checks import Error, register
from django.core.checks import Warning as CheckWarning
from django.core.exceptions import ImproperlyConfigured

from .mfa_crypto import get_mfa_fernet


@register()
def check_mfa_encryption_key(app_configs, **kwargs):
    """Validate ``MFA_ENCRYPTION_KEY`` and ``MFA_ENCRYPTION_PREVIOUS_KEYS``.

    In production (``DEBUG=False``) a missing or malformed key is a blocking
    ``Error`` that prevents startup.  In development and test
    (``DEBUG=True``) it is a non-blocking ``Warning`` so local servers still
    start.  Test settings supply a deterministic valid key, so the check is
    silent under the test runner.

    No key material is ever echoed in the message &mdash; only the setting
    *name* (``label``) is included for operator reference.
    """
    from django.conf import settings

    errors = []

    try:
        get_mfa_fernet()
    except ImproperlyConfigured as exc:
        msg = str(exc)
        if settings.DEBUG:
            errors.append(CheckWarning(msg, id="accounts.W001"))
        else:
            errors.append(Error(msg, id="accounts.E001"))

    return errors
