"""AUTH-05B.3B: MFA enrollment enforcement permission tests.

Verifies the permission composition in ``apps/accounts/permissions.py``:

1.  Authenticated admin without MFA → 403 mfa_enrollment_required
2.  Authenticated approver without MFA → 403 mfa_enrollment_required
3.  Admin with MFA → 200 (existing RBAC behaviour restored)
4.  Approver with MFA → 200 (existing RBAC behaviour restored)
5.  Viewer without MFA → 200 on IsDashboardUser (read) endpoints
6.  Viewer → 403 on IsApprover / IsOrganizationAdmin (not mfa_enrollment_required)
7.  Agent API key → 401 on privileged human-only routes
8.  Anonymous → 401 on privileged endpoints
9.  Wrong-organization access → 404 (data isolation preserved)
10. Pending MFA challenge → 401 before MFA completion
11. MFA enrollment endpoints → 200 for an unenrolled admin
12. Logout + password-reset → accessible without MFA

Run with PostgreSQL:
    TEST_DATABASE_URL=postgresql://agentgate:agentgate@localhost:5432/agentgate \\
    python manage.py test tests.test_auth_mfa_drf_bypass
"""

import re
import time
import uuid
from http import HTTPStatus

from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.totp.internal.auth import (
    format_hotp_value,
    hotp_value,
    validate_totp_code,
)
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Organization, OrgMembership
from apps.agents.models import Agent

User = get_user_model()

HEADLESS_BASE = "/api/auth/headless/browser/v1"
PASSWORD = "Abc!12345"

