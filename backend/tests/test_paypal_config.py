"""INT-13D: PayPal sandbox configuration validation tests.

All tests are offline — no PayPal API calls are made.  Uses deterministic
test-only credential values that must never appear in production configuration.
"""

from django.test import SimpleTestCase, override_settings

from apps.payments.checks import check_paypal_config
from apps.payments.paypal import config as paypal_config
from apps.payments.paypal.config import (
    SANDBOX_API_BASE_URL,
    SANDBOX_WEB_BASE_URL,
    SUPPORTED_ENVIRONMENTS,
    PayPalConfigError,
    get_paypal_config,
)

# Deterministic test-only values — never use in production.
TEST_CLIENT_ID = "test-client-id-12345"
TEST_CLIENT_SECRET = "test-client-secret-67890"
TEST_WEBHOOK_ID = "test-webhook-id-abcde"


@override_settings(
    PAYPAL_ENV="sandbox",
    PAYPAL_CLIENT_ID="",
    PAYPAL_CLIENT_SECRET="",
    PAYPAL_WEBHOOK_ID="",
    PAYPAL_CHECKOUT_ENABLED="false",
    PAYPAL_PAYOUTS_ENABLED="false",
)
class PayPalConfigDefaultTests(SimpleTestCase):
    """1. Default-disabled behavior — both features off, no credentials required."""

    def test_both_features_disabled_by_default(self):
        from django.conf import settings

        cfg = get_paypal_config(settings)
        self.assertFalse(cfg.checkout_enabled)
        self.assertFalse(cfg.payouts_enabled)

    def test_default_env_is_sandbox(self):
        from django.conf import settings

        cfg = get_paypal_config(settings)
        self.assertEqual(cfg.env, "sandbox")


@override_settings(
    PAYPAL_ENV="sandbox",
    PAYPAL_CLIENT_ID=TEST_CLIENT_ID,
    PAYPAL_CLIENT_SECRET=TEST_CLIENT_SECRET,
    PAYPAL_WEBHOOK_ID=TEST_WEBHOOK_ID,
    PAYPAL_CHECKOUT_ENABLED="true",
    PAYPAL_PAYOUTS_ENABLED="true",
)
class PayPalConfigValidSandboxTests(SimpleTestCase):
    """2. Valid sandbox configuration — credentials present, both features on."""

    def test_valid_config_returns_parsed_values(self):
        from django.conf import settings

        cfg = get_paypal_config(settings)
        self.assertEqual(cfg.env, "sandbox")
        self.assertTrue(cfg.checkout_enabled)
        self.assertTrue(cfg.payouts_enabled)
        self.assertEqual(cfg.client_id, TEST_CLIENT_ID)
        self.assertEqual(cfg.client_secret, TEST_CLIENT_SECRET)
        self.assertEqual(cfg.webhook_id, TEST_WEBHOOK_ID)

    def test_config_is_frozen(self):
        from django.conf import settings

        cfg = get_paypal_config(settings)
        with self.assertRaises(Exception):
            cfg.checkout_enabled = False  # frozen dataclass

    def test_system_check_passes_for_valid_config(self):
        self.assertEqual(check_paypal_config(None), [])


@override_settings(PAYPAL_ENV="production")
class PayPalConfigProductionRejectionTests(SimpleTestCase):
    """3. Production environment rejection."""

    def test_production_env_rejected_by_get_paypal_config(self):
        from django.conf import settings

        with self.assertRaises(PayPalConfigError) as ctx:
            get_paypal_config(settings)
        self.assertIn("sandbox", str(ctx.exception))

    def test_production_env_reported_as_error(self):
        errors = check_paypal_config(None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, "payments.E001")
        self.assertIn("production", errors[0].msg)

    def test_production_env_is_in_supported_environments_check(self):
        self.assertNotIn("production", SUPPORTED_ENVIRONMENTS)


@override_settings(
    PAYPAL_ENV="sandbox",
    PAYPAL_CLIENT_ID="",
    PAYPAL_CLIENT_SECRET="",
    PAYPAL_WEBHOOK_ID="",
    PAYPAL_CHECKOUT_ENABLED="true",
    PAYPAL_PAYOUTS_ENABLED="false",
)
class PayPalConfigMissingCheckoutCredentialsTests(SimpleTestCase):
    """4. Missing Checkout credentials."""

    def test_checkout_enabled_without_credentials_raises(self):
        from django.conf import settings

        with self.assertRaises(PayPalConfigError) as ctx:
            get_paypal_config(settings)
        self.assertIn("PAYPAL_CHECKOUT_ENABLED", str(ctx.exception))

    def test_checkout_enabled_without_credentials_reported_as_error(self):
        errors = check_paypal_config(None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, "payments.E001")

    def test_error_message_does_not_leak_credentials(self):
        errors = check_paypal_config(None)
        msg = errors[0].msg
        self.assertNotIn(TEST_CLIENT_ID, msg)
        self.assertNotIn(TEST_CLIENT_SECRET, msg)


