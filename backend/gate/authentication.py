from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication, exceptions

from .models import Agent, hash_key


class AgentPrincipal:
    """Stands in for request.user so DRF's permission checks work for agents."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, agent):
        self.agent = agent


class AgentKeyAuthentication(authentication.BaseAuthentication):
    """Authorization: Bearer <agent key>. Only a hash of the key is stored and compared."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode()
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Use 'Authorization: Bearer <agent key>'.")
        try:
            agent = Agent.objects.get(api_key_hash=hash_key(parts[1]), status=Agent.Status.ACTIVE)
        except Agent.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid or inactive agent key.") from None
        return (AgentPrincipal(agent), None)

    def authenticate_header(self, request):
        return self.keyword


class AgentKeyScheme(OpenApiAuthenticationExtension):
    target_class = "gate.authentication.AgentKeyAuthentication"
    name = "AgentKey"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "description": "Agent API key, for example agk_...",
        }
