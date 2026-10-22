"""Local development settings."""

from .base import *  # noqa: F403

DEBUG = True
if not SECRET_KEY:  # noqa: F405
    SECRET_KEY = "dev-only-insecure-secret-key"