@override_settings(
    PAYPAL_ENV="sandbox",
    PAYPAL_CLIENT_ID="",
    PAYPAL_CLIENT_SECRET="",
    PAYPAL_WEBHOOK_ID="",
    PAYPAL_CHECKOUT_ENABLED="false",
    PAYPAL_PAYOUTS_ENABLED="true",
)
class PayPalConfigMissingPayoutsCredentialsTests(SimpleTestCase):
    """5. Missing Payouts credentials."""

    def test_payouts_enabled_without_credentials_raises(self):
        from django.conf import settings

        with self.assertRaises(PayPalConfigError) as ctx:
            get_paypal_config(settings)
        self.assertIn("PAYPAL_PAYOUTS_ENABLED", str(ctx.exception))

    def test_payouts_enabled_without_credentials_reported_as_error(self):
        errors = check_paypal_config(None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, "payments.E001")

    def test_error_message_does_not_leak_credentials(self):
        errors = check_paypal_config(None)
        msg = errors[0].msg
        self.assertNotIn(TEST_CLIENT_ID, msg)
        self.assertNotIn(TEST_CLIENT_SECRET, msg)


@override_settings(
    PAYPAL_ENV="sandbox",
    PAYPAL_CLIENT_ID=TEST_CLIENT_ID,
    PAYPAL_CLIENT_SECRET=TEST_CLIENT_SECRET,
    PAYPAL_WEBHOOK_ID=TEST_WEBHOOK_ID,
    PAYPAL_CHECKOUT_ENABLED="maybe",
    PAYPAL_PAYOUTS_ENABLED="false",
)
class PayPalConfigInvalidBooleanTests(SimpleTestCase):
    """6. Invalid feature-flag values."""

    def test_invalid_checkout_flag_value_raises(self):
        from django.conf import settings

        with self.assertRaises(PayPalConfigError) as ctx:
            get_paypal_config(settings)
        self.assertIn("PAYPAL_CHECKOUT_ENABLED", str(ctx.exception))

    def test_invalid_checkout_flag_reported_as_error(self):
        errors = check_paypal_config(None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, "payments.E001")


@override_settings(
    PAYPAL_ENV="sandbox",
    PAYPAL_CLIENT_ID=TEST_CLIENT_ID,
    PAYPAL_CLIENT_SECRET=TEST_CLIENT_SECRET,
    PAYPAL_WEBHOOK_ID=TEST_WEBHOOK_ID,
    PAYPAL_CHECKOUT_ENABLED="false",
    PAYPAL_PAYOUTS_ENABLED="perhaps",
)
class PayPalConfigInvalidPayoutsBooleanTests(SimpleTestCase):
    """6b. Invalid payouts feature-flag value."""

    def test_invalid_payouts_flag_value_raises(self):
        from django.conf import settings

        with self.assertRaises(PayPalConfigError) as ctx:
            get_paypal_config(settings)
        self.assertIn("PAYPAL_PAYOUTS_ENABLED", str(ctx.exception))


class PayPalSandboxURLTests(SimpleTestCase):
    """7. Sandbox URL invariant."""

    def test_api_base_url_is_sandbox(self):
        self.assertEqual(SANDBOX_API_BASE_URL, "https://api.sandbox.paypal.com")

    def test_web_base_url_is_sandbox(self):
        self.assertEqual(SANDBOX_WEB_BASE_URL, "https://www.sandbox.paypal.com")

    def test_no_production_url_constant(self):
        # The module must not expose any production endpoint constant.
        self.assertFalse(hasattr(paypal_config, "_PRODUCTION_API_BASE_URL"))
        self.assertFalse(hasattr(paypal_config, "PRODUCTION_API_BASE_URL"))


@override_settings(
    PAYPAL_ENV="sandbox",
    PAYPAL_CLIENT_ID="",
    PAYPAL_CLIENT_SECRET="",
    PAYPAL_WEBHOOK_ID="",
    PAYPAL_CHECKOUT_ENABLED="false",
    PAYPAL_PAYOUTS_ENABLED="false",
)
class PayPalConfigDisabledFeaturesTests(SimpleTestCase):
    """8. No credentials required when both features are disabled."""

    def test_disabled_features_pass_without_credentials(self):
        from django.conf import settings

        cfg = get_paypal_config(settings)
        self.assertFalse(cfg.checkout_enabled)
        self.assertFalse(cfg.payouts_enabled)
        self.assertEqual(cfg.env, "sandbox")

    def test_system_check_passes_when_disabled(self):
        self.assertEqual(check_paypal_config(None), [])
