"""AUTH-05B.7B: MFA authentication rate-limit regression tests.

Regression coverage for django-allauth's MFA login rate limiting.

The headless ``/auth/2fa/authenticate`` endpoint mounts allauth's MFA
``AuthenticateForm`` (``allauth/mfa/base/forms.py``).  Its ``clean_code`` calls
``check_rate_limit`` (``allauth/mfa/base/internal/flows.py``), which consumes the
allauth.account ``login_failed`` rate-limit bucket keyed per-user
(``mfa-auth-user-<pk>``) on *every* code submission and clears it on a
successful code via the callable it returns.

The MFA rate-limit threshold is derived deterministically from the installed
allauth configuration: the minimum rate amount across all ``login_failed``
clauses (since every clause must be satisfied).  Tests submit exactly
``threshold + 1`` invalid codes — no empirical probing loop — and fail closed
if MFA rate limiting is not active.  All cache state is isolated per test via
``cache.clear()`` and the TOTP clock is frozen to a single window so
rate-limit history never expires mid-test.
"""

import time
from http import HTTPStatus
from unittest.mock import patch

from allauth.account import app_settings as account_settings
from allauth.core.internal.ratelimit import parse_rates
from allauth.mfa import app_settings as mfa_settings
from django.core.cache import cache

from tests.test_auth_mfa_login_flow import _compute_totp, _pending_mfa_flow
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

# Safety bound: a sane MFA rate-limit threshold should never exceed this value.
# Guards against absurdly high configurations that would make tests impractically
# slow.  The allauth default (5 per-user) is well below this cap.
PROBE_CAP = 64


def _error_codes(response):
    """Return the list of failure ``code`` values in a headless error response."""
    return [error.get("code") for error in response.json().get("errors", [])]


