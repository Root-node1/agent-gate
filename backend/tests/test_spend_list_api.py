from unittest import SkipTest
from uuid import uuid4

from django.db import connection
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.policies.models import Policy
from apps.spend.models import SpendRequest
from apps.spend.serializers import SpendRequestSerializer
from tests.base import force_mfa

URL = "/v1/spend-requests/"

SENSITIVE_FIELDS = frozenset({
    "idempotency_key",
    "request_hash",
    "evidence_excerpt",
    "evidence_hash",
    "destination_type",
    "destination_value",
    "destination_fingerprint",
    "source_ref",
    "policy",
    "policy_version",
    "organization",
    "agent",
    "payee",
    "paypal_status",
    "decided_at",
    "executed_at",
    "updated_at",
    "key_hash",
    "api_key",
})


class SpendListApiBase(APITestCase):
    @classmethod
    def setUpClass(cls):
        if connection.vendor != "postgresql":
            raise SkipTest("spend list endpoint tests require PostgreSQL")
        super().setUpClass()

    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, self.key = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)
        self.admin = self._user("admin", OrgMembership.Role.ADMIN)
        self.approver = self._user("approver", OrgMembership.Role.APPROVER)
        self.viewer = self._user("viewer", OrgMembership.Role.VIEWER)

    def _user(self, name, role):
        user = User.objects.create_user(name)
        OrgMembership.objects.create(user=user, organization=self.organization, role=role)
        if role in (OrgMembership.Role.ADMIN, OrgMembership.Role.APPROVER):
            force_mfa(user)
        return user

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def create_request(self, organization=None, agent=None, amount_minor=1000, **kwargs):
        organization = organization or self.organization
        agent = agent or self.agent
        defaults = {
            "organization": organization,
            "agent": agent,
            "policy": self.policy,
            "policy_version": self.policy.version,
            "amount_minor": amount_minor,
            "currency": "USD",
            "merchant_ref": "acme.com",
            "decision": SpendRequest.Decision.ALLOW,
            "status": SpendRequest.Status.APPROVED,
        }
        defaults.update(kwargs)
        return SpendRequest.objects.create(**defaults)


class SpendListPermissionTests(SpendListApiBase):
    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_agent_api_key_cannot_access_dashboard_list(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key}")
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_user_without_membership_is_rejected(self):
        outsider = User.objects.create_user("outsider")
        self.authenticate(outsider)
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_admin_can_list_own_org_requests(self):
        self.create_request()
        self.authenticate(self.admin)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_approver_can_list_own_org_requests(self):
        self.create_request()
        self.authenticate(self.approver)
        self.assertEqual(self.client.get(URL).status_code, 200)

    def test_viewer_can_list_own_org_requests(self):
        self.create_request()
        self.authenticate(self.viewer)
        self.assertEqual(self.client.get(URL).status_code, 200)


class SpendListScopingTests(SpendListApiBase):
    def test_cross_organization_requests_are_excluded(self):
        self.create_request()
        other_org = Organization.objects.create(name="other")
        other_agent, _ = Agent.create_with_key("other-agent", other_org)
        Policy.objects.create(agent=other_agent)
        self.create_request(organization=other_org, agent=other_agent)
        self.authenticate(self.admin)
        body = self.client.get(URL).json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["merchant"], "acme.com")

    def test_empty_organization_returns_empty_results(self):
        self.authenticate(self.admin)
        body = self.client.get(URL).json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["results"], [])

    def test_no_duplicates_multi_org_membership(self):
        other_org = Organization.objects.create(name="second-org")
        other_agent, _ = Agent.create_with_key("second-agent", other_org)
        Policy.objects.create(agent=other_agent)
        OrgMembership.objects.create(
            user=self.admin, organization=other_org, role=OrgMembership.Role.ADMIN
        )
        req_a = self.create_request(organization=other_org, agent=other_agent)
        req_b = self.create_request(organization=self.organization, agent=self.agent)
        self.authenticate(self.admin)
        body = self.client.get(URL).json()
        ids = [r["id"] for r in body["results"]]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate spend request rows detected")
        self.assertEqual(set(ids), {str(req_b.id), str(req_a.id)})

    def test_organization_query_param_does_not_override_scope(self):
        self.create_request()
        self.authenticate(self.admin)
        body = self.client.get(f"{URL}?organization={self.organization.id}").json()
        self.assertEqual(body["count"], 1)


