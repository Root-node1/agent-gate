import sys
from importlib import import_module
from unittest.mock import patch

from django.core.checks import Error
from django.test import SimpleTestCase, override_settings

from apps.agents.checks import check_demo_mode_safety


class DemoModeSystemCheckTests(SimpleTestCase):
    @override_settings(DEBUG=False, DEMO_MODE=True, DEMO_MODE_ALLOW_PRODUCTION=False)
    def test_production_demo_requires_explicit_override(self):
        errors = check_demo_mode_safety(None)
        self.assertEqual([error.id for error in errors], ["agents.E001"])
        self.assertIsInstance(errors[0], Error)

    @override_settings(DEBUG=False, DEMO_MODE=True, DEMO_MODE_ALLOW_PRODUCTION=True)
    def test_production_demo_is_allowed_with_explicit_override(self):
        self.assertEqual(check_demo_mode_safety(None), [])

    @override_settings(DEBUG=True, DEMO_MODE=True, DEMO_MODE_ALLOW_PRODUCTION=False)
    def test_debug_demo_is_allowed_without_override(self):
        self.assertEqual(check_demo_mode_safety(None), [])

    @override_settings(DEBUG=False, DEMO_MODE=False, DEMO_MODE_ALLOW_PRODUCTION=False)
    def test_disabled_demo_is_allowed(self):
        self.assertEqual(check_demo_mode_safety(None), [])


class DemoModeStartupTests(SimpleTestCase):
    @override_settings(DEBUG=False, DEMO_MODE=True, DEMO_MODE_ALLOW_PRODUCTION=False)
    def test_wsgi_refuses_to_start_without_production_override(self):
        sys.modules.pop("config.wsgi", None)
        try:
            with patch("django.core.wsgi.get_wsgi_application"), patch(
                "apps.accounts.checks.check_redis_cache_connection", return_value=[]
            ):
                with self.assertRaises(SystemExit) as raised:
                    import_module("config.wsgi")
            self.assertIn("agents.E001", str(raised.exception))
        finally:
            sys.modules.pop("config.wsgi", None)
