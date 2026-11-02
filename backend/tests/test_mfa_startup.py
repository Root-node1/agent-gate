"""AUTH-05B.6A: Production startup enforcement for MFA bypass code.

Tests that the actual WSGI and ASGI startup code (config/wsgi.py and
config/asgi.py) refuses to initialize when DEBUG=False and a bypass code
is configured.  These tests exercise the real startup enforcement loop,
not just the check function.
"""

import sys
from importlib import import_module
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

TEST_KEY_PRIMARY = "QG92N9nkDu9c2Nh3TjwTBLTpPFozP20BQl2dwhAmsNM="


@override_settings(
    DEBUG=False,
    MFA_ENCRYPTION_KEY=TEST_KEY_PRIMARY,
    MFA_ENCRYPTION_PREVIOUS_KEYS=[],
    MFA_TOTP_INSECURE_BYPASS_CODE="123456",
)
class WSGIStrictStartupTests(SimpleTestCase):
    """AUTH-05B.6A: WSGI startup in production refuses to boot with bypass code."""

    def test_wsgi_raises_systemexit_on_bypass_in_production(self):
        """config/wsgi.py raises SystemExit when bypass code is configured in production."""
        sys.modules.pop("config.wsgi", None)
        try:
            with patch("django.core.wsgi.get_wsgi_application"):
                with patch(
                    "apps.accounts.checks.check_redis_cache_connection"
                ) as mock_redis:
                    mock_redis.return_value = []
                    with self.assertRaises(SystemExit) as ctx:
                        import_module("config.wsgi")
                    self.assertIn("Startup system checks failed", str(ctx.exception))
                    self.assertNotIn("123456", str(ctx.exception))
        finally:
            sys.modules.pop("config.wsgi", None)

    @override_settings(MFA_TOTP_INSECURE_BYPASS_CODE=None)
    def test_wsgi_starts_when_bypass_absent_in_production(self):
        """config/wsgi.py boots normally when no bypass code is configured."""
        sys.modules.pop("config.wsgi", None)
        try:
            with patch("django.core.wsgi.get_wsgi_application"):
                with patch(
                    "apps.accounts.checks.check_redis_cache_connection"
                ) as mock_redis:
                    mock_redis.return_value = []
                    import_module("config.wsgi")
        finally:
            sys.modules.pop("config.wsgi", None)


@override_settings(
    DEBUG=False,
    MFA_ENCRYPTION_KEY=TEST_KEY_PRIMARY,
    MFA_ENCRYPTION_PREVIOUS_KEYS=[],
    MFA_TOTP_INSECURE_BYPASS_CODE="123456",
)
class ASGIStrictStartupTests(SimpleTestCase):
    """AUTH-05B.6A: ASGI startup in production refuses to boot with bypass code."""

    def test_asgi_raises_systemexit_on_bypass_in_production(self):
        """config/asgi.py raises SystemExit when bypass code is configured in production."""
        sys.modules.pop("config.asgi", None)
        try:
            with patch("django.core.asgi.get_asgi_application"):
                with patch(
                    "apps.accounts.checks.check_redis_cache_connection"
                ) as mock_redis:
                    mock_redis.return_value = []
                    with self.assertRaises(SystemExit) as ctx:
                        import_module("config.asgi")
                    self.assertIn("Startup system checks failed", str(ctx.exception))
                    self.assertNotIn("123456", str(ctx.exception))
        finally:
            sys.modules.pop("config.asgi", None)

    @override_settings(MFA_TOTP_INSECURE_BYPASS_CODE=None)
    def test_asgi_starts_when_bypass_absent_in_production(self):
        """config/asgi.py boots normally when no bypass code is configured."""
        sys.modules.pop("config.asgi", None)
        try:
            with patch("django.core.asgi.get_asgi_application"):
                with patch(
                    "apps.accounts.checks.check_redis_cache_connection"
                ) as mock_redis:
                    mock_redis.return_value = []
                    import_module("config.asgi")
        finally:
            sys.modules.pop("config.asgi", None)
