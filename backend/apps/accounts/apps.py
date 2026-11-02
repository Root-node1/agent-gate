from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        from . import (  # noqa: F401
            checks,  # registers system checks
            signals,  # registers MFA security-event handlers
        )
