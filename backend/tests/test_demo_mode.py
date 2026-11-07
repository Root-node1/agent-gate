from io import StringIO

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Organization
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
from apps.spend.models import SpendRequest


@override_settings(DEMO_MODE=True, DEMO_ORG_NAME="demo", DEMO_USERNAME="demo-viewer")
class DemoModeApiTests(APITestCase):
    def setUp(self):
        call_command("seed_demo", stdout=StringIO())
        self.organization = Organization.objects.get(name="demo")
        self.agent = self.organization.agents.get(status="active")
        self.policy = self.agent.policies.order_by("-version").first()
        self.spend_request = SpendRequest.objects.create(
            organization=self.organization,
            agent=self.agent,
            policy=self.policy,
            policy_version=self.policy.version,
            amount_minor=100,
            currency="USD",
            merchant_ref="demo.example",
            decision=SpendRequest.Decision.NEEDS_APPROVAL,
            status=SpendRequest.Status.PENDING_APPROVAL,
        )

    def test_anonymous_can_read_demo_dashboard(self):
        response = self.client.get("/v1/spend-requests/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

        detail = self.client.get(f"/v1/spend-requests/{self.spend_request.id}/")
        self.assertEqual(detail.status_code, 200)

        audit = self.client.get("/v1/audit/")
        self.assertEqual(audit.status_code, 200)
        self.assertEqual(audit.json()["count"], 1)

    def test_demo_is_scoped_to_the_demo_organization(self):
        other = Organization.objects.create(name="real")
        other_agent = other.agents.create(name="real-agent")
        other_policy = other_agent.policies.create()
        other_request = SpendRequest.objects.create(
            organization=other,
            agent=other_agent,
            policy=other_policy,
            policy_version=other_policy.version,
            amount_minor=100,
            currency="USD",
            merchant_ref="real.example",
            decision=SpendRequest.Decision.ALLOW,
            status=SpendRequest.Status.APPROVED,
        )
        AuditEvent.record(AuditEvent.EventType.REQUEST_RECEIVED, organization=other)

        body = self.client.get("/v1/spend-requests/").json()
        self.assertEqual([row["id"] for row in body["results"]], [str(self.spend_request.id)])
        self.assertEqual(self.client.get(f"/v1/spend-requests/{other_request.id}/").status_code, 404)
        self.assertEqual(self.client.get("/v1/audit/").json()["count"], 1)

    def test_anonymous_writes_are_rejected_by_default(self):
        approval = Approval.objects.create(
            organization=self.organization,
            spend_request=self.spend_request,
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        client = APIClient(enforce_csrf_checks=True)
        for action in ("approve", "deny"):
            response = client.post(f"/v1/approvals/{approval.id}/{action}/", {}, format="json")
            self.assertEqual(response.status_code, 401)
        approval.refresh_from_db()
        self.assertEqual(approval.outcome, Approval.Outcome.PENDING)

    @override_settings(DEMO_MODE_ALLOW_WRITES=True)
    def test_anonymous_can_approve_only_inside_demo_org(self):
        approval = Approval.objects.create(
            organization=self.organization,
            spend_request=self.spend_request,
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        response = self.client.post(f"/v1/approvals/{approval.id}/approve/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["outcome"], "approved")

    def test_demo_cannot_use_admin_surfaces(self):
        self.assertEqual(self.client.get("/v1/agents/").status_code, 401)
        self.assertEqual(self.client.get("/v1/policies/").status_code, 401)


class DemoModeDisabledTests(APITestCase):
    @override_settings(DEMO_MODE=False)
    def test_anonymous_requests_are_rejected_when_disabled(self):
        self.assertEqual(self.client.get("/v1/spend-requests/").status_code, 401)
        self.assertEqual(self.client.get("/v1/audit/").status_code, 401)


@override_settings(DEMO_MODE=True, DEMO_ORG_NAME="demo", DEMO_USERNAME="demo-viewer")
class DemoModeSchemaTests(APITestCase):
    def test_demo_mode_is_not_advertised_as_a_credential_scheme(self):
        schema = self.client.get("/api/schema/?format=json").json()
        schemes = schema.get("components", {}).get("securitySchemes", {})
        self.assertNotIn("DemoMode", schemes)
        self.assertEqual(
            schema["paths"]["/v1/approvals/"]["get"]["security"],
            [{"Session": []}],
        )
