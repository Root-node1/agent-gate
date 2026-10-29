"""AUTH-05B.9C.3: MFA security event emission tests.

Verifies that allauth MFA signal handlers emit the correct security events
on the ``agentgate.security`` logger with the expected JSON payload fields
and log levels.

Signal-to-event mapping covered:
    authenticator_added      →  mfa.totp_activated                (WARNING)
    authenticator_removed    →  mfa.authenticator_removed          (WARNING)
    authenticator_reset      →  mfa.recovery_codes_regenerated     (WARNING)
    authenticator_used       →  mfa.challenge_succeeded            (INFO, reauthentication=True/False)
    authenticator_used       →  mfa.recovery_code_used             (WARNING, reauthentication=True/False)
    authentication_failed    →  mfa.challenge_failed               (WARNING, reauthentication=True/False)
"""

import json
import time
from http import HTTPStatus
from unittest.mock import patch

from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    format_hotp_value,
    hotp_value,
    validate_totp_code,
)
from django.core.cache import cache

from tests.test_auth_signup_login import (
    HEADLESS_BASE,
    PASSWORD,
    AuthTestBase,
    headless_login,
    headless_logout,
)

ACCOUNT_REAUTHENTICATE = f"{HEADLESS_BASE}/auth/reauthenticate"
MFA_AUTHENTICATE = f"{HEADLESS_BASE}/auth/2fa/authenticate"
MFA_REAUTHENTICATE = f"{HEADLESS_BASE}/auth/2fa/reauthenticate"
TOTP_MANAGE = f"{HEADLESS_BASE}/account/authenticators/totp"
RECOVERY_CODES_URL = f"{HEADLESS_BASE}/account/authenticators/recovery-codes"

_ALLOWED_FIELDS = frozenset(
    {
        "event",
        "user_id",
        "authenticator_type",
        "authenticator_id",
        "reauthentication",
    }
)


