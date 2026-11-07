"""Django system checks for demo-mode configuration."""

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def check_demo_mode_safety(app_configs, **kwargs):
    """Reject demo mode outside DEBUG unless production use is explicit."""
    if not getattr(settings, "DEMO_MODE", False):
        return []
    if settings.DEBUG or getattr(settings, "DEMO_MODE_ALLOW_PRODUCTION", False):
        return []
    return [
        Error(
            "DEMO_MODE is enabled while DEBUG is False. Set "
            "DEMO_MODE_ALLOW_PRODUCTION=true only when an anonymous demo is intentional.",
            id="agents.E001",
        )
    ]
