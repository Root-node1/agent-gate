import json
from uuid import uuid4

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.policies.models import Policy

URL = "/v1/spend-requests/"


class ThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        organization = Organization.objects.create(name="default")
        self.agent, key = Agent.create_with_key("shopper", organization)
        Policy.objects.create(agent=self.agent)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")

    def post(self):
        return self.client.post(
            URL,
            {"amount": "1.00", "currency": "USD", "merchant": "acme.com", "source": "trusted"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
            "DEFAULT_AUTHENTICATION_CLASSES": ["apps.agents.authentication.AgentKeyAuthentication"],
            "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
            "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
            "DEFAULT_THROTTLE_RATES": {"agent": "2/min", "anon": "2/min"},
        }
    )
    def test_agent_is_throttled_after_the_rate(self):
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().status_code, 429)

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=1_024)
    def test_oversized_body_is_rejected(self):
        payload = json.dumps(
            {
                "amount": "1.00",
                "currency": "USD",
                "merchant": "acme.com",
                "source": "trusted",
                "purpose": "x" * 4_096,
            }
        )
        response = self.client.post(
            URL,
            payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(response.status_code, 400)
