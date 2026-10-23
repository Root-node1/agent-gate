"""Test settings: SQLite unless TEST_DATABASE_URL points at a PostgreSQL server."""

import os

from .base import *  # noqa: F403
from .base import postgres_config

SECRET_KEY = "test-only-insecure-secret-key"
DEBUG = False

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
