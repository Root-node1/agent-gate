"""AUTH-02B: secure password reset, password change, and session security.

Covers the headless JSON contract:
  * POST /api/auth/headless/browser/v1/auth/password/request   (reset request)
  * POST /api/auth/headless/browser/v1/auth/password/reset      (reset confirm)
  * POST /api/auth/headless/browser/v1/account/password/change  (change password)

No custom endpoints or token tables are introduced; the flow delegates entirely
to django-allauth's headless implementation.
"""

import datetime
import re
from unittest.mock import patch
from urllib.parse import urlparse

from allauth.account.forms import default_token_generator
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrgMembership
from tests.test_auth_signup_login import (
    HEADLESS_BASE,
    PASSWORD,
    AuthTestBase,
    extract_verification_code,
    headless_login,
    headless_signup,
    headless_verify_email,
    unique_email,
)

User = get_user_model()

RESET_REQUEST = f"{HEADLESS_BASE}/auth/password/request"
RESET_CONFIRM = f"{HEADLESS_BASE}/auth/password/reset"
CHANGE_PASSWORD = f"{HEADLESS_BASE}/account/password/change"

# Reset link embedded in the password-reset email: <origin>/reset-password/<key>
KEY_RE = re.compile(r"/reset-password/([0-9A-Za-z-]+)")
# A headless verification code: AAAA-AAAA style upper alnum groups.
CODE_RE = re.compile(r"code[:\s]+([A-Z0-9]{4}-[A-Z0-9]{4})")


def _fresh_client():
    """Anonymous browser client with a CSRF cookie primed (like a real SPA)."""
    client = APIClient()
    client.get(f"{HEADLESS_BASE}/config")
    return client


def _signup_verified(email=None, password=PASSWORD, client=None):
    """Sign up then verify; returns the (client, user). Verifies sends a
    confirmation email, so the outbox is left clean for the recovery assertions."""
    client = client or _fresh_client()
    if email is None:
        email = unique_email()
    headless_signup(client, email=email, password=password)
    code = extract_verification_code()
    headless_verify_email(client, code)
    user = User.objects.get(email=email)
    mail.outbox.clear()
    return client, user


def _request_reset(client, email):
    return client.post(RESET_REQUEST, {"email": email}, format="json")


def _extract_reset_key():
    """Pull the reset key out of the last sent email body."""
    assert mail.outbox, "no email was sent"
    match = KEY_RE.search(mail.outbox[-1].body)
    assert match, f"reset link not found in email: {mail.outbox[-1].body!r}"
    return match.group(1)


def _confirm_reset(client, key, password="New!2345"):
    return client.post(
        RESET_CONFIRM, {"key": key, "password": password}, format="json"
    )


