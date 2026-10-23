from datetime import timedelta

from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication, exceptions

from .keys import PREFIX_LENGTH, hash_matches
from .models import ApiKey


class AgentPrincipal:
    """A request principal backed by an agent, so DRF permission checks work unchanged."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, agent):
        self.agent = agent


class AgentKeyAuthentication(authentication.BaseAuthentication):
    """Authorization: Bearer <agent key>. Lookup uses the prefix, then a constant-time hash check."""

    keyword = "Bearer"
    last_used_interval = timedelta(minutes=1)

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode()
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Use 'Authorization: Bearer <agent key>'.")
        raw_key = parts[1]
        try:
            api_key = ApiKey.objects.select_related("agent").get(
                prefix=raw_key[:PREFIX_LENGTH],
                revoked_at__isnull=True,
                agent__status="active",
            )
        except ApiKey.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid or inactive agent key.") from None
        if not hash_matches(raw_key, api_key.key_hash):
            raise exceptions.AuthenticationFailed("Invalid or inactive agent key.")
        self._mark_used(api_key)
        return (AgentPrincipal(api_key.agent), None)

    def _mark_used(self, api_key: ApiKey) -> None:
        now = timezone.now()
        if api_key.last_used_at is None or now - api_key.last_used_at > self.last_used_interval:
            ApiKey.objects.filter(pk=api_key.pk).update(last_used_at=now)

    def authenticate_header(self, request):
        return self.keyword


class AgentKeyScheme(OpenApiAuthenticationExtension):
    target_class = "apps.agents.authentication.AgentKeyAuthentication"
    name = "AgentKey"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "description": "Agent API key, for example agk_...",
        }
