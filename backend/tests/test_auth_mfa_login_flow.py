"""AUTH-05B.2C: MFA Headless login flow end-to-end tests.

Verifies the native allauth MFA login flow over the Headless contract after
mounting ``allauth.mfa.urls`` at ``/mfa/`` to resolve the previously failing
``reverse("mfa_authenticate")`` (NoReverseMatch) during the MFA login stage.
"""

import time
from http import HTTPStatus

from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    format_hotp_value,
    generate_totp_secret,
    hotp_value,
    validate_totp_code,
)
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test.utils import override_settings
from rest_framework.test import APITestCase

from tests.test_auth_github_oauth import (
    GITHUB_TEST_PROVIDERS,
    GitHubOAuthTestMixin,
)
from tests.test_auth_signup_login import (
    HEADLESS_BASE,
    PASSWORD,
    AuthTestBase,
    headless_login,
    headless_logout,
    unique_email,
)

User = get_user_model()

MFA_AUTHENTICATE = f"{HEADLESS_BASE}/auth/2fa/authenticate"
MFA_REAUTHENTICATE = f"{HEADLESS_BASE}/auth/reauthenticate"
TOTP_MANAGE = f"{HEADLESS_BASE}/account/authenticators/totp"


def _pending_mfa_flow(response):
    flows = response.json()["data"]["flows"]
    return next((f for f in flows if f["id"] == "mfa_authenticate"), None)


def _error_codes(response):
    """Return the list of failure ``code`` values in a headless error response."""
    return [error.get("code") for error in response.json().get("errors", [])]


def _compute_totp(secret):
    counter = int(time.time()) // mfa_settings.TOTP_PERIOD
    code = format_hotp_value(hotp_value(secret, counter))
    if not validate_totp_code(secret, code):
        time.sleep(1)
        counter = int(time.time()) // mfa_settings.TOTP_PERIOD
        code = format_hotp_value(hotp_value(secret, counter))
    return code


