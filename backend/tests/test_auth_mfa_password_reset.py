"""AUTH-05B.8B: Password reset + MFA continuity tests.

Verifies that a password reset does not remove or bypass an existing TOTP
authenticator.  The nine approved assertions:

  A. An existing user enrolls and activates TOTP.                     [setUp]
  B. The user completes the normal password-reset flow.
  C. The existing TOTP Authenticator record remains enrolled after reset.
  D. The old password is rejected.
  E. The new password is accepted but does NOT immediately establish a session.
  F. The login enters the pending mfa_authenticate stage.
  G. GET /api/auth/user/ returns 401 before MFA completion.
  H. Submitting a valid TOTP code completes authentication.
  I. GET /api/auth/user/ returns 200 after MFA completion.
"""
from http import HTTPStatus

from allauth.mfa.models import Authenticator
from django.core import mail
from django.core.cache import cache

from tests.test_auth_mfa_login_flow import (
    MFA_AUTHENTICATE,
    MFA_REAUTHENTICATE,
    TOTP_MANAGE,
    _compute_totp,
    _pending_mfa_flow,
)
from tests.test_auth_password_reset import (
    _confirm_reset,
    _extract_reset_key,
    _fresh_client,
    _request_reset,
)
from tests.test_auth_signup_login import (
    PASSWORD,
    AuthTestBase,
    headless_login,
    headless_logout,
)

NEW_PASSWORD = "New!2345"


class PasswordResetMFAContinuityTests(AuthTestBase):
    """A password reset must not invalidate an existing TOTP authenticator."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.user = self._signup_and_verify()
        headless_logout(self.client)
        headless_login(self.client, email=self.email)
        self.client.post(
            MFA_REAUTHENTICATE, {"password": PASSWORD}, format="json"
        )
        self.totp_secret = self._enroll_totp()
        mail.outbox.clear()
        headless_logout(self.client)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    # -- helpers --------------------------------------------------------

    def _enroll_totp(self):
        response = self.client.get(TOTP_MANAGE)
        secret = response.json()["meta"]["secret"]
        code = _compute_totp(secret)
        response = self.client.post(
            TOTP_MANAGE, {"code": code}, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        # Assertion A: the TOTP authenticator is active in the DB.
        self.assertTrue(
            Authenticator.objects.filter(
                user=self.user, type=Authenticator.Type.TOTP
            ).exists(),
            "TOTP authenticator must be enrolled after activation",
        )
        return secret

    def _perform_password_reset(self):
        """B. Complete the normal password-reset flow with a fresh anonymous client."""
        client = _fresh_client()
        _request_reset(client, self.email)
        key = _extract_reset_key()
        response = _confirm_reset(client, key, password=NEW_PASSWORD)
        return response

    # ------------------------------------------------------------------
    # B + C
    # ------------------------------------------------------------------
    def test_password_reset_completes_and_totp_persists(self):
        response = self._perform_password_reset()

        # B. The reset-confirm endpoint returns 401 (anonymous success per
        #    allauth with LOGIN_ON_EMAIL_CONFIRMATION=False).  No errors and
        #    is_authenticated==False is the success signal.
        body = response.json()
        self.assertFalse(body["meta"]["is_authenticated"])
        self.assertNotIn("errors", body)

        # C. The existing TOTP Authenticator record remains enrolled and active.
        auth = Authenticator.objects.get(
            user=self.user, type=Authenticator.Type.TOTP
        )
        wrapped = auth.wrap()
        self.assertTrue(
            wrapped.validate_code(_compute_totp(self.totp_secret)),
            "TOTP authenticator must remain active after password reset",
        )

    # ------------------------------------------------------------------
    # D
    # ------------------------------------------------------------------
    def test_old_password_rejected_after_reset(self):
        self._perform_password_reset()

        # D. The old password is rejected (400 = invalid credentials).
        login_old = headless_login(
            _fresh_client(), self.email, password=PASSWORD
        )
        self.assertEqual(login_old.status_code, HTTPStatus.BAD_REQUEST)

    # ------------------------------------------------------------------
    # E + F + G + H + I
    # ------------------------------------------------------------------
    def test_new_password_login_flow_completes_mfa_after_reset(self):
        self._perform_password_reset()

        # Confirm the password was actually changed in the DB.
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(PASSWORD))
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

        # E + F. The new password is accepted (not 400) but does not
        #      establish a session; login enters the pending MFA stage.
        client = _fresh_client()
        login_resp = headless_login(
            client, self.email, password=NEW_PASSWORD
        )
        self.assertNotEqual(
            login_resp.status_code,
            HTTPStatus.BAD_REQUEST,
            "new password should be accepted, not rejected as invalid",
        )
        self.assertEqual(login_resp.status_code, HTTPStatus.UNAUTHORIZED)
        self.assertFalse(login_resp.json()["meta"]["is_authenticated"])

        flow = _pending_mfa_flow(login_resp)
        self.assertIsNotNone(flow, "expected a pending mfa_authenticate flow")
        self.assertTrue(flow["is_pending"])
        self.assertIn("totp", flow["types"])

        # G. GET /api/auth/user/ returns 401 before MFA completion.
        self.assertEqual(
            client.get("/api/auth/user/").status_code,
            HTTPStatus.UNAUTHORIZED,
        )

        # H. Submitting a valid TOTP code completes authentication.
        mfa_resp = client.post(
            MFA_AUTHENTICATE,
            {"code": _compute_totp(self.totp_secret)},
            format="json",
        )
        self.assertEqual(mfa_resp.status_code, HTTPStatus.OK)
        self.assertTrue(mfa_resp.json()["meta"]["is_authenticated"])

        # I. GET /api/auth/user/ returns 200 after MFA completion.
        self.assertEqual(
            client.get("/api/auth/user/").status_code,
            HTTPStatus.OK,
        )