class MFAEntryPointBase(AuthTestBase):
    """Shared setup and helpers for MFA security-event tests."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.user = self._signup_and_verify()

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _login_and_password_reauth(self):
        headless_logout(self.client)
        headless_login(self.client, email=self.email)
        self.client.post(
            ACCOUNT_REAUTHENTICATE, {"password": PASSWORD}, format="json"
        )

    def _compute_valid_totp(self, secret):
        counter = int(time.time()) // mfa_settings.TOTP_PERIOD
        code = format_hotp_value(hotp_value(secret, counter))
        if not validate_totp_code(secret, code):
            time.sleep(1)
            counter = int(time.time()) // mfa_settings.TOTP_PERIOD
            code = format_hotp_value(hotp_value(secret, counter))
        return code

    def _enroll_totp(self):
        response = self.client.get(TOTP_MANAGE)
        secret = response.json()["meta"]["secret"]
        code = self._compute_valid_totp(secret)
        response = self.client.post(TOTP_MANAGE, {"code": code}, format="json")
        assert response.status_code == HTTPStatus.OK
        return secret

    def _enter_mfa_stage(self):
        headless_logout(self.client)
        response = headless_login(self.client, email=self.email)
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def _complete_mfa_login(self, secret):
        self._enter_mfa_stage()
        code = self._compute_valid_totp(secret)
        response = self.client.post(
            MFA_AUTHENTICATE, {"code": code}, format="json"
        )
        assert response.status_code == HTTPStatus.OK

    @staticmethod
    def _parse_events(captured):
        return [json.loads(r.getMessage()) for r in captured.records]


class MFAOnCommitSignalTests(MFAEntryPointBase):
    """Signals sent via transaction.on_commit.

    In Django's TestCase, on_commit callbacks are deferred and never
    execute.  We use captureOnCommitCallbacks(execute=True) to force
    them, and patch send_notification_mail because the MFA email
    templates are not shipped in this repo.
    """

    # --- authenticator_added → mfa.totp_activated -----------------------
    def test_totp_enrollment_emits_totp_activated(self):
        self._login_and_password_reauth()

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            with patch(
                "allauth.account.adapter.DefaultAccountAdapter"
                ".send_notification_mail"
            ):
                with self.captureOnCommitCallbacks(execute=True):
                    self._enroll_totp()

        events = self._parse_events(captured)
        totp_events = [e for e in events if e["event"] == "mfa.totp_activated"]
        self.assertEqual(len(totp_events), 1)

        ev = totp_events[0]
        self.assertEqual(ev["user_id"], str(self.user.id))
        self.assertEqual(ev["authenticator_type"], "totp")
        self.assertIsInstance(ev["authenticator_id"], int)
        self.assertNotIn("reauthentication", ev)
        self.assertTrue(
            set(ev.keys()).issubset(_ALLOWED_FIELDS),
            f"unexpected fields: {set(ev.keys()) - _ALLOWED_FIELDS}",
        )
        for rec in captured.records:
            if ev["event"] in rec.getMessage():
                self.assertEqual(rec.levelname, "WARNING")

    # --- Recovery-code auth_added is skipped (no duplicate event) -------
    def test_recovery_code_addition_does_not_emit_totp_activated(self):
        """During TOTP enrollment, recovery-code auth_added is silently
        skipped — only one mfa.totp_activated event is emitted."""
        self._login_and_password_reauth()

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            with patch(
                "allauth.account.adapter.DefaultAccountAdapter"
                ".send_notification_mail"
            ):
                with self.captureOnCommitCallbacks(execute=True):
                    self._enroll_totp()

        events = self._parse_events(captured)
        totp_events = [e for e in events if e["event"] == "mfa.totp_activated"]
        self.assertEqual(len(totp_events), 1)
        self.assertEqual(totp_events[0]["authenticator_type"], "totp")

    # --- authenticator_reset → mfa.recovery_codes_regenerated ----------
    def test_recovery_code_regeneration_emits_reset_event(self):
        self._login_and_password_reauth()
        self._enroll_totp()

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            with patch(
                "allauth.account.adapter.DefaultAccountAdapter"
                ".send_notification_mail"
            ):
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(RECOVERY_CODES_URL, format="json")
                    self.assertEqual(response.status_code, HTTPStatus.OK)

        events = self._parse_events(captured)
        resets = [
            e
            for e in events
            if e["event"] == "mfa.recovery_codes_regenerated"
        ]
        self.assertEqual(len(resets), 1)

        ev = resets[0]
        self.assertEqual(ev["user_id"], str(self.user.id))
        self.assertEqual(ev["authenticator_type"], "recovery_codes")
        self.assertIsInstance(ev["authenticator_id"], int)
        for rec in captured.records:
            if ev["event"] in rec.getMessage():
                self.assertEqual(rec.levelname, "WARNING")

    def test_payloads_contain_only_allowlisted_fields(self):
        """Event payloads must not leak secrets, codes, or PII."""
        self._login_and_password_reauth()
        self._enroll_totp()

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            with patch(
                "allauth.account.adapter.DefaultAccountAdapter"
                ".send_notification_mail"
            ):
                with self.captureOnCommitCallbacks(execute=True):
                    self.client.post(RECOVERY_CODES_URL, format="json")

        for payload in self._parse_events(captured):
            self.assertTrue(
                set(payload.keys()).issubset(_ALLOWED_FIELDS),
                f"unexpected fields: "
                f"{set(payload.keys()) - _ALLOWED_FIELDS}",
            )
            self.assertNotIn("secret", payload)
            self.assertNotIn("code", payload)


class MFAChallengeEventTests(MFAEntryPointBase):
    """Signals sent directly (not via on_commit).

    authenticator_used, authentication_failed, and
    authenticator_removed signals fire synchronously during the request,
    so no captureOnCommitCallbacks is needed.
    """

    # --- MFA login success → mfa.challenge_succeeded (INFO) --------------
    def test_mfa_login_success_emits_challenge_succeeded(self):
        self._login_and_password_reauth()
        secret = self._enroll_totp()

        self._enter_mfa_stage()
        code = self._compute_valid_totp(secret)

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            response = self.client.post(
                MFA_AUTHENTICATE, {"code": code}, format="json"
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTrue(response.json()["meta"]["is_authenticated"])

        events = self._parse_events(captured)
        succeeded = [
            e for e in events if e["event"] == "mfa.challenge_succeeded"
        ]
        self.assertEqual(len(succeeded), 1)
        ev = succeeded[0]
        self.assertEqual(ev["user_id"], str(self.user.id))
        self.assertEqual(ev["authenticator_type"], "totp")
        self.assertIn("reauthentication", ev)
        self.assertFalse(ev["reauthentication"])
        for rec in captured.records:
            if ev["event"] in rec.getMessage():
                self.assertEqual(rec.levelname, "INFO")

    # --- MFA login failure → mfa.challenge_failed (WARNING) ---------------
    def test_mfa_login_failure_emits_challenge_failed(self):
        self._login_and_password_reauth()
        self._enroll_totp()

        self._enter_mfa_stage()

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            response = self.client.post(
                MFA_AUTHENTICATE, {"code": "000000"}, format="json"
            )
            self.assertNotEqual(response.status_code, HTTPStatus.OK)

        events = self._parse_events(captured)
        failed = [e for e in events if e["event"] == "mfa.challenge_failed"]
        self.assertEqual(len(failed), 1)
        ev = failed[0]
        self.assertEqual(ev["user_id"], str(self.user.id))
        self.assertIn("reauthentication", ev)
        self.assertFalse(ev["reauthentication"])
        for rec in captured.records:
            if ev["event"] in rec.getMessage():
                self.assertEqual(rec.levelname, "WARNING")

    # --- Recovery-code MFA login → mfa.recovery_code_used (WARNING) ------
    def test_recovery_code_login_emits_recovery_code_used(self):
        self._login_and_password_reauth()
        self._enroll_totp()

        rc_auth = Authenticator.objects.get(
            user=self.user, type=Authenticator.Type.RECOVERY_CODES
        )
        code = rc_auth.wrap().get_unused_codes()[0]

        self._enter_mfa_stage()

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            response = self.client.post(
                MFA_AUTHENTICATE, {"code": code}, format="json"
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTrue(response.json()["meta"]["is_authenticated"])

        events = self._parse_events(captured)
        rc_events = [
            e for e in events if e["event"] == "mfa.recovery_code_used"
        ]
        self.assertEqual(len(rc_events), 1)
        ev = rc_events[0]
        self.assertEqual(ev["authenticator_type"], "recovery_codes")
        self.assertIn("reauthentication", ev)
        self.assertFalse(ev["reauthentication"])
        for rec in captured.records:
            if ev["event"] in rec.getMessage():
                self.assertEqual(rec.levelname, "WARNING")

    # --- MFA reauth success → challenge_succeeded (reauthentication=True) --
    def test_mfa_reauth_success_emits_reauthentication_true(self):
        self._login_and_password_reauth()
        secret = self._enroll_totp()
        self._complete_mfa_login(secret)

        # TOTP codes are single-use per time-window; clear the used-code cache
        # so a fresh code from the same secret/time-window is accepted.
        cache.clear()
        code = self._compute_valid_totp(secret)

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            response = self.client.post(
                MFA_REAUTHENTICATE, {"code": code}, format="json"
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)

        events = self._parse_events(captured)
        succeeded = [
            e for e in events if e["event"] == "mfa.challenge_succeeded"
        ]
        self.assertEqual(len(succeeded), 1)
        ev = succeeded[0]
        self.assertTrue(ev["reauthentication"])
        for rec in captured.records:
            if ev["event"] in rec.getMessage():
                self.assertEqual(rec.levelname, "INFO")

    # --- MFA reauth failure → challenge_failed (reauthentication=True) -----
    def test_mfa_reauth_failure_emits_reauthentication_true(self):
        self._login_and_password_reauth()
        secret = self._enroll_totp()
        self._complete_mfa_login(secret)

        cache.clear()

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            response = self.client.post(
                MFA_REAUTHENTICATE, {"code": "000000"}, format="json"
            )
            self.assertNotEqual(response.status_code, HTTPStatus.OK)

        events = self._parse_events(captured)
        failed = [
            e for e in events if e["event"] == "mfa.challenge_failed"
        ]
        self.assertEqual(len(failed), 1)
        ev = failed[0]
        self.assertTrue(ev["reauthentication"])
        for rec in captured.records:
            if ev["event"] in rec.getMessage():
                self.assertEqual(rec.levelname, "WARNING")


class MFAAuthenticatorRemovedTests(MFAEntryPointBase):
    """authenticator_removed is sent directly by delete_and_cleanup.

    deactivate_totp also sends a notification email (which requires
    allauth email templates not shipped here), so we patch the adapter.
    """

    _PATCH = patch(
        "allauth.account.adapter.DefaultAccountAdapter"
        ".send_notification_mail"
    )

    def test_totp_deactivation_emits_authenticator_removed(self):
        self._login_and_password_reauth()
        self._enroll_totp()

        totp_auth = Authenticator.objects.get(
            user=self.user, type=Authenticator.Type.TOTP
        )
        totp_auth_id = totp_auth.id
        self.assertIsNotNone(totp_auth_id)

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            with self._PATCH:
                response = self.client.delete(TOTP_MANAGE)
                self.assertEqual(response.status_code, HTTPStatus.OK)

        events = self._parse_events(captured)
        removed = [
            e for e in events if e["event"] == "mfa.authenticator_removed"
        ]
        totp_removed = [
            e for e in removed if e["authenticator_type"] == "totp"
        ]
        self.assertEqual(len(totp_removed), 1)
        ev = totp_removed[0]
        self.assertEqual(ev["user_id"], str(self.user.id))
        # Django clears pk on delete(), so authenticator_id is None in the
        # event payload — this is expected for authenticator_removed.
        self.assertIn("authenticator_id", ev)
        for rec in captured.records:
            if ev["event"] in rec.getMessage():
                self.assertEqual(rec.levelname, "WARNING")

    def test_recovery_codes_not_duplicated_on_totp_removal(self):
        """TOTP deactivation also removes the dangling recovery-codes auth."""
        self._login_and_password_reauth()
        self._enroll_totp()

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            with self._PATCH:
                self.client.delete(TOTP_MANAGE)

        events = self._parse_events(captured)
        removed = [
            e for e in events if e["event"] == "mfa.authenticator_removed"
        ]
        # TOTP removal triggers authenticator_removed for both TOTP and
        # the dangling recovery-codes authenticator.
        types = {e["authenticator_type"] for e in removed}
        self.assertIn("totp", types)
        self.assertIn("recovery_codes", types)
        self.assertEqual(len(removed), 2)


class MFAFailureIsolationTests(MFAEntryPointBase):
    """AUTH-05B.9C.3B — failure isolation gaps.

    A. Logging failure during successful MFA authentication does not
    block authentication.
    B. Logging failure during failed MFA verification preserves the
    expected error response (no HTTP 500).
    C. Unexpected authenticator metadata does not crash the MFA request.
    """

    def test_logging_failure_does_not_block_mfa_success(self):
        """If the security logger raises, MFA login still returns 200."""
        self._login_and_password_reauth()
        secret = self._enroll_totp()
        self._enter_mfa_stage()
        code = self._compute_valid_totp(secret)

        with patch("apps.accounts.signals._logger") as mock_logger:
            mock_logger.info.side_effect = Exception("simulated logger failure")
            response = self.client.post(
                MFA_AUTHENTICATE, {"code": code}, format="json"
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_logging_failure_does_not_block_mfa_failure_response(self):
        """If the security logger raises during MFA failure, the error
        response is preserved (no 500)."""
        self._login_and_password_reauth()
        self._enroll_totp()
        self._enter_mfa_stage()

        with patch("apps.accounts.signals._logger") as mock_logger:
            mock_logger.warning.side_effect = Exception("simulated logger failure")
            response = self.client.post(
                MFA_AUTHENTICATE, {"code": "000000"}, format="json"
            )
            self.assertNotEqual(response.status_code, HTTPStatus.OK)

    def test_handler_survives_unexpected_authenticator_type(self):
        """Signal handlers must not crash on authenticator types outside
        the known enum (e.g., a future or custom type)."""
        from unittest.mock import Mock

        from allauth.mfa import signals as mfa_signals

        mock_auth = Mock()
        mock_auth.type = "biometric_key"
        mock_auth.id = 42

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            mfa_signals.authenticator_used.send(
                sender=Authenticator,
                request=None,
                user=self.user,
                authenticator=mock_auth,
                reauthenticated=False,
                passwordless=False,
            )

        events = self._parse_events(captured)
        succeeded = [
            e for e in events if e["event"] == "mfa.challenge_succeeded"
        ]
        self.assertEqual(len(succeeded), 1)
        self.assertEqual(succeeded[0]["authenticator_type"], "biometric_key")
        self.assertEqual(succeeded[0]["authenticator_id"], 42)

    def test_payload_excludes_secrets_for_challenge_events(self):
        """All MFA challenge events must exclude TOTP secrets, codes, and
        recovery-code seeds."""
        self._login_and_password_reauth()
        secret = self._enroll_totp()
        self._enter_mfa_stage()
        code = self._compute_valid_totp(secret)

        with self.assertLogs("agentgate.security", level="DEBUG") as captured:
            self.client.post(
                MFA_AUTHENTICATE, {"code": code}, format="json"
            )

        for payload in self._parse_events(captured):
            for forbidden_key in ("secret", "code", "seed", "password",
                                  "email", "recovery_codes"):
                self.assertNotIn(forbidden_key, payload)
            self.assertTrue(
                set(payload.keys()).issubset(_ALLOWED_FIELDS)
            )


class MFASignalRegistrationTests(MFAEntryPointBase):
    """AUTH-05B.9C.3D — duplicate signal registration.

    AppConfig.ready() may be called multiple times during test setup.
    Each signal handler uses a dispatch_uid, so re-registration must not
    produce duplicate events.
    """

    def test_signal_handlers_registered_once(self):
        """Each MFA signal handler dispatch_uid appears exactly once."""
        from allauth.mfa import signals as mfa_signals

        import apps.accounts.signals  # noqa: F401 — ensures import

        signal_uid_map = {
            mfa_signals.authenticator_added: "mfa_security_authenticator_added",
            mfa_signals.authenticator_removed: "mfa_security_authenticator_removed",
            mfa_signals.authenticator_reset: "mfa_security_authenticator_reset",
            mfa_signals.authenticator_used: "mfa_security_authenticator_used",
            mfa_signals.authentication_failed: "mfa_security_authentication_failed",
        }

        for signal, expected_uid in signal_uid_map.items():
            # Django 6.x stores receivers as (lookup_key, ref, sender_ref, weak)
            # where lookup_key = (dispatch_uid, thread_id).
            uids = [
                r[0][0] for r in signal.receivers if r[0][0] is not None
            ]
            self.assertIn(
                expected_uid,
                uids,
                f"dispatch_uid {expected_uid!r} not found in {uids}",
            )
            self.assertEqual(
                uids.count(expected_uid),
                1,
                f"dispatch_uid {expected_uid!r} registered "
                f"{uids.count(expected_uid)} times",
            )
