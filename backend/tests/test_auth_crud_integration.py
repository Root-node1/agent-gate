"""INT-01: Cross-module integration tests spanning AUTH-01 and CRUD-03B.

These tests exercise the full authenticated admin workflow through genuine
login, email verification, Django sessions, CSRF, and organization memberships —
no ``force_authenticate`` bypasses.
"""

import re
import uuid
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Organization, OrgMembership
from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from tests.base import force_mfa

User = get_user_model()

PASSWORD = "Abc!12345"
HEADLESS_BASE = "/api/auth/headless/browser/v1"


def unique_email(prefix="integ"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def headless_signup(client, email=None, password=PASSWORD):
    if email is None:
        email = unique_email()
    return client.post(
        f"{HEADLESS_BASE}/auth/signup",
        {"email": email, "password": password},
        format="json",
    )


def extract_verification_code():
    assert len(mail.outbox) == 1, f"expected exactly one email, got {len(mail.outbox)}"
    match = re.search(r"code[:\s]+([A-Z0-9]{4}-[A-Z0-9]{4})", mail.outbox[0].body)
    assert match, f"verification code not found in email body: {mail.outbox[0].body!r}"
    return match.group(1)


def headless_verify_email(client, code):
    return client.post(
        f"{HEADLESS_BASE}/auth/email/verify",
        {"key": code},
        format="json",
    )


def headless_login(client, email, password=PASSWORD):
    return client.post(
        f"{HEADLESS_BASE}/auth/login",
        {"email": email, "password": password},
        format="json",
    )


def get_csrf_token(client):
    response = client.get(f"{HEADLESS_BASE}/config")
    return response.cookies["csrftoken"].value


def policy_payload(agent_id, **overrides):
    payload = {
        "agent": str(agent_id),
        "name": "Restrictive policy",
        "currency": "USD",
        "per_transaction_cap": "100.00",
        "approval_threshold": "50.00",
        "daily_budget": "500.00",
        "weekly_budget": "2000.00",
        "monthly_budget": "5000.00",
        "merchant_window_cap": "100.00",
        "merchant_mode": "blocklist",
        "velocity_max_count": 0,
        "velocity_window_seconds": 3600,
        "new_payee_cooldown_hours": 0,
        "untrusted_source_action": "needs_approval",
        "injection_escalate_threshold": 60,
        "classifier_required": False,
        "approval_ttl_minutes": 60,
        "timezone": "Africa/Nairobi",
        "merchant_rules": [
            {"merchant_ref": "acme.com", "kind": "allow", "note": "vendor"},
            {"merchant_ref": "evil.com", "kind": "block"},
        ],
    }
    payload.update(overrides)
    return payload


class _SignupMixin:
    """Signup → verify → login via genuine allauth headless flow."""

    def _full_signup_flow(self, client, email=None):
        if email is None:
            email = unique_email()
        mail.outbox.clear()
        headless_signup(client, email=email)
        code = extract_verification_code()
        headless_verify_email(client, code)
        login_resp = headless_login(client, email=email)
        self.assertIn(login_resp.status_code, (200, 409))
        return User.objects.get(email=email), email


class AuthCrudIntegrationTest(APITestCase, _SignupMixin):
    """End-to-end admin workflow through genuine allauth headless auth."""

    def setUp(self):
        mail.outbox.clear()
        self.email = unique_email("integration")

    def test_full_admin_workflow_through_genuine_session(self):
        """Signup → verify → login → org membership → agent → policy →
        policy update → merchant-rule add → merchant-rule delete → audit → logout."""
        client = APIClient()

        # 1-3. Signup, email verification, login
        user, _ = self._full_signup_flow(client, self.email)
        force_mfa(user)

        # Verify dashboard session
        user_resp = client.get("/api/auth/user/")
        self.assertEqual(user_resp.status_code, 200)
        self.assertEqual(user_resp.json()["email"], self.email)
        self.assertTrue(user_resp.json()["is_email_verified"])
        self.assertEqual(user_resp.json()["memberships"], [])

        # 4. CSRF token
        csrf_token = get_csrf_token(client)

        # 5. Organization membership assignment (trusted test fixture)
        org = Organization.objects.create(name="acme-corp")
        OrgMembership.objects.create(
            user=user, organization=org, role=OrgMembership.Role.ADMIN
        )
        updated = client.get("/api/auth/user/").json()
        self.assertEqual(len(updated["memberships"]), 1)

        # 6. Create agent (POST /v1/agents/)
        agent_resp = client.post(
            "/v1/agents/",
            {"name": "test-agent", "organization": str(org.id)},
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )
        self.assertEqual(agent_resp.status_code, 201)
        agent_body = agent_resp.json()
        self.assertTrue(agent_body["api_key"].startswith("agk_"))
        agent_id = agent_body["id"]

        # 7. Create policy (POST /v1/policies/) — version 1, minor-unit response
        policy_resp = client.post(
            "/v1/policies/",
            policy_payload(agent_id),
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )
        self.assertEqual(policy_resp.status_code, 201)
        policy_body = policy_resp.json()
        self.assertEqual(policy_body["version"], 1)
        self.assertEqual(policy_body["currency"], "USD")
        self.assertEqual(policy_body["per_transaction_cap_minor"], 10_000)
        self.assertEqual(policy_body["daily_budget_minor"], 50_000)
        policy_id = policy_body["id"]

        # 8. Patch policy (PATCH /v1/policies/{id}/) — version 1 → 2
        patch_resp = client.patch(
            f"/v1/policies/{policy_id}/",
            {"expected_version": 1, "daily_budget": "750.00"},
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()["version"], 2)
        self.assertEqual(patch_resp.json()["daily_budget_minor"], 75_000)
        policy_id_v2 = patch_resp.json()["id"]
        self.assertNotEqual(policy_id_v2, policy_id)

        # 9a. Add merchant rule (POST /v1/policies/{id}/merchant-rules/) — v2 → v3
        add_resp = client.post(
            f"/v1/policies/{policy_id_v2}/merchant-rules/",
            {
                "expected_version": 2,
                "merchant_ref": "vendor.com",
                "kind": "allow",
                "note": "preferred vendor",
            },
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )
        self.assertEqual(add_resp.status_code, 201)
        self.assertEqual(add_resp.json()["version"], 3)
        vendor_rule = next(
            r for r in add_resp.json()["merchant_rules"] if r["merchant_ref"] == "vendor.com"
        )
        rule_id = vendor_rule["id"]
        policy_id_v3 = add_resp.json()["id"]

        # 9b. Delete merchant rule (DELETE with If-Match header) — v3 → v4
        delete_resp = client.delete(
            f"/v1/policies/{policy_id_v3}/merchant-rules/{rule_id}/",
            HTTP_IF_MATCH="3",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(delete_resp.status_code, 200)
        self.assertEqual(delete_resp.json()["version"], 4)
        remaining = {r["merchant_ref"] for r in delete_resp.json()["merchant_rules"]}
        self.assertNotIn("vendor.com", remaining)

        # 10. Audit chain verification
        policy_events = AuditEvent.objects.filter(
            event_type=AuditEvent.EventType.POLICY_CHANGED,
            actor_id=str(user.id),
        )
        self.assertGreaterEqual(policy_events.count(), 4)
        actions = {e.payload["action"] for e in policy_events}
        self.assertIn("created", actions)
        self.assertIn("updated", actions)
        self.assertIn("merchant_rule_added", actions)
        self.assertIn("merchant_rule_removed", actions)

        agent_events = AuditEvent.objects.filter(
            event_type=AuditEvent.EventType.AGENT_CREATED,
            actor_id=str(user.id),
        )
        self.assertEqual(agent_events.count(), 1)

        out = StringIO()
        call_command("verify_audit", stdout=out)
        self.assertIn("verified", out.getvalue().lower())

        # 11. Logout — invalidates session
        logout_resp = client.post("/api/auth/logout/")
        self.assertEqual(logout_resp.status_code, 204)
        self.assertEqual(client.get("/api/auth/user/").status_code, 401)


class CrossModulePermissionTests(APITestCase, _SignupMixin):
    """Agent API keys and non-admin members must not access CRUD endpoints."""

    def setUp(self):
        mail.outbox.clear()
        self.client = APIClient()
        self.user, self.email = self._full_signup_flow(self.client)
        force_mfa(self.user)

        org = Organization.objects.create(name="perm-org")
        OrgMembership.objects.create(
            user=self.user, organization=org, role=OrgMembership.Role.ADMIN
        )
        self.org = org
        csrf_token = get_csrf_token(self.client)
        resp = self.client.post(
            "/v1/agents/",
            {"name": "perm-agent", "organization": str(org.id)},
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.raw_key = resp.json()["api_key"]

    def test_agent_api_key_cannot_access_crud_or_dashboard(self):
        """Agent API keys must not authenticate dashboard endpoints."""
        self.client.post("/api/auth/logout/")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(self.client.get("/v1/agents/").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/user/").status_code, 401)

    def test_non_admin_viewer_cannot_create_agent(self):
        """A VIEWER member must receive 403 on agent/POST."""
        viewer_client = APIClient()
        _, _ = self._full_signup_flow(viewer_client, unique_email("viewer"))
        viewer = User.objects.get(email=_)
        OrgMembership.objects.create(
            user=viewer, organization=self.org, role=OrgMembership.Role.VIEWER
        )
        csrf_token = get_csrf_token(viewer_client)
        resp = viewer_client.post(
            "/v1/agents/",
            {"name": "evil-agent", "organization": str(self.org.id)},
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_foreign_admin_cannot_create_agent_in_other_org(self):
        """Admin of org B must be rejected (400) when targeting an agent in org A."""
        foreign_client = APIClient()
        f_user, _f_email = self._full_signup_flow(foreign_client)
        force_mfa(f_user)
        f_org = Organization.objects.create(name="foreign-org")
        OrgMembership.objects.create(
            user=f_user, organization=f_org, role=OrgMembership.Role.ADMIN
        )
        csrf_token = get_csrf_token(foreign_client)
        resp = foreign_client.post(
            "/v1/agents/",
            {"name": "cross-agent", "organization": str(self.org.id)},
            HTTP_X_CSRFTOKEN=csrf_token,
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class CrossModuleCsrfTests(APITestCase, _SignupMixin):
    """CSRF enforcement on state-changing CRUD operations."""

    def setUp(self):
        mail.outbox.clear()
        self.client = APIClient()
        self.user, _ = self._full_signup_flow(self.client)
        force_mfa(self.user)
        org = Organization.objects.create(name="csrf-org")
        OrgMembership.objects.create(
            user=self.user, organization=org, role=OrgMembership.Role.ADMIN
        )
        self.org = org

    def test_create_agent_without_csrf_returns_403(self):
        """POST /v1/agents/ without X-CSRFToken header must be rejected."""
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.cookies = self.client.cookies
        csrf_client.get(f"{HEADLESS_BASE}/config")

        resp = csrf_client.post(
            "/v1/agents/",
            {"name": "no-csrf", "organization": str(self.org.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Agent.objects.filter(name="no-csrf").exists())

    def test_create_agent_with_csrf_succeeds(self):
        """POST /v1/agents/ with a valid X-CSRFToken must succeed."""
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.cookies = self.client.cookies
        token = csrf_client.get(f"{HEADLESS_BASE}/config").cookies["csrftoken"].value

        resp = csrf_client.post(
            "/v1/agents/",
            {"name": "with-csrf", "organization": str(self.org.id)},
            HTTP_X_CSRFTOKEN=token,
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
