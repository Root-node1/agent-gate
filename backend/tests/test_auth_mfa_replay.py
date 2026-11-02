"""AUTH-05B.7A: TOTP replay regression tests.

Proves that a valid TOTP code cannot be reused during its validity window.
Tests allauth's built-in cache-backed used-code tracking
(``TOTP._mark_code_used`` via ``cache.add``) through the headless MFA
authentication flow.  No custom replay-logic is introduced; this suite is
strictly test-only.
"""

import time
from http import HTTPStatus
from unittest.mock import patch

from allauth.core.internal.cryptokit import normalize_user_code
from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, validate_totp_code
from django.core.cache import cache

from tests.test_auth_mfa_login_flow import (
    _compute_totp,
    _pending_mfa_flow,
)
from tests.test_auth_signup_login import (
    HEADLESS_BASE,
    PASSWORD,
    AuthTestBase,
    headless_login,
    headless_logout,
)

MFA_AUTHENTICATE = f"{HEADLESS_BASE}/auth/2fa/authenticate"
MFA_REAUTHENTICATE = f"{HEADLESS_BASE}/auth/reauthenticate"
TOTP_MANAGE = f"{HEADLESS_BASE}/account/authenticators/totp"

TOTP_PERIOD = mfa_settings.TOTP_PERIOD