class RequestPasswordResetTests(AuthTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_reset_request_returns_200_and_sends_email(self):
        client, _ = _signup_verified(email=self.email)
        client = _fresh_client()  # anonymous requester
        response = _request_reset(client, self.email)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, [self.email])
        self.assertIn("Reset your AgentGate password", sent.subject)
        self.assertIn("expires in 1 hour", sent.body)

    def test_reset_link_points_to_spa(self):
        _signup_verified(email=self.email)
        client = _fresh_client()
        _request_reset(client, self.email)
        key = _extract_reset_key()
        self.assertTrue(key)  # link present
        # the full link uses the configured frontend origin + route
        link_match = re.search(
            r"(https?://[^/\s]+/reset-password/[0-9A-Za-z-]+)",
            mail.outbox[0].body,
        )
        self.assertIsNotNone(link_match)
        parsed = urlparse(link_match.group(1))
        self.assertEqual(parsed.netloc, "app.test")
        self.assertEqual(parsed.path, "/reset-password/" + key)

    def test_reset_request_for_unknown_email_is_indistinguishable(self):
        """Enumeration protection: an unknown address replies with the same 200 as a
        known address, with no error surfaced to the requester; it only receives
        the enumeration-resistant notice instead of a reset link."""
        client = _fresh_client()
        response = _request_reset(client, "does-not-exist@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("errors", response.json())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("password reset requested", mail.outbox[0].subject.lower())

    def test_reset_request_does_not_leak_account_existence(self):
        _signup_verified(email=self.email)
        client_known = _fresh_client()
        client_unknown = _fresh_client()
        resp_known = _request_reset(client_known, self.email)
        resp_unknown = _request_reset(client_unknown, "nope@example.com")
        self.assertEqual(resp_known.status_code, 200)
        self.assertEqual(resp_unknown.status_code, 200)
        self.assertNotIn("errors", resp_known.json())
        self.assertNotIn("errors", resp_unknown.json())


class ResetConfirmationTests(AuthTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client, self.user = _signup_verified(email=self.email)

    def _do_reset_request(self):
        self.client = _fresh_client()
        _request_reset(self.client, self.email)
        return _extract_reset_key()

    def test_successful_reset_confirmation_status_is_401(self):
        """The reset-confirm endpoint is an anonymous operation. allauth returns
        AuthenticationResponse(request) which resolves to 401 (no session) even on
        success. A 401 with no `errors` and meta.is_authenticated==False is a
        successful reset -- never treat it as a failure.

        (Verified empirically against allauth 65.21.0, NOT assumed.)"""
        key = self._do_reset_request()
        response = _confirm_reset(self.client, key)
        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertFalse(body["meta"]["is_authenticated"])
        self.assertNotIn("errors", body)
        self.assertIn("flows", body["data"])

    def test_successful_reset_changes_password(self):
        key = self._do_reset_request()
        _confirm_reset(self.client, key, password="New!2345")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New!2345"))

    def test_successful_reset_sends_notification(self):
        key = self._do_reset_request()
        _confirm_reset(self.client, key)
        subjects = [m.subject for m in mail.outbox]
        self.assertTrue(
            any("Your AgentGate password was reset" in s for s in subjects),
            subjects,
        )

    def test_reset_does_not_autologin(self):
        """LOGIN_ON_PASSWORD_RESET is False: the requester stays anonymous."""
        key = self._do_reset_request()
        _confirm_reset(self.client, key)
        self.assertEqual(self.client.get(f"{HEADLESS_BASE}/auth/session").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/user/").status_code, 401)

    def test_new_password_works_and_old_password_fails(self):
        key = self._do_reset_request()
        _confirm_reset(self.client, key, password="New!2345")
        login_old = headless_login(_fresh_client(), self.email, password=PASSWORD)
        self.assertEqual(login_old.status_code, 400)
        login_new = headless_login(_fresh_client(), self.email, password="New!2345")
        self.assertEqual(login_new.status_code, 200)

    def test_invalid_token_is_rejected(self):
        response = _confirm_reset(self.client, "not-a-valid-key", password="New!2345")
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())

    def test_reused_token_is_rejected(self):
        """Tokens are single-use: the password is embedded in the hash, so once
        the password changes the previously-issued token no longer validates."""
        key = self._do_reset_request()
        first = _confirm_reset(self.client, key, password="New!2345")
        self.assertNotIn("errors", first.json())
        second = _confirm_reset(self.client, key, password="Another!2345")
        self.assertEqual(second.status_code, 400)
        self.assertIn("errors", second.json())

    def test_expired_token_is_rejected(self):
        """A token older than PASSWORD_RESET_TIMEOUT (1h) is rejected."""
        key = self._do_reset_request()
        # Password is unchanged yet; bump the generator's view of "now" beyond
        # the 1-hour window so check_token marks the token expired.
        future = datetime.datetime.now() + datetime.timedelta(hours=2)
        with patch.object(default_token_generator, "_now", return_value=future):
            response = _confirm_reset(self.client, key, password="New!2345")
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())
        self.assertFalse(self.user.check_password("New!2345"))


class UnverifiedUserResetTests(AuthTestBase):
    """An unverified account must not be recoverable in a way that bypasses the
    mandatory email-verification gate."""

    def setUp(self):
        super().setUp()
        cache.clear()
        headless_signup(self.client, email=self.email, password=PASSWORD)
        self.user = User.objects.get(email=self.email)
        mail.outbox.clear()

    def test_unverified_user_reset_does_not_grant_login(self):
        _request_reset(_fresh_client(), self.email)
        key = _extract_reset_key()
        response = _confirm_reset(_fresh_client(), key, password="New!2345")
        # Reset succeeds (401 == success, anonymous) ...
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("errors", response.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New!2345"))
        # ... but the email is still unverified, so login stays blocked.
        Address = EmailAddress.objects.get(email=self.email)
        self.assertFalse(Address.verified)
        login = headless_login(_fresh_client(), self.email, password="New!2345")
        self.assertNotEqual(login.status_code, 200)


class ChangePasswordTests(AuthTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client, self.user = _signup_verified(email=self.email)

    def _change(self, current=PASSWORD, new="New!2345"):
        return self.client.post(
            CHANGE_PASSWORD,
            {"current_password": current, "new_password": new},
            format="json",
        )

    def test_change_password_succeeds_and_preserves_session(self):
        response = self._change()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["meta"]["is_authenticated"])
        # Current session stays valid (LOGOUT_ON_PASSWORD_CHANGE=False).
        self.assertEqual(self.client.get(f"{HEADLESS_BASE}/auth/session").status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New!2345"))

    def test_other_session_is_invalidated_after_change(self):
        """Django stores an auth-hash in every session keyed on the password.
        Changing the password invalidates every *other* session on its next
        request (lazy revocation, without allauth.usersessions)."""
        other = _fresh_client()
        headless_login(other, self.email, password=PASSWORD)
        self.assertEqual(other.get(f"{HEADLESS_BASE}/auth/session").status_code, 200)
        # Current session changes the password ...
        self._change()
        # ... and a different, already-open session is rejected on next use.
        self.assertEqual(other.get(f"{HEADLESS_BASE}/auth/session").status_code, 401)

    def test_change_notifies_user(self):
        self._change()
        subjects = [m.subject for m in mail.outbox]
        self.assertTrue(
            any("Your AgentGate password was changed" in s for s in subjects),
            subjects,
        )

    def test_wrong_current_password_rejected(self):
        response = self._change(current="wrong", new="New!2345")
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())

    def test_change_requires_authentication(self):
        anon = _fresh_client()
        response = anon.post(
            CHANGE_PASSWORD,
            {"current_password": PASSWORD, "new_password": "New!2345"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["meta"]["is_authenticated"])


class RateLimitTests(AuthTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_rate_limit_configuration_matches_auth03_requirement(self):
        """AUTH-03 acceptance: max 3 reset requests per hour per email,
        while retaining the IP-level cap for DoS resistance."""
        from django.conf import settings

        rate = settings.ACCOUNT_RATE_LIMITS.get("reset_password", "")
        self.assertIn("3/h/key", rate)
        self.assertIn("20/m/ip", rate)

    def test_reset_request_is_rate_limited_per_email(self):
        _signup_verified(email=self.email)
        client = _fresh_client()
        results = []
        for _ in range(6):
            results.append(_request_reset(client, self.email).status_code)
        # AUTH-03: 3/h/key — 3 succeed, 4th is rate-limited.
        self.assertEqual(results[:3], [200, 200, 200])
        self.assertEqual(results[3], 429)


class RecoveryCSRFTests(AuthTestBase):
    """CSRF enforcement on the headless recovery endpoints.
    The browser client must send X-CSRFToken on every POST (bootstrapped via
    GET /config); without it the middleware rejects with 403."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.client, self.user = _signup_verified(email=self.email)

    def test_reset_request_without_csrf_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.get(f"{HEADLESS_BASE}/config")
        response = client.post(
            RESET_REQUEST, {"email": self.email}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)

    def test_reset_request_with_csrf_succeeds(self):
        client = Client(enforce_csrf_checks=True)
        resp = client.get(f"{HEADLESS_BASE}/config")
        token = resp.cookies["csrftoken"].value
        response = client.post(
            RESET_REQUEST,
            {"email": self.email},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)

    def test_password_change_without_csrf_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get(f"{HEADLESS_BASE}/config")
        response = client.post(
            CHANGE_PASSWORD,
            {"current_password": PASSWORD, "new_password": "New!2345"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)


class RecoverySecurityTests(AuthTestBase):
    """Additional security invariants not covered by the existing test classes."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.client, self.user = _signup_verified(email=self.email)

    def test_weak_password_rejected_on_reset(self):
        """AUTH_PASSWORD_VALIDATORS are enforced on the reset-confirm endpoint."""
        client = _fresh_client()
        _request_reset(client, self.email)
        key = _extract_reset_key()
        response = _confirm_reset(client, key, password="password")
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password("password"))

    def test_reset_does_not_change_org_membership(self):
        """Recovery must never alter organization membership or roles."""
        org = Organization.objects.create(name="secure-org")
        membership = OrgMembership.objects.create(
            user=self.user, organization=org, role=OrgMembership.Role.ADMIN
        )
        client = _fresh_client()
        _request_reset(client, self.email)
        key = _extract_reset_key()
        _confirm_reset(client, key, password="New!2345")
        membership.refresh_from_db()
        self.assertEqual(membership.role, OrgMembership.Role.ADMIN)
        self.assertEqual(membership.organization, org)
        self.assertEqual(OrgMembership.objects.count(), 1)

    def test_reset_only_sends_notification_email(self):
        """After reset, only the 'password was reset' notification is sent,
        not a verification or second reset-key email."""
        client = _fresh_client()
        _request_reset(client, self.email)
        key = _extract_reset_key()
        mail.outbox.clear()
        _confirm_reset(client, key, password="New!2345")
        subjects = [m.subject for m in mail.outbox]
        self.assertEqual(len(subjects), 1)
        self.assertIn("password was reset", subjects[0])

    def test_unknown_email_receives_unknown_account_email(self):
        """An unknown email receives an enumeration-resistant notice, not a
        reset link, but the HTTP response is indistinguishable from a known
        email (200, no errors)."""
        client = _fresh_client()
        response = _request_reset(client, "never-registered@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("/reset-password/", mail.outbox[0].body)
        self.assertIn("password reset requested", mail.outbox[0].subject.lower())