# Privileged route URLs
APPROVAL_LIST_URL = "/v1/approvals/"
AUDIT_LIST_URL = "/v1/audit/"
AUDIT_VERIFY_URL = "/v1/audit/verify/"
USER_URL = "/api/auth/user/"
LOGOUT_URL = "/api/auth/logout/"
AGENT_DETAIL_URL = "/v1/agents/{id}/"
TOTP_MANAGE_URL = f"{HEADLESS_BASE}/account/authenticators/totp"
MFA_AUTHENTICATE_URL = f"{HEADLESS_BASE}/auth/2fa/authenticate"
MFA_REAUTHENTICATE_URL = f"{HEADLESS_BASE}/auth/reauthenticate"
PASSWORD_REQUEST_URL = f"{HEADLESS_BASE}/auth/password/request"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def unique_email(prefix="mfa"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def _extract_code():
    assert len(mail.outbox) == 1, f"expected one email, got {len(mail.outbox)}"
    match = re.search(r"code[:\s]+([A-Z0-9]{4}-[A-Z0-9]{4})", mail.outbox[0].body)
    assert match, f"verification code not found in: {mail.outbox[0].body!r}"
    return match.group(1)


def _signup_verify_login(email, password=PASSWORD):
    """Full signup -> verify -> login. Returns an authenticated APIClient."""
    client = APIClient()
    mail.outbox.clear()
    client.post(
        f"{HEADLESS_BASE}/auth/signup",
        {"email": email, "password": password},
        format="json",
    )
    code = _extract_code()
    client.post(f"{HEADLESS_BASE}/auth/email/verify", {"key": code}, format="json")
    resp = client.post(
        f"{HEADLESS_BASE}/auth/login",
        {"email": email, "password": password},
        format="json",
    )
    assert resp.status_code in (200, 409), f"login failed: {resp.status_code} {resp.content}"
    return client


def _compute_totp(secret):
    """Compute a valid TOTP code from a provisioning secret."""
    counter = int(time.time()) // mfa_settings.TOTP_PERIOD
    code = format_hotp_value(hotp_value(secret, counter))
    if not validate_totp_code(secret, code):
        time.sleep(1)
        counter = int(time.time()) // mfa_settings.TOTP_PERIOD
        code = format_hotp_value(hotp_value(secret, counter))
    return code


def _enroll_totp(client):
    """Enroll TOTP for the logged-in, reauthenticated user. Returns the secret."""
    resp = client.get(TOTP_MANAGE_URL)
    assert resp.status_code in (200, 404), f"TOTP GET failed: {resp.status_code} {resp.content}"
    secret = resp.json()["meta"]["secret"]
    code = _compute_totp(secret)
    resp = client.post(TOTP_MANAGE_URL, {"code": code}, format="json")
    assert resp.status_code == 200, f"TOTP POST failed: {resp.content}"
    return secret


def _create_user(role, email=None, with_mfa=False):
    """Signup -> verify -> login -> assign org role -> optionally enroll TOTP.

    Returns ``(client, user, org, totp_secret_or_none)``.
    """
    if email is None:
        email = unique_email()
    client = _signup_verify_login(email)
    org = Organization.objects.create(name=f"{role.value}-org-{uuid.uuid4().hex[:6]}")
    user = User.objects.get(email=email)
    OrgMembership.objects.create(user=user, organization=org, role=role)
    secret = None
    if with_mfa:
        client.post(MFA_REAUTHENTICATE_URL, {"password": PASSWORD}, format="json")
        secret = _enroll_totp(client)
    return client, user, org, secret


def _pending_mfa_flow(response):
    flows = response.json()["data"]["flows"]
    return next((f for f in flows if f["id"] == "mfa_authenticate"), None)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

class MFAEnforcementPermissionTests(APITestCase):
    """AUTH-05B.3B: privileged MFA enrollment enforcement through DRF permissions."""

    # 1. Admin without MFA denied
    def test_admin_without_mfa_denied(self):
        client, _, _, _ = _create_user(OrgMembership.Role.ADMIN)
        resp = client.get(AUDIT_VERIFY_URL)
        self.assertEqual(resp.status_code, HTTPStatus.FORBIDDEN)
        self.assertEqual(resp.json()["code"], "mfa_enrollment_required")

    # 2. Approver without MFA denied
    def test_approver_without_mfa_denied(self):
        client, _, _, _ = _create_user(OrgMembership.Role.APPROVER)
        resp = client.get(APPROVAL_LIST_URL)
        self.assertEqual(resp.status_code, HTTPStatus.FORBIDDEN)
        self.assertEqual(resp.json()["code"], "mfa_enrollment_required")

    # 3. Admin with MFA allowed
    def test_admin_with_mfa_allowed(self):
        client, _, _, _ = _create_user(OrgMembership.Role.ADMIN, with_mfa=True)
        resp = client.get(AUDIT_VERIFY_URL)
        self.assertEqual(resp.status_code, HTTPStatus.OK)

    # 4. Approver with MFA allowed
    def test_approver_with_mfa_allowed(self):
        client, _, _, _ = _create_user(OrgMembership.Role.APPROVER, with_mfa=True)
        resp = client.get(APPROVAL_LIST_URL)
        self.assertEqual(resp.status_code, HTTPStatus.OK)

    # 5. Viewer without MFA retains permitted read access
    def test_viewer_without_mfa_retains_read_access(self):
        client, _, _, _ = _create_user(OrgMembership.Role.VIEWER)
        resp = client.get(AUDIT_LIST_URL)
        self.assertEqual(resp.status_code, HTTPStatus.OK)

    # 6. Viewer denied admin and approver operations
    def test_viewer_denied_admin_and_approver_operations(self):
        client, _, _, _ = _create_user(OrgMembership.Role.VIEWER)

        resp = client.get(AUDIT_VERIFY_URL)
        self.assertEqual(resp.status_code, HTTPStatus.FORBIDDEN)
        self.assertNotIn(
            "mfa_enrollment_required",
            str(resp.json()),
            "viewer must not receive mfa_enrollment_required",
        )

        resp = client.get(APPROVAL_LIST_URL)
        self.assertEqual(resp.status_code, HTTPStatus.FORBIDDEN)
        self.assertNotIn(
            "mfa_enrollment_required",
            str(resp.json()),
            "viewer must not receive mfa_enrollment_required",
        )

    # 7. Agent-key principal denied human-only routes
    def test_agent_key_denied_human_only_routes(self):
        org = Organization.objects.create(name=f"agent-org-{uuid.uuid4().hex[:6]}")
        _agent, raw_key = Agent.create_with_key("agent-key-user", org)

        anon = APIClient()
        anon.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        for url in (APPROVAL_LIST_URL, AUDIT_VERIFY_URL, USER_URL):
            resp = anon.get(url)
            self.assertEqual(
                resp.status_code,
                HTTPStatus.UNAUTHORIZED,
                f"agent key accessed {url}",
            )

    # 8. Anonymous requests denied
    def test_anonymous_denied(self):
        anon = APIClient()
        for url in (APPROVAL_LIST_URL, AUDIT_VERIFY_URL, USER_URL):
            resp = anon.get(url)
            self.assertEqual(
                resp.status_code,
                HTTPStatus.UNAUTHORIZED,
                f"anonymous accessed {url}",
            )

    # 9. Wrong-organization access remains denied
    def test_wrong_org_access_denied(self):
        client, _, _, _ = _create_user(OrgMembership.Role.ADMIN, with_mfa=True)
        org_b = Organization.objects.create(name=f"foreign-{uuid.uuid4().hex[:6]}")
        agent_b = Agent.objects.create(name="foreign-agent", organization=org_b)
        resp = client.get(AGENT_DETAIL_URL.format(id=agent_b.id))
        self.assertEqual(resp.status_code, HTTPStatus.NOT_FOUND)

    # 10. Pending MFA challenge does not authorize privileged access
    def test_pending_mfa_challenge_blocks_privileged_access(self):
        email = unique_email("mfa-pending")
        client = _signup_verify_login(email)
        org = Organization.objects.create(name=f"pending-{uuid.uuid4().hex[:6]}")
        user = User.objects.get(email=email)
        OrgMembership.objects.create(
            user=user, organization=org, role=OrgMembership.Role.ADMIN
        )

        # Enroll TOTP
        client.post(MFA_REAUTHENTICATE_URL, {"password": PASSWORD}, format="json")
        secret = _enroll_totp(client)

        # Logout so the next login enters the MFA pending stage
        headless_logout_resp = client.delete(f"{HEADLESS_BASE}/auth/session")
        assert headless_logout_resp.status_code == HTTPStatus.UNAUTHORIZED

        # Password login — should enter MFA pending stage (not authenticated)
        login_resp = client.post(
            f"{HEADLESS_BASE}/auth/login",
            {"email": email, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(login_resp.status_code, HTTPStatus.UNAUTHORIZED)
        self.assertFalse(login_resp.json()["meta"]["is_authenticated"])
        flow = _pending_mfa_flow(login_resp)
        self.assertIsNotNone(flow, "expected pending mfa_authenticate flow")
        self.assertTrue(flow["is_pending"])

        # Privileged access blocked before MFA completes
        resp = client.get(AUDIT_VERIFY_URL)
        self.assertEqual(resp.status_code, HTTPStatus.UNAUTHORIZED)
        resp = client.get(APPROVAL_LIST_URL)
        self.assertEqual(resp.status_code, HTTPStatus.UNAUTHORIZED)

        # Complete MFA challenge
        mfa_resp = client.post(
            MFA_AUTHENTICATE_URL,
            {"code": _compute_totp(secret)},
            format="json",
        )
        self.assertEqual(mfa_resp.status_code, HTTPStatus.OK)
        self.assertTrue(mfa_resp.json()["meta"]["is_authenticated"])

        # Privileged access now granted
        resp = client.get(AUDIT_VERIFY_URL)
        self.assertEqual(resp.status_code, HTTPStatus.OK)
        resp = client.get(APPROVAL_LIST_URL)
        self.assertEqual(resp.status_code, HTTPStatus.OK)

    # 11. MFA enrollment endpoints remain accessible to unenrolled admins
    def test_mfa_enrollment_endpoints_accessible_to_unenrolled_admin(self):
        client, _, _, _ = _create_user(OrgMembership.Role.ADMIN, with_mfa=False)
        # Reauthentication is required by allauth before MFA management
        client.post(MFA_REAUTHENTICATE_URL, {"password": PASSWORD}, format="json")
        resp = client.get(TOTP_MANAGE_URL)
        self.assertIn(resp.status_code, (HTTPStatus.OK, HTTPStatus.NOT_FOUND))
        self.assertIn("secret", resp.json()["meta"])

    # 12a. Logout remains accessible to unenrolled admins
    def test_logout_accessible_without_mfa(self):
        client, _, _, _ = _create_user(OrgMembership.Role.ADMIN, with_mfa=False)
        resp = client.post(LOGOUT_URL)
        self.assertEqual(resp.status_code, HTTPStatus.NO_CONTENT)
        self.assertEqual(client.get(USER_URL).status_code, HTTPStatus.UNAUTHORIZED)

    # 12b. Account recovery (password reset) remains accessible
    def test_password_reset_accessible_to_anonymous(self):
        anon = APIClient()
        resp = anon.post(
            PASSWORD_REQUEST_URL,
            {"email": "recover@example.com"},
            format="json",
        )
        self.assertIn(resp.status_code, (HTTPStatus.OK, HTTPStatus.ACCEPTED))