class TOTPReplayTests(AuthTestBase):
    """Prove TOTP codes cannot be replayed within their validity window."""

    def setUp(self):
        super().setUp()
        cache.clear()
        # Snap to the start of the current TOTP window for deterministic
        # time control.  All code computation and validation in these tests
        # uses this frozen instant.
        self.base_time = (int(time.time()) // TOTP_PERIOD) * TOTP_PERIOD
        self.next_window_time = self.base_time + TOTP_PERIOD
        self.user = self._signup_and_verify()
        headless_logout(self.client)
        headless_login(self.client, email=self.email)
        self.client.post(MFA_REAUTHENTICATE, {"password": PASSWORD}, format="json")
        self.totp_secret = self._enroll_totp()
        headless_logout(self.client)

    def _enroll_totp(self):
        """Enroll a TOTP authenticator and return the plaintext secret."""
        response = self.client.get(TOTP_MANAGE)
        secret = response.json()["meta"]["secret"]
        with patch("time.time", return_value=self.base_time):
            code = _compute_totp(secret)
            response = self.client.post(TOTP_MANAGE, {"code": code}, format="json")
        assert response.status_code == HTTPStatus.OK, response.json()
        return secret

    def _enter_mfa_stage(self):
        """Password-login and assert the MFA challenge is pending."""
        response = headless_login(self.client, email=self.email)
        self.assertEqual(response.status_code, HTTPStatus.UNAUTHORIZED)
        self.assertFalse(response.json()["meta"]["is_authenticated"])
        self.assertIsNotNone(_pending_mfa_flow(response), "MFA stage should be pending")

    def _compute_totp_at(self, secret, frozen_time):
        """Compute a TOTP code as if *frozen_time* were the wall clock."""
        with patch("time.time", return_value=frozen_time):
            return _compute_totp(secret)

    def _submit_totp_at(self, code, frozen_time=None):
        """Submit *code* to the MFA authenticate endpoint.

        When *frozen_time* is given, ``time.time`` is patched for the duration
        of the request so that allauth validates against the same TOTP window
        the code was computed for.
        """
        if frozen_time is not None:
            with patch("time.time", return_value=frozen_time):
                return self.client.post(
                    MFA_AUTHENTICATE, {"code": code}, format="json"
                )
        return self.client.post(
            MFA_AUTHENTICATE, {"code": code}, format="json"
        )

    # ------------------------------------------------------------------
    # 1. First submission of a valid TOTP code succeeds.
    # ------------------------------------------------------------------
    def test_first_totp_submission_succeeds(self):
        self._enter_mfa_stage()
        code = self._compute_totp_at(self.totp_secret, self.base_time)
        response = self._submit_totp_at(code, frozen_time=self.base_time)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTrue(response.json()["meta"]["is_authenticated"])

    # ------------------------------------------------------------------
    # 2. Reusing the same code in a fresh MFA challenge within the same
    #    TOTP window fails.
    # ------------------------------------------------------------------
    def test_replayed_totp_within_same_window_fails(self):
        self._enter_mfa_stage()
        code = self._compute_totp_at(self.totp_secret, self.base_time)
        response = self._submit_totp_at(code, frozen_time=self.base_time)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTrue(response.json()["meta"]["is_authenticated"])

        # Fresh MFA challenge — logout then password-login again.
        headless_logout(self.client)
        self._enter_mfa_stage()

        # Same code, same window — must be rejected.
        response = self._submit_totp_at(code, frozen_time=self.base_time)
        self.assertNotEqual(response.status_code, HTTPStatus.OK)
        # Re-authentication with a replay does not complete MFA.
        self.assertEqual(
            self.client.get("/api/auth/user/").status_code,
            HTTPStatus.UNAUTHORIZED,
        )

    # ------------------------------------------------------------------
    # 3. Replay rejection is caused by used-code tracking, not an expired
    #    code, missing challenge, or unrelated rate limit.
    # ------------------------------------------------------------------
    def test_replay_rejection_is_from_used_code_tracking(self):
        self._enter_mfa_stage()
        code = self._compute_totp_at(self.totp_secret, self.base_time)
        self._submit_totp_at(code, frozen_time=self.base_time)

        # Start a fresh MFA challenge.
        headless_logout(self.client)
        self._enter_mfa_stage()

        with patch("time.time", return_value=self.base_time):
            # (a) The code is still valid for this window — NOT expired.
            self.assertTrue(validate_totp_code(self.totp_secret, code))

            # (b) Replay via the API is rejected.
            response = self._submit_totp_at(code)

            # (c) TOTP.validate_code returns False specifically because
            #     _mark_code_used() found the cache entry already present.
            totp_auth = Authenticator.objects.get(
                user=self.user, type=Authenticator.Type.TOTP
            )
            totp = totp_auth.wrap()
            self.assertIsInstance(totp, TOTP)
            self.assertFalse(totp.validate_code(code))

            # (d) The used-code cache entry exists — this is the mechanism
            #     that causes the rejection, not the database, not a
            #     rate-limit, not a missing challenge.
            cache_key = (
                f"allauth.mfa.totp.used"
                f"?user={self.user.pk}"
                f"&code={normalize_user_code(code)}"
            )
            self.assertIsNotNone(cache.get(cache_key))

        # (e) The HTTP response carries "incorrect_code", not
        #     "too_many_login_attempts" (rate-limited).
        self.assertNotEqual(response.status_code, HTTPStatus.OK)
        self.assertNotEqual(
            response.status_code, HTTPStatus.TOO_MANY_REQUESTS,
            "replay should not trigger rate-limiting",
        )
        errors = response.json().get("errors", [])
        error_codes = [e.get("code") for e in errors]
        self.assertIn("incorrect_code", error_codes)
        self.assertNotIn("too_many_login_attempts", error_codes)

    # ------------------------------------------------------------------
    # 4. A different valid code in a subsequent time window succeeds.
    # ------------------------------------------------------------------
    def test_different_code_in_next_time_window_succeeds(self):
        self._enter_mfa_stage()
        code1 = self._compute_totp_at(self.totp_secret, self.base_time)
        response = self._submit_totp_at(code1, frozen_time=self.base_time)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTrue(response.json()["meta"]["is_authenticated"])

        # Fresh MFA challenge.
        headless_logout(self.client)
        self._enter_mfa_stage()

        # Advance to the next TOTP window and compute a *different* code.
        code2 = self._compute_totp_at(self.totp_secret, self.next_window_time)
        self.assertNotEqual(code1, code2, "expected a different code in the next window")

        response = self._submit_totp_at(code2, frozen_time=self.next_window_time)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTrue(response.json()["meta"]["is_authenticated"])
