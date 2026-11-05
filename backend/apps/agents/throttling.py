"""Per-agent request throttling for retryable writes."""

from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class AgentKeyRateThrottle(SimpleRateThrottle):
    """Limit requests by API key owner, not by IP address."""

    scope = "agent"

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)

    def get_cache_key(self, request, view):
        agent = getattr(request.user, "agent", None)
        if agent is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(agent.pk)}


class DemoModeRateThrottle(SimpleRateThrottle):
    """Limit anonymous demo traffic without charging real dashboard sessions."""

    scope = "demo"

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)

    def get_cache_key(self, request, view):
        if not getattr(request, "demo_mode", False):
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
