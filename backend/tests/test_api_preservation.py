"""
API Contract and Data Visibility Preservation Tests (Property 6)

These are PRESERVATION tests — they assert already-working behavior that must
not regress.  Every test in this file MUST PASS on the current unfixed code.

**Validates: Requirements 3.1, 3.2, 3.3**
"""

from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from tests.base import force_mfa

# ---------------------------------------------------------------------------
# 1. Path alignment — /v1/agents/ resolves and returns 200 for authenticated users
# ---------------------------------------------------------------------------

class AgentsPathAlignmentTests(APITestCase):
    """Preservation: the /v1/agents/ path is correctly routed (Requirement 3.1)."""

    def setUp(self):
        self.org = Organization.objects.create(name="path-alignment-org")
        self.user = User.objects.create_user("path-user")
        OrgMembership.objects.create(
            user=self.user, organization=self.org, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.user)
        self.client.force_authenticate(user=self.user)

    def test_agents_list_path_resolves_and_returns_200(self):
        """GET /v1/agents/ returns HTTP 200 for an authenticated org member."""
        response = self.client.get("/v1/agents/")
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200 from GET /v1/agents/, got {response.status_code}: {response.content}",
        )

    def test_agents_list_response_is_json(self):
        """GET /v1/agents/ returns valid JSON (content-type check)."""
        response = self.client.get("/v1/agents/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("results", body, "Paginated response should contain 'results' key")
        self.assertIn("count", body, "Paginated response should contain 'count' key")


# ---------------------------------------------------------------------------
# 2. Org data visibility — user A only sees their own org's agents
# ---------------------------------------------------------------------------

class OrgDataVisibilityTests(APITestCase):
    """Preservation: org-scoping isolates agents per org (Requirement 3.2)."""

    def setUp(self):
        # Org A with user A (admin) and 2 agents
        self.org_a = Organization.objects.create(name="org-a-visibility")
        self.user_a = User.objects.create_user("user-a-visibility")
        OrgMembership.objects.create(
            user=self.user_a, organization=self.org_a, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.user_a)
        Agent.create_with_key("agent-a1", self.org_a)
        Agent.create_with_key("agent-a2", self.org_a)

        # Org B with user B (admin) and 1 agent
        self.org_b = Organization.objects.create(name="org-b-visibility")
        self.user_b = User.objects.create_user("user-b-visibility")
        OrgMembership.objects.create(
            user=self.user_b, organization=self.org_b, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.user_b)
        self.agent_b, _ = Agent.create_with_key("agent-b1", self.org_b)

    def test_user_a_sees_only_own_org_agents(self):
        """User A sees exactly 2 agents (their own), not 3 (org A + org B)."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/v1/agents/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["count"],
            2,
            f"User A should see exactly 2 agents (their org), got {body['count']}",
        )

    def test_user_b_sees_only_own_org_agents(self):
        """User B sees exactly 1 agent (their own), not 3."""
        self.client.force_authenticate(user=self.user_b)
        response = self.client.get("/v1/agents/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["count"],
            1,
            f"User B should see exactly 1 agent (their org), got {body['count']}",
        )

    def test_user_a_result_ids_do_not_include_org_b_agent(self):
        """The agent IDs returned to user A do not include org B's agent."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/v1/agents/")
        self.assertEqual(response.status_code, 200)
        returned_ids = {r["id"] for r in response.json()["results"]}
        self.assertNotIn(
            str(self.agent_b.id),
            returned_ids,
            "Org B's agent must not appear in org A user's list",
        )


# ---------------------------------------------------------------------------
# 3. Org scoping on individual reads — user A cannot read user B's agent
# ---------------------------------------------------------------------------

class OrgScopingIndividualReadTests(APITestCase):
    """Preservation: cross-org agent reads return 404 (Requirement 3.2)."""

    def setUp(self):
        self.org_a = Organization.objects.create(name="org-a-read")
        self.user_a = User.objects.create_user("user-a-read")
        OrgMembership.objects.create(
            user=self.user_a, organization=self.org_a, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.user_a)

        self.org_b = Organization.objects.create(name="org-b-read")
        self.user_b = User.objects.create_user("user-b-read")
        OrgMembership.objects.create(
            user=self.user_b, organization=self.org_b, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.user_b)
        self.agent_b, _ = Agent.create_with_key("cross-org-agent", self.org_b)

    def test_user_a_cannot_read_user_b_agent(self):
        """GET /v1/agents/<B_agent_id>/ by user A returns 404 (not 200 or 403)."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f"/v1/agents/{self.agent_b.id}/")
        self.assertEqual(
            response.status_code,
            404,
            f"User A should get 404 accessing org B's agent, got {response.status_code}",
        )

    def test_user_b_can_read_own_agent(self):
        """GET /v1/agents/<B_agent_id>/ by user B returns 200 (sanity check)."""
        self.client.force_authenticate(user=self.user_b)
        response = self.client.get(f"/v1/agents/{self.agent_b.id}/")
        self.assertEqual(
            response.status_code,
            200,
            f"User B should get 200 accessing their own agent, got {response.status_code}",
        )


# ---------------------------------------------------------------------------
# 4. Auth protection — /v1/agents/ returns 401 for unauthenticated requests
# ---------------------------------------------------------------------------

class AuthProtectionTests(APITestCase):
    """Preservation: unauthenticated access is blocked with 401 (Requirement 3.1)."""

    def test_unauthenticated_agents_list_returns_401(self):
        """GET /v1/agents/ without authentication returns HTTP 401."""
        # Explicitly do NOT authenticate
        response = self.client.get("/v1/agents/")
        self.assertEqual(
            response.status_code,
            401,
            f"Expected 401 for unauthenticated GET /v1/agents/, got {response.status_code}",
        )

    def test_unauthenticated_agents_detail_returns_401(self):
        """GET /v1/agents/<some-uuid>/ without authentication returns HTTP 401."""
        import uuid
        fake_id = uuid.uuid4()
        response = self.client.get(f"/v1/agents/{fake_id}/")
        self.assertEqual(
            response.status_code,
            401,
            f"Expected 401 for unauthenticated agent detail, got {response.status_code}",
        )


# ---------------------------------------------------------------------------
# 5. OpenAPI endpoint exists — GET /api/schema/ returns 200
# ---------------------------------------------------------------------------

class OpenAPISchemaEndpointTests(APITestCase):
    """Preservation: the OpenAPI schema endpoint is available (Requirement 3.3)."""

    def test_schema_endpoint_returns_200(self):
        """GET /api/schema/ returns HTTP 200 (schema endpoint is available)."""
        response = self.client.get("/api/schema/")
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200 from GET /api/schema/, got {response.status_code}",
        )

    def test_schema_endpoint_returns_yaml_or_json(self):
        """GET /api/schema/ returns a non-empty body (actual schema content)."""
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            len(response.content) > 100,
            "Schema endpoint returned suspiciously small content",
        )


# ---------------------------------------------------------------------------
# 6. Error envelope on unauthenticated requests — error.code and error.message present
# ---------------------------------------------------------------------------

class ErrorEnvelopePreservationTests(APITestCase):
    """Preservation: 401 responses use the standard error envelope (Requirement 3.1)."""

    def test_unauthenticated_agents_list_returns_error_envelope(self):
        """Unauthenticated GET /v1/agents/ returns error envelope with code and message."""
        response = self.client.get("/v1/agents/")
        self.assertEqual(response.status_code, 401)

        body = response.json()

        # Must have top-level 'error' key
        self.assertIn(
            "error",
            body,
            f"Response missing 'error' key: {body}",
        )
        error = body["error"]

        # error.code must be present and non-empty
        self.assertIn(
            "code",
            error,
            f"'error' dict missing 'code' key: {error}",
        )
        self.assertTrue(
            error["code"],
            "error.code must be a non-empty string",
        )

        # error.message must be present and non-empty
        self.assertIn(
            "message",
            error,
            f"'error' dict missing 'message' key: {error}",
        )
        self.assertTrue(
            error["message"],
            "error.message must be a non-empty string",
        )

    def test_error_envelope_has_request_id(self):
        """Unauthenticated request returns a response with a request_id."""
        response = self.client.get("/v1/agents/")
        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertIn(
            "request_id",
            body,
            f"Response missing 'request_id' key: {body}",
        )
        self.assertTrue(
            body["request_id"],
            "request_id must be a non-empty string",
        )

    def test_error_envelope_does_not_leak_detail_key(self):
        """Error responses do not expose the raw DRF 'detail' key (envelope contract)."""
        response = self.client.get("/v1/agents/")
        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertNotIn(
            "detail",
            body,
            "Raw DRF 'detail' key must not appear in error response — use the envelope",
        )
