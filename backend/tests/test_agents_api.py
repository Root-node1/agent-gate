from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent, ApiKey
from apps.audit.models import AuditEvent
from apps.policies.models import Policy


class AgentApiTestBase(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, self.raw_key = Agent.create_with_key("billing-agent", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)

        self.admin = User.objects.create_user("admin")
        OrgMembership.objects.create(
            user=self.admin, organization=self.organization, role=OrgMembership.Role.ADMIN
        )

        self.viewer = User.objects.create_user("viewer")
        OrgMembership.objects.create(
            user=self.viewer, organization=self.organization, role=OrgMembership.Role.VIEWER
        )

        self.other_org = Organization.objects.create(name="other-org")
        self.other_admin = User.objects.create_user("other-admin")
        OrgMembership.objects.create(
            user=self.other_admin, organization=self.other_org, role=OrgMembership.Role.ADMIN
        )
        self.other_agent, _ = Agent.create_with_key("foreign-agent", self.other_org)

        self.client.force_authenticate(user=self.admin)


class AgentListTests(AgentApiTestBase):
    def test_list_returns_org_scoped_agents(self):
        response = self.client.get("/v1/agents/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_list_does_not_expose_key_hash(self):
        response = self.client.get("/v1/agents/")
        body = response.json()
        self.assertNotIn("key_hash", str(body))
        for result in body["results"]:
            self.assertIn("current_key_prefix", result)
            self.assertNotIn("key_hash", str(result))
            self.assertNotIn("api_key", str(result))

    def test_list_excludes_foreign_org_agents(self):
        response = self.client.get("/v1/agents/")
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertNotIn(str(self.other_agent.id), [r["id"] for r in body["results"]])

    def test_unauthenticated_list_is_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/v1/agents/").status_code, 401)

    def test_non_member_is_rejected(self):
        outsider = User.objects.create_user("outsider")
        self.client.force_authenticate(user=outsider)
        self.assertEqual(self.client.get("/v1/agents/").status_code, 403)


class AgentCreateTests(AgentApiTestBase):
    def test_create_returns_raw_key_once(self):
        response = self.client.post(
            "/v1/agents/",
            {"name": "new-agent", "organization": str(self.organization.id)},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["api_key"].startswith("agk_"))
        self.assertNotIn("key_hash", str(body))

    def test_create_stores_only_hash(self):
        response = self.client.post(
            "/v1/agents/",
            {"name": "new-agent", "organization": str(self.organization.id)},
        )
        api_key = ApiKey.objects.get(agent__name="new-agent")
        self.assertNotEqual(api_key.key_hash, response.json()["api_key"])
        self.assertTrue(api_key.key_hash.startswith("agk_") is False)

    def test_create_records_audit_events(self):
        before = AuditEvent.objects.filter(event_type=AuditEvent.EventType.AGENT_CREATED).count()
        self.client.post(
            "/v1/agents/",
            {"name": "new-agent", "organization": str(self.organization.id)},
        )
        after = AuditEvent.objects.filter(event_type=AuditEvent.EventType.AGENT_CREATED).count()
        self.assertEqual(after, before + 1)
        key_events = AuditEvent.objects.filter(event_type=AuditEvent.EventType.KEY_CREATED)
        self.assertTrue(key_events.exists())

    def test_create_requires_admin(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(
            "/v1/agents/",
            {"name": "viewer-agent", "organization": str(self.organization.id)},
        )
        self.assertEqual(response.status_code, 403)

    def test_create_cross_org_is_rejected(self):
        response = self.client.post(
            "/v1/agents/",
            {"name": "evil-agent", "organization": str(self.other_org.id)},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Agent.objects.filter(name="evil-agent").exists())

    def test_create_invalid_input_is_rejected(self):
        response = self.client.post("/v1/agents/", {"name": "  spaced  "})
        self.assertEqual(response.status_code, 400)

    def test_create_unknown_field_is_rejected(self):
        response = self.client.post(
            "/v1/agents/",
            {"name": "evil", "organization": str(self.organization.id), "evil": 1},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_duplicate_name_is_rejected(self):
        self.client.post(
            "/v1/agents/",
            {"name": "billing-agent", "organization": str(self.organization.id)},
        )
        response = self.client.post(
            "/v1/agents/",
            {"name": "billing-agent", "organization": str(self.organization.id)},
        )
        self.assertEqual(response.status_code, 400)


class AgentRetrieveTests(AgentApiTestBase):
    def test_retrieve_returns_detail(self):
        response = self.client.get(f"/v1/agents/{self.agent.id}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], str(self.agent.id))
        self.assertIn("current_key", body)
        self.assertEqual(body["current_key"]["prefix"], self.agent.current_key.prefix)
        self.assertNotIn("key_hash", str(body))

    def test_retrieve_cross_org_is_404(self):
        self.client.force_authenticate(user=self.other_admin)
        response = self.client.get(f"/v1/agents/{self.agent.id}/")
        self.assertEqual(response.status_code, 404)

    def test_retrieve_viewer_can_access(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(f"/v1/agents/{self.agent.id}/")
        self.assertEqual(response.status_code, 200)

    def test_retrieve_unauthenticated_is_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(f"/v1/agents/{self.agent.id}/").status_code, 401)


class AgentUpdateTests(AgentApiTestBase):
    def test_admin_can_update_name(self):
        response = self.client.patch(
            f"/v1/agents/{self.agent.id}/", {"name": "renamed-agent"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "renamed-agent")

    def test_admin_can_suspend_agent(self):
        response = self.client.patch(
            f"/v1/agents/{self.agent.id}/", {"status": "suspended"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "suspended")
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, Agent.Status.SUSPENDED)

    def test_suspend_blocks_spend_requests(self):
        self.client.patch(f"/v1/agents/{self.agent.id}/", {"status": "suspended"})
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        response = self.client.post(
            "/v1/spend-requests/",
            {"amount": "10.00", "currency": "USD", "merchant": "acme.com", "source": "trusted"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="suspend-spend-1",
        )
        self.assertEqual(response.status_code, 401)

    def test_viewer_cannot_update(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.patch(
            f"/v1/agents/{self.agent.id}/", {"status": "suspended"}
        )
        self.assertEqual(response.status_code, 403)

    def test_cross_org_update_is_404(self):
        self.client.force_authenticate(user=self.other_admin)
        response = self.client.patch(
            f"/v1/agents/{self.agent.id}/", {"status": "suspended"}
        )
        self.assertEqual(response.status_code, 404)

    def test_invalid_status_is_rejected(self):
        response = self.client.patch(
            f"/v1/agents/{self.agent.id}/", {"status": "malicious"}
        )
        self.assertEqual(response.status_code, 400)

    def test_name_collision_is_rejected(self):
        Agent.create_with_key("other-agent", self.organization)
        response = self.client.patch(
            f"/v1/agents/{self.agent.id}/", {"name": "other-agent"}
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_field_in_update_is_rejected(self):
        response = self.client.patch(
            f"/v1/agents/{self.agent.id}/", {"evil": 1}
        )
        self.assertEqual(response.status_code, 400)


class AgentRotateKeyTests(AgentApiTestBase):
    def test_rotate_returns_new_raw_key(self):
        old_prefix = self.agent.current_key.prefix
        response = self.client.post(f"/v1/agents/{self.agent.id}/rotate-key/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        new_key = body["api_key"]
        self.assertTrue(new_key.startswith("agk_"))
        self.agent.refresh_from_db()
        new_prefix = self.agent.current_key.prefix
        self.assertNotEqual(old_prefix, new_prefix)

    def test_old_key_is_revoked_after_rotation(self):
        old_key = self.agent.current_key
        self.client.post(f"/v1/agents/{self.agent.id}/rotate-key/")
        old_key.refresh_from_db()
        self.assertIsNotNone(old_key.revoked_at)

    def test_rotated_key_works_for_spend(self):
        response = self.client.post(f"/v1/agents/{self.agent.id}/rotate-key/")
        new_key = response.json()["api_key"]
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_key}")
        spend_response = self.client.post(
            "/v1/spend-requests/",
            {"amount": "10.00", "currency": "USD", "merchant": "acme.com", "source": "trusted"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-rotate-spend-1",
        )
        self.assertEqual(spend_response.status_code, 201)
        self.assertEqual(spend_response.json()["decision"], "allow")

    def test_rotate_requires_admin(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(f"/v1/agents/{self.agent.id}/rotate-key/")
        self.assertEqual(response.status_code, 403)

    def test_rotate_cross_org_is_404(self):
        self.client.force_authenticate(user=self.other_admin)
        response = self.client.post(f"/v1/agents/{self.agent.id}/rotate-key/")
        self.assertEqual(response.status_code, 404)


class AgentRevokeKeyTests(AgentApiTestBase):
    def test_revoke_disables_key(self):
        old_key = self.agent.current_key
        old_prefix = old_key.prefix
        response = self.client.post(f"/v1/agents/{self.agent.id}/revoke-key/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["current_key"])
        self.assertEqual(body["revoked_key"]["prefix"], old_prefix)

    def test_revoked_key_returns_401(self):
        self.client.post(f"/v1/agents/{self.agent.id}/revoke-key/")
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        response = self.client.post(
            "/v1/spend-requests/",
            {"amount": "10.00", "currency": "USD", "merchant": "acme.com", "source": "trusted"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-revoke-spend-1",
        )
        self.assertEqual(response.status_code, 401)

    def test_revoke_without_key_returns_400(self):
        self.client.post(f"/v1/agents/{self.agent.id}/revoke-key/")
        response = self.client.post(f"/v1/agents/{self.agent.id}/revoke-key/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("No active API key", response.json()["detail"])

    def test_revoke_requires_admin(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(f"/v1/agents/{self.agent.id}/revoke-key/")
        self.assertEqual(response.status_code, 403)


class SpendApiRegressionTests(AgentApiTestBase):
    def test_existing_agent_key_still_works(self):
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        response = self.client.post(
            "/v1/spend-requests/",
            {"amount": "10.00", "currency": "USD", "merchant": "acme.com", "source": "trusted"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="regression-1",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["decision"], "allow")
