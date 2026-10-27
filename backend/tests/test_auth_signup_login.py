"""AUTH-01: email/password signup, login, session, logout and CSRF behaviour (headless)."""

import re
import uuid

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.test.utils import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Organization, OrgMembership
from apps.agents.models import Agent

User = get_user_model()

PASSWORD = "Abc!12345"

HEADLESS_BASE = "/api/auth/headless/browser/v1"


def unique_email(prefix="dash"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def headless_signup(client, email=None, password=PASSWORD):
    """Signup via headless API. Returns response."""
    if email is None:
        email = unique_email()
    return client.post(
        f"{HEADLESS_BASE}/auth/signup",
        {"email": email, "password": password},
        format="json",
    )


def headless_verify_email(client, code):
    """Verify email via headless API using code in request body."""
    return client.post(
        f"{HEADLESS_BASE}/auth/email/verify",
        {"key": code},
        format="json",
    )


def headless_login(client, email=unique_email(), password=PASSWORD):
    """Login via headless API."""
    return client.post(
        f"{HEADLESS_BASE}/auth/login",
        {"email": email, "password": password},
        format="json",
    )


def headless_logout(client):
    """Logout via headless API."""
    return client.delete(f"{HEADLESS_BASE}/auth/session")


def headless_current_user(client):
    """Get current user via headless API."""
    return client.get(f"{HEADLESS_BASE}/auth/session")


def get_csrf_token(client):
    """Get CSRF token by hitting config endpoint."""
    response = client.get(f"{HEADLESS_BASE}/config")
    return response.cookies.get("csrftoken").value if "csrftoken" in response.cookies else None


def extract_verification_code():
    """Extract verification code from the last sent email."""
    assert len(mail.outbox) == 1, f"expected exactly one email, got {len(mail.outbox)}"
    match = re.search(r"code[:\s]+([A-Z0-9]{4}-[A-Z0-9]{4})", mail.outbox[0].body)
    assert match, f"verification code not found in email body: {mail.outbox[0].body!r}"
    return match.group(1)


class AuthTestBase(APITestCase):
    def setUp(self):
        super().setUp()
        mail.outbox.clear()
        self.email = unique_email()

    def _signup_and_verify(self, email=None):
        """Helper to signup and verify a user."""
        if email is None:
            email = self.email
        headless_signup(self.client, email=email)
        code = extract_verification_code()
        headless_verify_email(self.client, code)
        return User.objects.get(email=email)


class SignupTests(AuthTestBase):
    def test_signup_creates_unverified_account_and_sends_confirmation(self):
        response = headless_signup(self.client, email=self.email)
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.json()["meta"]["is_authenticated"] is False)
        flows = response.json()["data"]["flows"]
        verify_flow = next((f for f in flows if f["id"] == "verify_email"), None)
        self.assertIsNotNone(verify_flow)
        self.assertTrue(verify_flow.get("is_pending"))

        user = User.objects.get(email=self.email)
        self.assertTrue(user.has_usable_password())
        address = EmailAddress.objects.get(email=self.email)
        self.assertFalse(address.verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.email])

    def test_signup_password_is_hashed_not_plaintext(self):
        response = headless_signup(self.client, email=self.email)
        self.assertEqual(response.status_code, 401)
        user = User.objects.get(email=self.email)
        self.assertNotEqual(user.password, PASSWORD)
        self.assertIn("$", user.password)
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))

    def test_signup_duplicate_email_is_rejected(self):
        headless_signup(self.client, email=self.email)
        response = headless_signup(self.client, email=self.email)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(User.objects.filter(email=self.email).count(), 1)


class DomainRestrictionTests(AuthTestBase):
    @override_settings(ACCOUNT_ALLOWED_SIGNUP_DOMAINS=["example.com"])
    def test_allowlisted_domain_signups(self):
        response = headless_signup(self.client, email="dash@example.com")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(User.objects.filter(email="dash@example.com").exists())

    @override_settings(ACCOUNT_ALLOWED_SIGNUP_DOMAINS=["example.com"])
    def test_non_allowlisted_domain_is_blocked(self):
        response = headless_signup(self.client, email="attacker@bad.example")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="attacker@bad.example").exists())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ACCOUNT_ALLOWED_SIGNUP_DOMAINS=[])
    def test_empty_allowlist_allows_all_domains(self):
        response = headless_signup(self.client, email="anybody@anywhere.com")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(User.objects.filter(email="anybody@anywhere.com").exists())


