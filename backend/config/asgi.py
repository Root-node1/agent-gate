"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.conf import settings
from django.core.asgi import get_asgi_application
from django.core.checks import Error

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod')

application = get_asgi_application()

# AUTH-05B.2D: fail fast in production if the MFA encryption key is missing
# or invalid.  See config/wsgi.py for the full rationale — the same approach
# avoids duplicate check execution (runserver's built-in check handles dev)
# and fixes the silent-return bug where run_checks() errors were discarded.
if not settings.DEBUG:
    from apps.accounts.checks import check_mfa_encryption_key

    startup_errors = [e for e in check_mfa_encryption_key(None) if isinstance(e, Error)]
    if startup_errors:
        raise SystemExit(f"Startup system checks failed: {startup_errors}")
