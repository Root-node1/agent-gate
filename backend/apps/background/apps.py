"""Django AppConfig for the background-job foundation.

This app registers Procrastinate's Django integration and owns the smoke-test
task. Approval-expiration and payment-execution tasks will be added here in
later iterations.
"""

from django.apps import AppConfig


class BackgroundConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.background"
