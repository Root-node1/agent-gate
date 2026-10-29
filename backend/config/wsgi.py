"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.conf import settings
from django.core.checks import Error
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod')

application = get_wsgi_application()

# AUTH-05B.2D: fail fast in production if the MFA encryption key is missing
# or invalid.  We call the app-specific check directly rather than run_checks()
# to avoid two problems:
#
# 1. run_checks() returns a list of issues but never raises — the return value
#    was discarded, so a missing MFA key in production would NOT block startup.
# 2. manage.py runserver already calls run_checks() via its check() step, then
#    imports this module (via get_internal_wsgi_application) which would call
#    it again — a duplicate full-suite run including database-dependent checks.
#
# By calling only check_mfa_encryption_key and guarding on DEBUG=False, we get:
# - Production fail-closed: a missing/invalid key raises SystemExit.
# - No duplicate in development: runserver's built-in check handles DEBUG=True.
# - No database-dependent checks at container startup.
# AUTH-05B.4B.2: fail fast in production if Redis cache is missing or broken
# We call the app-specific check directly rather than run_checks()
# to avoid problems similar to the MFA key check:
#
# 1. run_checks() returns a list of issues but never raises.
# 2. This module would be imported twice (runserver + startup).
#
# By calling only check_redis_cache_connection and guarding on DEBUG=False, we get:
# - Production fail-closed: broken Redis raises SystemExit.
# - No duplicate in development: runserver's built-in check handles DEBUG=True.
# - No network-dependent checks at container startup.
if not settings.DEBUG:
    from apps.accounts.checks import (
        check_mfa_bypass_code,
        check_mfa_encryption_key,
        check_redis_cache_connection,
    )

    startup_errors = []
    for check_func in [check_mfa_encryption_key, check_mfa_bypass_code, check_redis_cache_connection]:
        errors = [e for e in check_func(None) if isinstance(e, Error)]
        startup_errors.extend(errors)
    if startup_errors:
        raise SystemExit(f"Startup system checks failed: {startup_errors}")
