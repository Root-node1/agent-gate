"""IDOR/BOLA authorization tests (VULN-006).

Verifies that authenticated users cannot access resources
belonging to organizations they are not a member of.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from tests.base import force_mfa


class IdorBolaTestBase(APITestCase):
    """Base class with two organizations and two users."""

    def setUp(self):
        # Organization A with admin user
        self.org_a = Organization.objects.create(name="org-a")
        self.user_a = User.objects.create_user("user-a")
        OrgMembership.objects.create(
            user=self.user_a, organization=self.org_a, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.user_a)

        # Organization B with admin user (foreign org)
        self.org_b = Organization.objects.create(name="org-b")
        self.user_b = User.objects.create_user("user-b")
        OrgMembership.objects.create(
            user=self.user_b, organization=self.org_b, role=OrgMembership.Role.ADMIN
        )
        force_mfa(self.user_b)

        # Agents in both orgs
        self.agent_a = Agent.create_with_key("agent-a", self.org_a)[0]
        self.agent_b = Agent.create_with_key("agent-b", self.org_b)[0]

        self.client.force_authenticate(user=self.user_a)


class AgentIdorBolaTests(IdorBolaTestBase):
    """Agent endpoints must not expose foreign-organization agents."""

    def test_list_excludes_foreign_org_agents(self):
        response = self.client.get("/v1/agents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in response.json()["results"]]
        self.assertIn(str(self.agent_a.id), ids)
        self.assertNotIn(str(self.agent_b.id), ids)

    def test_retrieve_foreign_agent_is_rejected(self):
        response = self.client.get(f"/v1/agents/{self.agent_b.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_foreign_agent_is_rejected(self):
        response = self.client.patch(
            f"/v1/agents/{self.agent_b.id}/", {"name": "hacked"}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_foreign_agent_is_rejected(self):
        response = self.client.delete(f"/v1/agents/{self.agent_b.id}/")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_foreign_user_cannot_access_own_org_agent(self):
        """User B cannot access Organization A's agent."""
        self.client.force_authenticate(user=self.user_b)
        response = self.client.get(f"/v1/agents/{self.agent_a.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