class LoginTests(AuthTestBase):
    def setUp(self):
        super().setUp()
        self.user = self._signup_and_verify()

    def test_unverified_user_cannot_log_in(self):
        client = APIClient()
        email = unique_email("fresh")
        headless_signup(client, email=email)
        response = headless_login(client, email=email)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["meta"]["is_authenticated"])
        self.assertEqual(client.get("/api/auth/user/").status_code, 401)

    def test_verified_user_can_log_in(self):
        response = headless_login(self.client, email=self.email)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get("/api/auth/user/").status_code, 200)

    def test_wrong_password_is_rejected(self):
        client = APIClient()
        response = headless_login(client, email=self.email, password="wrong")
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())

    def test_inactive_user_cannot_authenticate(self):
        client = APIClient()
        email = unique_email("inactive")
        inactive = User.objects.create_user(
            username=f"disabled-{uuid.uuid4().hex[:8]}", email=email, password=PASSWORD
        )
        inactive.is_active = False
        inactive.save()
        response = headless_login(client, email=email)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["meta"]["is_authenticated"])


class CurrentUserEndpointTests(AuthTestBase):
    def test_unauthenticated_returns_401(self):
        self.assertEqual(self.client.get("/api/auth/user/").status_code, 401)

    def test_agent_key_is_not_a_dashboard_session(self):
        _agent, key = Agent.create_with_key("shopper", Organization.objects.create(name="acme"))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
        self.assertEqual(self.client.get("/api/auth/user/").status_code, 401)

    def test_authenticated_user_returns_profile(self):
        self._signup_and_verify()
        response = self.client.get("/api/auth/user/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["email"], self.email)
        self.assertTrue(body["is_email_verified"])
        self.assertEqual(body["memberships"], [])
        for field in ("password", "is_staff", "is_superuser", "last_login"):
            self.assertNotIn(field, body)

    def test_signup_does_not_grant_org_membership(self):
        self._signup_and_verify()
        self.assertFalse(OrgMembership.objects.filter(user=User.objects.get(email=self.email)).exists())


class LogoutTests(AuthTestBase):
    def setUp(self):
        super().setUp()
        self._signup_and_verify()

    def test_logout_clears_session(self):
        self.assertEqual(self.client.get("/api/auth/user/").status_code, 200)
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/auth/user/").status_code, 401)

    def test_headless_logout_clears_session(self):
        self.assertEqual(headless_current_user(self.client).status_code, 200)
        response = headless_logout(self.client)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["meta"]["is_authenticated"])
        self.assertEqual(headless_current_user(self.client).status_code, 401)


class CSRFTests(AuthTestBase):
    def setUp(self):
        super().setUp()
        self.user = self._signup_and_verify()

    def test_login_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            f"{HEADLESS_BASE}/auth/login",
            {"email": self.email, "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_login_with_csrf_token_succeeds(self):
        client = Client(enforce_csrf_checks=True)
        client.get(f"{HEADLESS_BASE}/config")
        token = client.cookies["csrftoken"].value
        response = client.post(
            f"{HEADLESS_BASE}/auth/login",
            {"email": self.email, "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["meta"]["is_authenticated"])

    def test_logout_without_csrf_token_is_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = headless_logout(client)
        self.assertEqual(response.status_code, 403)

    def test_headless_logout_requires_csrf(self):
        headless_login(self.client, email=self.email)
        client = APIClient(enforce_csrf_checks=True)
        client.cookies = self.client.cookies
        response = headless_logout(client)
        self.assertEqual(response.status_code, 403)

    def test_config_endpoint_sets_csrf_cookie(self):
        client = APIClient()
        response = client.get(f"{HEADLESS_BASE}/config")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)