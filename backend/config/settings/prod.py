"""Production settings for the Contabo host and Neon PostgreSQL."""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env_int

DEBUG = False

if not SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")

TRUSTED_PROXY_COUNT = env_int("TRUSTED_PROXY_COUNT", 1)
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": TRUSTED_PROXY_COUNT}  # noqa: F405

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^healthz$", r"^readyz$"]
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

prod_email_host = os.environ.get("EMAIL_HOST", "").strip()
if prod_email_host:
    EMAIL_HOST = prod_email_host
    EMAIL_PORT = env_int("EMAIL_PORT", 587)
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() == "true"
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    if "DEFAULT_FROM_EMAIL" in os.environ:
        DEFAULT_FROM_EMAIL = os.environ["DEFAULT_FROM_EMAIL"]
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "agentgate_cache",
    }
}
