"""Local development settings."""

from .base import *  # noqa: F403

DEBUG = True
if not SECRET_KEY:  # noqa: F405
    SECRET_KEY = "dev-only-insecure-secret-key"

# Vite frontend dev server. Add production origins to the same variable in prod.
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://localhost:8000"]
# Local dev runs over plain HTTP; flip these on in prod.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
# Emails are printed to the console during development.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
