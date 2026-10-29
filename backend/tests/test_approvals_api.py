from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.approvals import services as approval_services
from apps.approvals.models import Approval
from apps.audit.models import AuditEvent
from apps.payees.models import Payee, fingerprint
from apps.policies.models import Policy
from apps.spend import services
from apps.spend.models import SpendRequest
from tests.base import force_mfa


class ApprovalApiBase(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, self.key = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent)
        self.approver = self.user("approver", OrgMembership.Role.APPROVER)
        self.admin = self.user("admin", OrgMembership.Role.ADMIN)
        self.viewer = self.user("viewer", OrgMembership.Role.VIEWER)

    def user(self, name, role):
        user = User.objects.create_user(name)
        OrgMembership.objects.create(user=user, organization=self.organization, role=role)
        if role in (OrgMembership.Role.ADMIN, OrgMembership.Role.APPROVER):
            force_mfa(user)
        return user

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def pending(self, amount="75.00", **kwargs):
        spend_request, _ = services.submit_spend_request(
            self.agent,
            amount=Decimal(amount),
            currency="USD",
            merchant="acme.com",
            source_type=SpendRequest.SourceType.TRUSTED,
            **kwargs,
        )
        self.assertEqual(spend_request.decision, SpendRequest.Decision.NEEDS_APPROVAL)
        return spend_request

    def url(self, approval):
        return f"/v1/approvals/{approval.pk}/"


class ApprovalPermissionTests(ApprovalApiBase):
    def test_agent_key_cannot_reach_approvals(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key}")
        response = self.client.get("/v1/approvals/")
        self.assertIn(response.status_code, (401, 403))

    def test_user_without_membership_is_rejected(self):
        outsider = User.objects.create_user("outsider")
        self.authenticate(outsider)
        self.assertEqual(self.client.get("/v1/approvals/").status_code, 403)

    def test_viewer_cannot_read_or_decide(self):
        approval = self.pending()
        self.authenticate(self.viewer)
        self.assertEqual(self.client.get(self.url(approval)).status_code, 403)
        denied = self.client.post(self.url(approval) + "approve/", {}, format="json")
        self.assertEqual(denied.status_code, 403)

    def test_session_post_is_csrf_protected(self):
        approval = self.pending()
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.approver)
        response = client.post(self.url(approval) + "approve/", {}, format="json")
        self.assertEqual(response.status_code, 403)


class ApprovalListTests(ApprovalApiBase):
    def test_pending_is_the_default_and_all_includes_decided(self):
        pending = self.pending()
        denied = self.pending(amount="80.00")
        approval_services.decide(denied.approval.pk, user=self.approver, approve=False)
        self.authenticate(self.approver)

        default = self.client.get("/v1/approvals/").json()
        self.assertEqual(default["count"], 1)
        self.assertEqual(default["results"][0]["id"], str(pending.approval.pk))
        every = self.client.get("/v1/approvals/?outcome=all").json()
        self.assertEqual(every["count"], 2)

    def test_approvals_are_scoped_to_the_users_organizations(self):
        mine = self.pending()
        other_org = Organization.objects.create(name="other")
        other_agent, _ = Agent.create_with_key("other", other_org)
        Policy.objects.create(agent=other_agent)
        other, _ = services.submit_spend_request(
            other_agent,
            amount=Decimal("75.00"),
            currency="USD",
            merchant="acme.com",
            source_type=SpendRequest.SourceType.TRUSTED,
        )
        self.authenticate(self.approver)

        body = self.client.get("/v1/approvals/").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], str(mine.approval.pk))
        self.assertEqual(self.client.get(self.url(other.approval)).status_code, 404)

    def test_invalid_outcome_filter_is_rejected(self):
        self.authenticate(self.approver)
        self.assertEqual(self.client.get("/v1/approvals/?outcome=maybe").status_code, 400)