class MFAHeadlessLoginFlowTests(AuthTestBase):
    """End-to-end MFA login flow over the Headless contract."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.user = self._signup_and_verify()
        headless_logout(self.client)
        headless_login(self.client, email=self.email)
        self.client.post(MFA_REAUTHENTICATE, {"password": PASSWORD}, format="json")
        self.totp_secret = self._enroll_totp()
        headless_logout(self.client)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _enroll_totp(self):
        response = self.client.get(TOTP_MANAGE)
        secret = response.json()["meta"]["secret"]
        code = _compute_totp(secret)
        response = self.client.post(TOTP_MANAGE, {"code": code}, format="json")
        self.assertEqual(response.status_code, HTTPStatus.OK)
        return secret

    def _unused_recovery_codes(self):
        rc_auth = Authenticator.objects.get(
            user=self.user, type=Authenticator.Type.RECOVERY_CODES
        )
        return rc_auth.wrap().get_unused_codes()

    def _enter_mfa_stage(self):
        headless_logout(self.client)
        response = headless_login(self.client, email=self.email)
        self.assertEqual(response.status_code, HTTPStatus.UNAUTHORIZED)
        self.assertFalse(response.json()["meta"]["is_authenticated"])
        flow = _pending_mfa_flow(response)
        self.assertIsNotNone(flow, "expected a pending mfa_authenticate flow")
        self.assertTrue(flow["is_pending"])

    def _submit_mfa_code(self, code):
        return self.client.post(MFA_AUTHENTICATE, {"code": code}, format="json")

    # ------------------------------------------------------------------
    # 1. Password login with an enrolled TOTP authenticator enters the
    #    pending MFA stage.
    # ------------------------------------------------------------------
    def test_password_login_enters_pending_mfa_stage(self):
        response = headless_login(self.client, email=self.email)

        self.assertEqual(response.status_code, HTTPStatus.UNAUTHORIZED)
        self.assertFalse(response.json()["meta"]["is_authenticated"])

        flow = _pending_mfa_flow(response)
        self.assertIsNotNone(flow, "expected a pending mfa_authenticate flow")
        self.assertTrue(flow["is_pending"])
        self.assertIn("totp", flow["types"])

    # ------------------------------------------------------------------
    # 2. Privileged access is unavailable before MFA completion.
    # ------------------------------------------------------------------
    def test_privileged_access_blocked_before_mfa(self):
        headless_login(self.client, email=self.email)

        for path in ("/api/auth/user/", "/v1/agents/"):
            self.assertEqual(
                self.client.get(path).status_code,
                HTTPStatus.UNAUTHORIZED,
                f"{path} should be 401 before MFA completes",
            )

    # ------------------------------------------------------------------
    # 3. Incorrect TOTP codes are rejected.
    # ------------------------------------------------------------------
    def test_incorrect_totp_rejected(self):
        headless_login(self.client, email=self.email)

        response = self.client.post(MFA_AUTHENTICATE, {"code": "000000"}, format="json")
        self.assertNotEqual(response.status_code, HTTPStatus.OK)

        # MFA has not completed; session remains unauthenticated.
        self.assertEqual(
            self.client.get("/api/auth/user/").status_code,
            HTTPStatus.UNAUTHORIZED,
        )

    # ------------------------------------------------------------------
    # 4. Correct TOTP completes authentication.
    # ------------------------------------------------------------------
    def test_correct_totp_completes_authentication(self):
        headless_login(self.client, email=self.email)

        response = self.client.post(
            MFA_AUTHENTICATE, {"code": _compute_totp(self.totp_secret)}, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTrue(response.json()["meta"]["is_authenticated"])
        self.assertEqual(self.client.get("/api/auth/user/").status_code, HTTPStatus.OK)

    # ------------------------------------------------------------------
    # 5. Recovery-code authentication works.
    # ------------------------------------------------------------------
    def test_recovery_code_authenticates(self):
        rc_auth = Authenticator.objects.get(
            user=self.user, type=Authenticator.Type.RECOVERY_CODES
        )
        code = rc_auth.wrap().get_unused_codes()[0]

        headless_login(self.client, email=self.email)

        response = self.client.post(MFA_AUTHENTICATE, {"code": code}, format="json")
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTrue(response.json()["meta"]["is_authenticated"])

    def test_consumed_recovery_code_cannot_be_reused(self):
        """AUTH-05B.7C: a recovery code consumed during MFA login is single-use.

        allauth persists recovery-code consumption via the authenticator's
        ``used_mask`` in the database (``RecoveryCodes._mark_code_used``).  This
        test exercises that contract end-to-end over the headless MFA
        authenticate endpoint and proves the same code cannot be replayed in a
        subsequent challenge.
        """
        codes = self._unused_recovery_codes()
        self.assertGreaterEqual(
            len(codes), 2, "need at least two unused recovery codes"
        )
        code = codes[0]
        other_code = codes[1]

        # (1) A fresh recovery code successfully completes an MFA login challenge.
        self._enter_mfa_stage()
        response = self._submit_mfa_code(code)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTrue(response.json()["meta"]["is_authenticated"])

        # Consumption is persisted in the DB (used_mask), not in the rate-limit
        # cache: re-querying reveals the code as consumed.
        self.assertNotIn(code, self._unused_recovery_codes())

        # (2) The same recovery code is rejected in a *new* MFA login challenge.
        self._enter_mfa_stage()

        # (3) Clear the shared rate-limit bucket so any rejection here can only
        #     stem from code consumption (DB persisted), not from rate limiting.
        #     Sessions are DB-backed, so the pending MFA challenge is untouched.
        cache.clear()
        response = self._submit_mfa_code(code)

        self.assertNotEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("incorrect_code", _error_codes(response))
        self.assertNotIn("too_many_login_attempts", _error_codes(response))
        self.assertNotEqual(response.status_code, HTTPStatus.TOO_MANY_REQUESTS)
        self.assertEqual(
            self.client.get("/api/auth/user/").status_code,
            HTTPStatus.UNAUTHORIZED,
            "replaying a consumed recovery code must not authenticate the user",
        )

        # (4) Another (still unused) recovery code remains valid.
        self._enter_mfa_stage()
        response = self._submit_mfa_code(other_code)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTrue(response.json()["meta"]["is_authenticated"])


@override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_TEST_PROVIDERS)
class OAuthMFAStageTests(GitHubOAuthTestMixin, APITestCase):
    """6. GitHub OAuth login with an enrolled authenticator follows the MFA stage."""

    def test_github_login_with_totp_enters_mfa_stage(self):
        email = unique_email("mfa")

        # First OAuth login creates the user and authenticates immediately (no MFA).
        state_id = self._start_redirect()
        self._callback_with_github(state_id, email=email, verified=True)
        self.assertEqual(
            self.client.get(f"{HEADLESS_BASE}/auth/session").json()["meta"][
                "is_authenticated"
            ],
            True,
        )

        # OAuth users have no usable password, so enroll the TOTP authenticator
        # directly (the headless MFA API is otherwise gated behind password
        # reauthentication). This emulates a fully provisioned MFA account.
        user = User.objects.get(email=email)
        secret = generate_totp_secret()
        adapter = get_mfa_adapter()
        Authenticator.objects.create(
            user=user,
            type=Authenticator.Type.TOTP,
            data={"secret": adapter.encrypt(secret)},
        )
        headless_logout(self.client)

        # Second OAuth login: the user now has MFA, so the login must be held
        # at the pending MFA stage rather than completing the session.
        state_id2 = self._start_redirect()
        response = self._callback_with_github(state_id2, email=email, verified=True)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        sess = self.client.get(f"{HEADLESS_BASE}/auth/session")
        self.assertEqual(sess.status_code, HTTPStatus.UNAUTHORIZED)
        meta = sess.json()["meta"]
        self.assertFalse(meta["is_authenticated"])

        flow = _pending_mfa_flow(sess)
        self.assertIsNotNone(flow)
        self.assertTrue(flow["is_pending"])
        self.assertIn("totp", flow["types"])
