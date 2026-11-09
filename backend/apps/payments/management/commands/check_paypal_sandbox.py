"""Read-only readiness check for isolated PayPal Sandbox configuration."""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.payments.paypal.config import PayPalConfigError, get_paypal_config


class Command(BaseCommand):
    help = "Validate PayPal Sandbox configuration without printing secrets."

    def handle(self, *args, **options):
        errors = []
        warnings = []

        # PayPal environment must be sandbox.
        env = getattr(settings, "PAYPAL_ENV", "sandbox")
        if env != "sandbox":
            errors.append(f"PAYPAL_ENV must be 'sandbox', got {env!r}.")

        # Parse feature flags and credentials through the shared contract.
        try:
            config = get_paypal_config(settings)
        except PayPalConfigError as exc:
            errors.append(str(exc))
            config = None

        if config is not None:
            if not (config.checkout_enabled or config.payouts_enabled):
                warnings.append(
                    "Both PAYPAL_CHECKOUT_ENABLED and PAYPAL_PAYOUTS_ENABLED are false."
                )
            if config.checkout_enabled and not config.webhook_id:
                warnings.append(
                    "PAYPAL_WEBHOOK_ID is missing while checkout is enabled."
                )
            if config.payouts_enabled and not config.webhook_id:
                warnings.append(
                    "PAYPAL_WEBHOOK_ID is missing while payouts are enabled."
                )

        # Host / origin configuration for local Sandbox callbacks.
        allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])
        if not allowed_hosts:
            errors.append("ALLOWED_HOSTS is empty.")
        csrf_origins = getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
        if not csrf_origins:
            warnings.append("CSRF_TRUSTED_ORIGINS is empty.")

        # MFA prerequisite.
        mfa_key = getattr(settings, "MFA_ENCRYPTION_KEY", "")
        if not mfa_key:
            errors.append("MFA_ENCRYPTION_KEY is not configured.")

        # Database isolation sanity check (name only, no connection).
        try:
            db_name = settings.DATABASES["default"]["NAME"]
        except Exception:
            db_name = None
        if db_name:
            lowered = str(db_name).lower()
            if lowered.startswith("test_"):
                errors.append(
                    "Runtime database name starts with 'test_'; refusing test DB."
                )
            if "prod" in lowered:
                warnings.append(
                    "Runtime database name contains 'prod'; verify isolation."
                )

        if errors:
            for item in errors:
                self.stderr.write(self.style.ERROR(f"ERROR: {item}"))
            for item in warnings:
                self.stderr.write(self.style.WARNING(f"WARNING: {item}"))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("PayPal Sandbox readiness: OK"))
        for item in warnings:
            self.stdout.write(self.style.WARNING(f"WARNING: {item}"))
        if db_name:
            self.stdout.write(f"Database: {db_name}")
        self.stdout.write("No secret values were printed.")
