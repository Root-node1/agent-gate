"""Django system checks for MFA configuration (AUTH-05B.2D, AUTH-05B.6).

Registered via ``apps/accounts/apps.py`` → ``ready()`` so it runs in every
context that invokes the Django check framework:

- ``manage.py check`` — all checks, including this one.
- ``manage.py runserver`` — Django calls ``run_checks()`` before booting.
- ``manage.py migrate``, ``manage.py test``, and other management commands
  that invoke ``check()``.

In production (``DEBUG=False``) the check is also called **directly** from
``config/wsgi.py`` / ``config/asgi.py`` (outside the ``run_checks()`` path)
to guarantee fail-closed startup: an insecure MFA configuration raises
``SystemExit`` before the server accepts its first request.

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


@register()
def check_redis_cache_connection(app_configs, **kwargs):
    """Validate Redis cache connection and basic operations (AUTH-05B.4B.2).

    Production (``DEBUG=False``) requires Redis to be reachable and functional:
    - ``cache.add()`` must be atomic for an existing live key.
    - All cache operations (write/read/delete) must succeed.
    - No credentials appear in errors or logs.
    - No silent fallback to another cache backend.

    Development and test (``DEBUG=True``) allow Redis to be missing for local
    development and testing.

    Uses a unique, short-lived test key that does not persist.
    """
    from django.conf import settings
    from django.core.cache import caches

    errors = []

    # Development and test environments (DEBUG=True) skip Redis validation to
    # allow local development and testing without a live Redis server.
    if settings.DEBUG:
        return errors

    cache = caches["default"]

    # Generate a unique key for testing.  16AD6C8D-TEST-PURPOSE-ONLY, 4
    # characters of entropy + "-test" suffix to keep key size small.  Using a
    # UUID would produce a larger key that increases load on Redis and has
    # higher risk of collision in constrained deployments.
    import hashlib
    import uuid

    test_key = f"{hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:16]}-test"

    try:
        # 1. Test basic connectivity and reachability.
        # Redis must be reachable.  If this fails, the connection parameters
        # are wrong or the Redis server is unavailable.
        cache.add(test_key, "test-value", timeout=5)
    except Exception as exc:
        # No credentials appear in error messages.
        msg = (
            "Redis cache connection failed: Redis server is unreachable "
            f"or misconfiguration: {type(exc).__name__}. "
            "Set up Redis and ensure REDIS_URL is correct."
        )
        errors.append(Error(msg, id="accounts.E002"))
        return errors

    try:
        # 2. Test cache write/read operation.
        # Cache write/read/delete must succeed.  If this fails, the cache
        # backend is broken even if Redis is reachable.
        cache.set(test_key, "updated-value", timeout=5)
        val = cache.get(test_key)
        if val != "updated-value":
            raise ValueError("Cache read returned incorrect value")
        cache.delete(test_key)
    except Exception as exc:
        msg = (
            "Redis cache operations failed: write/read/delete errors. "
            f"Redis configuration or connectivity issue: {type(exc).__name__}."
        )
        errors.append(Error(msg, id="accounts.E003"))
        return errors

    try:
        # 3. Test cache.add() atomicity.
        # cache.add() must be atomic for an existing live key.  We pre-seed the
        # key with a value (simulating another process's work).  Then cache.add()
        # should return False (key already exists), NOT raise or silently
        # overwrite.
        cache.set(test_key, "existing-value", timeout=5)
        result = cache.add(test_key, "new-value", timeout=5)
        if not isinstance(result, bool):
            raise TypeError(f"Expected bool from cache.add(), got {type(result)}")
        if result:
            # If cache.add() succeeded when the key already existed, the Redis
            # backend is misconfigured and silently overwriting existing keys.
            # This is a security issue.
            msg = (
                "Redis cache.add() is not atomic: key was overwritten "
                "when it already existed.  This is a security misconfiguration."
            )
            errors.append(Error(msg, id="accounts.E004"))
            return errors
        # Clean up
        cache.delete(test_key)
    except Exception as exc:
        # Any exception during the atomicity test indicates a broken cache
        # backend, not just misconfiguration.
        msg = (
            f"Redis cache atomicity test failed: {type(exc).__name__}. "
            "Cache backend is misconfigured."
        )
        errors.append(Error(msg, id="accounts.E005"))
        return errors

    return errors


@register()
def check_mfa_bypass_code(app_configs, **kwargs):
    """Reject ``MFA_TOTP_INSECURE_BYPASS_CODE`` in production (AUTH-05B.6).

    The bypass code is a development/test convenience that allows any TOTP
    code to validate successfully.  Enabling it in production defeats MFA
    entirely, so:

    - ``None`` and ``""`` are treated as *disabled* (no issue).
    - Any other value &mdash; including falsey non-empty values such as
      ``0`` or ``False`` &mdash; is treated as *configured* and triggers:
      - Production (``DEBUG=False``): a blocking ``Error``.
      - Development / test (``DEBUG=True``): a non-blocking ``Warning``.

    No bypass-code value is ever echoed &mdash; only the setting *name*
    (``label``) is included for operator reference.
    """
    from django.conf import settings

    errors = []

    bypass_code = getattr(settings, "MFA_TOTP_INSECURE_BYPASS_CODE", None)
    if bypass_code is not None and bypass_code != "":
        msg = (
            "MFA_TOTP_INSECURE_BYPASS_CODE is configured but must not be "
            "set in production.  Remove it from the environment immediately."
        )
        if settings.DEBUG:
            errors.append(CheckWarning(msg, id="accounts.W002"))
        else:
            errors.append(Error(msg, id="accounts.E006"))

    return errors