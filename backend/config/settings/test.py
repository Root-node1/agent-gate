"""Test settings: SQLite unless TEST_DATABASE_URL points at a PostgreSQL server."""

import os

from .base import *  # noqa: F403
from .base import postgres_config

SECRET_KEY = "test-only-insecure-secret-key"
DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
if TEST_DATABASE_URL:
    DATABASES = {"default": postgres_config(TEST_DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }

# Capture outbound verification emails in memory so tests can inspect them.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Relax confirm_email rate limit so signup + immediate login doesn't hit it.
# Relax signup rate limit for tests.
ACCOUNT_RATE_LIMITS = {
    "confirm_email": "5/10s/key",
    "signup": "100/m/ip",
}