class ApprovalDecisionTests(ApprovalApiBase):
    def test_approve_updates_both_rows_and_audits_the_user(self):
        spend_request = self.pending()
        self.authenticate(self.approver)
        response = self.client.post(
            self.url(spend_request.approval) + "approve/", {"note": "looks fine"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["outcome"], "approved")
        self.assertEqual(response.json()["status"], "approved")
        self.assertEqual(response.json()["note"], "looks fine")

        spend_request.refresh_from_db()
        approval = Approval.objects.get(pk=spend_request.approval.pk)
        self.assertEqual(spend_request.status, SpendRequest.Status.APPROVED)
        self.assertEqual(approval.approver, self.approver)
        event = AuditEvent.objects.get(event_type=AuditEvent.EventType.APPROVAL_APPROVED)
        self.assertEqual(event.actor_id, str(self.approver.pk))
        self.assertEqual(event.spend_request, spend_request)

    def test_double_approve_is_idempotent(self):
        spend_request = self.pending()
        self.authenticate(self.approver)
        url = self.url(spend_request.approval) + "approve/"
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 200)
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 200)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type=AuditEvent.EventType.APPROVAL_APPROVED
            ).count(),
            1,
        )

    def test_deny_marks_the_request_rejected(self):
        spend_request = self.pending()
        self.authenticate(self.approver)
        response = self.client.post(self.url(spend_request.approval) + "deny/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["outcome"], "denied")
        spend_request.refresh_from_db()
        self.assertEqual(spend_request.status, SpendRequest.Status.REJECTED)
        self.assertTrue(
            AuditEvent.objects.filter(event_type=AuditEvent.EventType.APPROVAL_DENIED).exists()
        )

    def test_conflicting_decision_is_rejected(self):
        spend_request = self.pending()
        self.authenticate(self.approver)
        self.client.post(self.url(spend_request.approval) + "approve/", {}, format="json")
        response = self.client.post(self.url(spend_request.approval) + "deny/", {}, format="json")
        self.assertEqual(response.status_code, 409)

    def test_recheck_denies_when_the_budget_is_now_too_low(self):
        spend_request = self.pending()
        self.policy.daily_budget_minor = 5_000
        self.policy.save()
        self.authenticate(self.approver)
        response = self.client.post(
            self.url(spend_request.approval) + "approve/", {}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("R06_DAILY_BUDGET", response.json()["rules"])
        spend_request.refresh_from_db()
        self.assertEqual(spend_request.status, SpendRequest.Status.PENDING_APPROVAL)
        self.assertEqual(spend_request.approval.outcome, Approval.Outcome.PENDING)

    def test_recheck_denies_when_the_destination_changed(self):
        spend_request = self.pending(
            destination_type="paypal_email", destination_value="old@example.com"
        )
        services.submit_spend_request(
            self.agent,
            amount=Decimal("10.00"),
            currency="USD",
            merchant="acme.com",
            source_type=SpendRequest.SourceType.TRUSTED,
            destination_type="paypal_email",
            destination_value="new@example.com",
        )
        payee = Payee.objects.get(organization=self.organization, merchant_ref="acme.com")
        self.assertEqual(payee.destination_fingerprint, fingerprint("paypal_email", "new@example.com"))
        self.authenticate(self.approver)
        response = self.client.post(
            self.url(spend_request.approval) + "approve/", {}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["rules"], ["destination_changed"])

    def test_expired_approval_cannot_be_approved(self):
        spend_request = self.pending()
        Approval.objects.filter(pk=spend_request.approval.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.authenticate(self.approver)
        response = self.client.post(
            self.url(spend_request.approval) + "approve/", {}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            Approval.objects.get(pk=spend_request.approval.pk).outcome,
            Approval.Outcome.EXPIRED,
        )
        spend_request.refresh_from_db()
        self.assertEqual(spend_request.status, SpendRequest.Status.EXPIRED)
        self.assertTrue(
            AuditEvent.objects.filter(event_type=AuditEvent.EventType.APPROVAL_EXPIRED).exists()
        )

    def test_admin_can_decide(self):
        spend_request = self.pending()
        self.authenticate(self.admin)
        response = self.client.post(
            self.url(spend_request.approval) + "approve/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200)