class SpendListPaginationTests(SpendListApiBase):
    def test_pagination_contract(self):
        self.authenticate(self.admin)
        for _ in range(3):
            self.create_request()
        body = self.client.get(URL).json()
        self.assertIn("count", body)
        self.assertIn("next", body)
        self.assertIn("previous", body)
        self.assertIn("results", body)
        self.assertEqual(body["count"], 3)
        self.assertEqual(len(body["results"]), 3)

    def test_limit_param_controls_page_size(self):
        self.authenticate(self.admin)
        for _ in range(5):
            self.create_request()
        body = self.client.get(f"{URL}?limit=2").json()
        self.assertEqual(body["count"], 5)
        self.assertEqual(len(body["results"]), 2)

    def test_offset_param_paginates(self):
        self.authenticate(self.admin)
        for _ in range(5):
            self.create_request()
        body = self.client.get(f"{URL}?limit=2&offset=2").json()
        self.assertEqual(len(body["results"]), 2)
        first_id = body["results"][0]["id"]
        all_body = self.client.get(URL).json()
        self.assertNotEqual(first_id, all_body["results"][0]["id"])


class SpendListOrderingTests(SpendListApiBase):
    def test_results_ordered_newest_first(self):
        first = self.create_request()
        second = self.create_request()
        self.authenticate(self.admin)
        body = self.client.get(URL).json()
        ids = [r["id"] for r in body["results"]]
        self.assertEqual(ids, [str(second.id), str(first.id)])

    def test_deterministic_ordering_same_timestamp(self):
        first = self.create_request()
        second = self.create_request()
        third = self.create_request()
        same_time = timezone.now()
        SpendRequest.objects.filter(
            pk__in=[first.pk, second.pk, third.pk]
        ).update(created_at=same_time)
        self.authenticate(self.admin)
        body = self.client.get(URL).json()
        ids = [r["id"] for r in body["results"]]
        expected = sorted(ids, reverse=True)
        self.assertEqual(
            ids,
            expected,
            "Results must order deterministically by -id when created_at ties",
        )


class SpendListSecurityTests(SpendListApiBase):
    def test_no_sensitive_values_in_response(self):
        self.create_request(
            idempotency_key="SECRET-KEY-123",
            request_hash="SECRET-HASH-ABC",
            evidence_excerpt="TOPSECRET-EVIDENCE",
            destination_type="paypal_email",
            destination_value="leak@paypal.com",
            destination_fingerprint="FP-SECRET",
        )
        self.authenticate(self.admin)
        body = self.client.get(URL).json()
        serialized = str(body)
        self.assertNotIn("SECRET-KEY-123", serialized)
        self.assertNotIn("SECRET-HASH-ABC", serialized)
        self.assertNotIn("TOPSECRET-EVIDENCE", serialized)
        self.assertNotIn("leak@paypal.com", serialized)
        self.assertNotIn("FP-SECRET", serialized)

    def test_response_only_contains_serializer_fields(self):
        self.create_request()
        self.authenticate(self.admin)
        body = self.client.get(URL).json()
        allowed = set(SpendRequestSerializer.Meta.fields)
        page_keys = {"count", "next", "previous", "results"}
        self.assertTrue(set(body.keys()).issubset(page_keys))
        for result in body["results"]:
            for field in SENSITIVE_FIELDS:
                self.assertNotIn(field, result)
            self.assertTrue(set(result.keys()).issubset(allowed))


class SpendListRegressionTests(SpendListApiBase):
    def test_post_still_works_with_agent_key(self):
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key}")
        response = self.client.post(
            URL,
            {"amount": "10.00", "currency": "USD", "merchant": "acme.com", "source": "trusted"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["decision"], "allow")

    def test_detail_still_works_with_agent_key(self):
        spend_request = self.create_request()
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key}")
        response = self.client.get(f"{URL}{spend_request.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(spend_request.id))


class SpendListSchemaTests(APITestCase):
    def _schema(self):
        response = self.client.get("/api/schema/?format=json")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_get_advertises_dashboard_session_auth(self):
        schema = self._schema()
        op = schema["paths"]["/v1/spend-requests/"]["get"]
        self.assertEqual(op["security"], [{"Session": []}])

    def test_post_advertises_agent_key_auth(self):
        schema = self._schema()
        op = schema["paths"]["/v1/spend-requests/"]["post"]
        self.assertEqual(op["security"], [{"AgentKey": []}])

    def test_get_advertises_paginated_response(self):
        schema = self._schema()
        op = schema["paths"]["/v1/spend-requests/"]["get"]
        schema_ref = op["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertEqual(schema_ref["$ref"], "#/components/schemas/PaginatedSpendRequestList")