class MFARateLimitTests(AuthTestBase):
    """End-to-end regression coverage for MFA login rate limiting."""

    def setUp(self):
        super().setUp()
        cache.clear()
        # Snap to the start of the current TOTP window so that an invalid code
        # (derived by perturbing the valid one) stays invalid for the whole test,
        # and so rate-limit history (keyed on ``time.time``) never expires
        # mid-test.
        self.base_time = (int(time.time()) // TOTP_PERIOD) * TOTP_PERIOD
        self.user = self._signup_and_verify()
        headless_logout(self.client)
        headless_login(self.client, email=self.email)
        self.client.post(MFA_REAUTHENTICATE, {"password": PASSWORD}, format="json")
        self.totp_secret = self._enroll_totp()
        headless_logout(self.client)

    def tearDown(self):
        # The MFA rate-limit buckets live in the shared LocMem cache and are NOT
        # rolled back with the database.  Failing to clear here leaks consumed
        # ``login_failed`` IP/user counters into subsequent test classes whose
        # setUp does not clear the cache, which can trip the shared IP-based
        # limit and produce spurious failures downstream.
        cache.clear()
        super().tearDown()

    # ------------------------------------------------------------------
    # Fixtures & helpers
    # ------------------------------------------------------------------
    def _enroll_totp(self):
        """Enroll a TOTP authenticator and return the plaintext secret."""
        response = self.client.get(TOTP_MANAGE)
        secret = response.json()["meta"]["secret"]
        # Freeze the clock across both code computation and the enrollment POST
        # so the server never validates against a rolled-over TOTP window.
        with patch("time.time", return_value=self.base_time):
            code = _compute_totp(secret)
            response = self.client.post(TOTP_MANAGE, {"code": code}, format="json")
        self.assertEqual(response.status_code, HTTPStatus.OK, response.json())
        return secret

    def _compute_totp_at(self, secret, frozen_time):
        """Compute the TOTP code that is valid at *frozen_time*."""
        with patch("time.time", return_value=frozen_time):
            return _compute_totp(secret)

    def _enter_mfa_stage(self):
        """Log out (if any) and re-establish the pending MFA challenge."""
        headless_logout(self.client)
        response = headless_login(self.client, email=self.email)
        self.assertEqual(response.status_code, HTTPStatus.UNAUTHORIZED, response.json())
        flow = _pending_mfa_flow(response)
        self.assertIsNotNone(flow, "expected a pending mfa_authenticate flow")
        self.assertTrue(flow["is_pending"])

    def _invalid_code_at(self, frozen_time):
        """A TOTP code that is provably invalid at *frozen_time* (tolerance=0)."""
        valid = self._compute_totp_at(self.totp_secret, frozen_time)
        return str((int(valid) - 1) % 10**6).zfill(6)

    def _submit_totp_at(self, code, frozen_time=None):
        """Submit *code* to the MFA authenticate endpoint."""
        if frozen_time is None:
            frozen_time = self.base_time
        with patch("time.time", return_value=frozen_time):
            return self.client.post(
                MFA_AUTHENTICATE, {"code": code}, format="json"
            )

    def _submit_invalid(self, frozen_time=None):
        """Submit a provably-invalid code (a failed MFA attempt)."""
        return self._submit_totp_at(
            self._invalid_code_at(frozen_time or self.base_time),
            frozen_time or self.base_time,
        )

    def _effective_rate_limit_threshold(self):
        """Return the effective MFA rate-limit threshold from allauth config.

        Both the IP-based and per-user clauses must be satisfied for an attempt
        to pass, so the minimum ``amount`` across all ``login_failed`` rate
        clauses is the effective limit.  Returns ``None`` when no
        ``login_failed`` rate limiting is configured at all.
        """
        rates = parse_rates(
            account_settings.RATE_LIMITS.get("login_failed")
        )
        if not rates:
            return None
        return min(rate.amount for rate in rates)

    def _probe_rate_limit(self):
        """Submit invalid MFA codes until rate-limited, using a deterministic threshold.

        The threshold is derived from the effective ``login_failed`` rate-limit
        policy rather than empirically probing.  Returns the full list of
        responses (each an ``incorrect_code`` failure except the final
        rate-limited one).  Fails the test rather than skipping when MFA rate
        limiting is not active.
        """
        cache.clear()
        self._enter_mfa_stage()
        threshold = self._effective_rate_limit_threshold()
        self.assertIsNotNone(
            threshold,
            "MFA rate limiting (login_failed) is not configured — "
            "mandatory MFA rate-limit protection must not be disabled",
        )
        self.assertLessEqual(
            threshold,
            PROBE_CAP,
            f"MFA rate-limit threshold ({threshold}) exceeds safety cap ({PROBE_CAP})",
        )
        responses = []
        # Submit `threshold` invalid codes — each must be rejected as
        # incorrect_code (the per-user and IP counters are below the limit).
        for _ in range(threshold):
            response = self._submit_invalid()
            responses.append(response)
        # The (threshold + 1)-th attempt must be rate-limited.
        response = self._submit_invalid()
        responses.append(response)
        self.assertIn(
            "too_many_login_attempts",
            _error_codes(response),
            f"MFA rate limiting must engage after {threshold} failed attempts, "
            f"but the {(threshold + 1)}-th attempt was not rate-limited",
        )
        return responses

    # ------------------------------------------------------------------
    # A. Repeated incorrect TOTP submissions eventually trigger rate limiting.
    # ------------------------------------------------------------------
    def test_repeated_incorrect_totp_triggers_rate_limit(self):
        responses = self._probe_rate_limit()
        codes_sequence = [_error_codes(response) for response in responses]
        # Non-rate-limited attempts precede the rate-limited one.
        self.assertIn(["incorrect_code"], codes_sequence)
        # The final attempt is the rate-limited one.
        self.assertIn("too_many_login_attempts", _error_codes(responses[-1]))

    # ------------------------------------------------------------------
    # B. The rate-limited response is distinguishable from an ordinary
    #    incorrect-code response.
    # ------------------------------------------------------------------
    def test_rate_limited_response_differs_from_incorrect_code(self):
        responses = self._probe_rate_limit()
        self.assertGreater(
            len(responses),
            1,
            "expected at least one non-rate-limited attempt to compare against",
        )
        incorrect = responses[0]
        rate_limited = responses[-1]
        incorrect_codes = _error_codes(incorrect)
        rate_limited_codes = _error_codes(rate_limited)

        self.assertEqual(incorrect_codes, ["incorrect_code"])
        self.assertEqual(rate_limited_codes, ["too_many_login_attempts"])
        self.assertNotEqual(
            incorrect_codes,
            rate_limited_codes,
            "rate-limited response must not masquerade as an incorrect code",
        )

        # Response contract: rate-limited MFA returns HTTP 400.
        self.assertEqual(
            rate_limited.status_code,
            HTTPStatus.BAD_REQUEST,
            "rate-limited MFA response must return HTTP 400",
        )
        # The user remains unauthenticated after a rate-limited attempt.
        self.assertEqual(
            self.client.get("/api/auth/user/").status_code,
            HTTPStatus.UNAUTHORIZED,
            "rate-limited MFA must not authenticate the user",
        )

    # ------------------------------------------------------------------
    # C. A fresh MFA challenge for the same user does not reset the
    #    rate-limit counter.
    # ------------------------------------------------------------------
    def test_fresh_mfa_challenge_does_not_reset_counter(self):
        responses = self._probe_rate_limit()
        allowed = len(responses) - 1
        self.assertGreater(allowed, 0)

        # The probe saturated the per-user counter.  Re-establishing the MFA
        # challenge (a fresh password login) must NOT clear it.
        self._enter_mfa_stage()
        response = self._submit_invalid()
        self.assertEqual(
            _error_codes(response),
            ["too_many_login_attempts"],
            "fresh MFA challenge must not reset the failed-attempt counter",
        )

    # ------------------------------------------------------------------
    # D. A successful authentication clears the failed-attempt counter.
    # ------------------------------------------------------------------
    def test_successful_authentication_clears_counter(self):
        responses = self._probe_rate_limit()
        allowed = len(responses) - 1
        self.assertGreater(allowed, 0)

        # Rebuild up to one short of the limit on a clean counter.
        cache.clear()
        self._enter_mfa_stage()
        for _ in range(allowed - 1):
            response = self._submit_invalid()
            self.assertEqual(_error_codes(response), ["incorrect_code"])

        # A valid code succeeds and clears the counter.
        valid_code = self._compute_totp_at(self.totp_secret, self.base_time)
        response = self._submit_totp_at(valid_code)
        self.assertEqual(response.status_code, HTTPStatus.OK, response.json())
        self.assertTrue(response.json()["meta"]["is_authenticated"])

        # Fresh MFA challenge: the counter should be empty, so the same number
        # of failures that would have tripped the limit now all fail softly.
        self._enter_mfa_stage()
        for _ in range(allowed):
            response = self._submit_invalid()
            self.assertNotIn(
                "too_many_login_attempts",
                _error_codes(response),
                "successful authentication should have cleared the failed-attempt counter",
            )
