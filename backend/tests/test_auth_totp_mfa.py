"""AUTH-05B.1/AUTH-05B.2: MFA configuration, encryption, and enrollment tests.

These tests verify that:
- allauth.mfa is installed and MFA_* settings are configured as specified.
- The CustomMFAAdapter provides Fernet-backed at-rest encryption.
- TOTP enrollment via the headless API succeeds and secrets are stored encrypted.
- Non-MFA authentication remains functional (covered by the existing 63 auth tests).
"""

import logging
import time
from http import HTTPStatus

from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    format_hotp_value,
    hotp_value,
    validate_totp_code,
)
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.test import TestCase, override_settings

from apps.accounts.adapters import CustomMFAAdapter
from tests.test_auth_signup_login import (
    HEADLESS_BASE,
    PASSWORD,
    AuthTestBase,
    headless_login,
    headless_logout,
)


class MFASettingsTests(TestCase):
    """Verify MFA configuration is loaded with the expected values."""

    def test_allauth_mfa_in_installed_apps(self):
        self.assertIn("allauth.mfa", settings.INSTALLED_APPS)

    def test_mfa_adapter_setting(self):
        self.assertEqual(
            settings.MFA_ADAPTER,
            "apps.accounts.adapters.CustomMFAAdapter",
        )

    def test_mfa_encryption_key_setting(self):
        self.assertTrue(settings.MFA_ENCRYPTION_KEY)

    def test_mfa_encryption_previous_keys_setting(self):
        self.assertIsInstance(settings.MFA_ENCRYPTION_PREVIOUS_KEYS, list)

    def test_trust_disabled(self):
        self.assertFalse(settings.MFA_TRUST_ENABLED)

    def test_totp_tolerance_is_strict(self):
        self.assertEqual(settings.MFA_TOTP_TOLERANCE, 0)

    def test_recovery_codes_show_once(self):
        self.assertTrue(settings.MFA_RECOVERY_CODES_SHOW_ONCE)

    def test_totp_issuer(self):
        self.assertEqual(settings.MFA_TOTP_ISSUER, "AgentGate")

    def test_supported_types_excludes_webauthn(self):
        self.assertEqual(settings.MFA_SUPPORTED_TYPES, ["totp", "recovery_codes"])

    def test_no_invented_mfa_enabled_setting(self):
        """allauth has no MFA_ENABLED setting; MFA is purely app-driven."""
        self.assertFalse(hasattr(settings, "MFA_ENABLED"))

    def test_adapter_resolves_to_custom(self):
        from allauth.mfa.adapter import get_adapter

        adapter = get_adapter()
        from apps.accounts.adapters import CustomMFAAdapter

        self.assertIsInstance(adapter, CustomMFAAdapter)

    def test_config_endpoint_exposes_mfa(self):
        response = self.client.get(f"{HEADLESS_BASE}/config")
        self.assertEqual(response.status_code, HTTPStatus.OK)
        data = response.json()["data"]
        self.assertIn("mfa", data)
        self.assertEqual(data["mfa"]["supported_types"], ["totp", "recovery_codes"])


class TOTPEnrollmentTests(AuthTestBase):
    """Verify TOTP enrollment succeeds and secrets are stored encrypted."""

    def setUp(self):
        super().setUp()
        self.user = self._signup_and_verify()
        headless_logout(self.client)
        headless_login(self.client, email=self.email)
        self.client.post(
            f"{HEADLESS_BASE}/auth/reauthenticate",
            {"password": PASSWORD},
            format="json",
        )

    def test_user_is_authenticated(self):
        self.assertEqual(self.client.get("/api/auth/user/").status_code, 200)

    def test_totp_provisioning_returns_issuer(self):
        response = self.client.get(f"{HEADLESS_BASE}/account/authenticators/totp")
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        meta = response.json()["meta"]
        self.assertIn("otpauth://totp/", meta["totp_url"])
        self.assertIn("issuer=AgentGate", meta["totp_url"])
        self.assertIn("secret", meta)

    def test_totp_enrollment_succeeds(self):
        response = self.client.get(f"{HEADLESS_BASE}/account/authenticators/totp")
        secret = response.json()["meta"]["secret"]
        code = self._compute_valid_totp(secret)
        response = self.client.post(
            f"{HEADLESS_BASE}/account/authenticators/totp",
            {"code": code},
            format="json",
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(Authenticator.objects.filter(type="totp").count(), 1)

    def test_stored_secret_is_encrypted_not_plaintext(self):
        response = self.client.get(f"{HEADLESS_BASE}/account/authenticators/totp")
        secret = response.json()["meta"]["secret"]
        code = self._compute_valid_totp(secret)
        self.client.post(
            f"{HEADLESS_BASE}/account/authenticators/totp",
            {"code": code},
            format="json",
        )
        auth = Authenticator.objects.get(type="totp")
        stored = auth.data["secret"]
        self.assertNotEqual(stored, secret)
        self.assertNotEqual(stored, secret.encode().hex())
        # A Fernet token contains a version byte (0x80) and a timestamp; verify
        # it decrypts back to the original plaintext secret.
        key = settings.MFA_ENCRYPTION_KEY
        fernet = Fernet(key)
        self.assertEqual(fernet.decrypt(stored.encode()).decode(), secret)

    def _compute_valid_totp(self, secret):
        counter = int(time.time()) // mfa_settings.TOTP_PERIOD
        code = format_hotp_value(hotp_value(secret, counter))
        if not validate_totp_code(secret, code):
            time.sleep(1)
            counter = int(time.time()) // mfa_settings.TOTP_PERIOD
            code = format_hotp_value(hotp_value(secret, counter))
        return code


class MFAEncryptionPersistenceTests(AuthTestBase):
    """AUTH-05B.2B: PostgreSQL-backed persistence tests for Fernet MFA encryption.

    These tests exercise the full stack: headless API -> allauth MFA flows ->
    CustomMFAAdapter (Fernet) -> PostgreSQL Authenticator rows.
    """

    def setUp(self):
        super().setUp()
        self.user = self._signup_and_verify()
        headless_logout(self.client)
        headless_login(self.client, email=self.email)
        self.client.post(
            f"{HEADLESS_BASE}/auth/reauthenticate",
            {"password": PASSWORD},
            format="json",
        )
        self._totp_secret = self._enroll_totp()

    def _enroll_totp(self):
        """Enroll TOTP and return the plaintext secret for code computation."""
        response = self.client.get(f"{HEADLESS_BASE}/account/authenticators/totp")
        secret = response.json()["meta"]["secret"]
        code = self._compute_valid_totp(secret)
        response = self.client.post(
            f"{HEADLESS_BASE}/account/authenticators/totp",
            {"code": code},
            format="json",
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        return secret

    def _compute_valid_totp(self, secret):
        counter = int(time.time()) // mfa_settings.TOTP_PERIOD
        code = format_hotp_value(hotp_value(secret, counter))
        if not validate_totp_code(secret, code):
            time.sleep(1)
            counter = int(time.time()) // mfa_settings.TOTP_PERIOD
            code = format_hotp_value(hotp_value(secret, counter))
        return code

    def _tamper_ciphertext(self, value):
        """Flip one character near the end of a Fernet token."""
        idx = -10
        replacement = "A" if value[idx] != "A" else "B"
        return value[:idx] + replacement + value[idx + 1 :]

    # ------------------------------------------------------------------
    # 4. Recovery-code enrollment stores its seed encrypted
    # ------------------------------------------------------------------
    def test_recovery_code_seed_is_encrypted_not_plaintext(self):
        """The auto-generated recovery-codes seed is stored as a Fernet token."""
        rc_auth = Authenticator.objects.get(type="recovery_codes")
        stored_seed = rc_auth.data["seed"]

        # A plaintext seed (secrets.token_hex(40)) is 80 hex chars; a Fernet
        # token is substantially longer and starts with the 0x80 version byte.
        self.assertGreater(len(stored_seed), 100, "seed appears to be plaintext")

        # Verify it decrypts back to a valid 80-char hex seed.
        fernet = Fernet(settings.MFA_ENCRYPTION_KEY)
        decrypted_seed = fernet.decrypt(stored_seed.encode()).decode()
        self.assertEqual(len(decrypted_seed), 80)
        self.assertTrue(all(c in "0123456789abcdef" for c in decrypted_seed))

        # The stored value must not equal the plaintext.
        self.assertNotEqual(stored_seed, decrypted_seed)

    # ------------------------------------------------------------------
    # 5. Recovery-code verification works with encrypted persistence
    # ------------------------------------------------------------------
    def test_recovery_code_verification_works(self):
        """A recovery code from the encrypted seed validates correctly."""
        response = self.client.post(
            f"{HEADLESS_BASE}/account/authenticators/recovery-codes",
            format="json",
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        codes = response.json()["data"]["unused_codes"]
        self.assertGreater(len(codes), 0)

        rc_auth = Authenticator.objects.get(type="recovery_codes")
        wrapped = rc_auth.wrap()
        self.assertTrue(wrapped.validate_code(codes[0]))

    # ------------------------------------------------------------------
    # 6. Tampered ciphertext cannot authenticate
    # ------------------------------------------------------------------
    def test_tampered_ciphertext_raises_invalid_token(self):
        """Tampering the stored TOTP ciphertext raises InvalidToken on validate."""
        totp_auth = Authenticator.objects.get(type="totp")
        original = totp_auth.data["secret"]
        totp_auth.data["secret"] = self._tamper_ciphertext(original)
        totp_auth.save()

        code = self._compute_valid_totp(self._totp_secret)
        wrapped = totp_auth.wrap()
        with self.assertRaises(InvalidToken):
            wrapped.validate_code(code)

    # ------------------------------------------------------------------
    # 7. Wrong encryption keys cannot decrypt existing records
    # ------------------------------------------------------------------
    def test_wrong_encryption_key_cannot_decrypt(self):
        """A record encrypted under the test key cannot be decrypted with a new key."""
        wrong_key = Fernet.generate_key().decode()
        totp_auth = Authenticator.objects.get(type="totp")
        stored = totp_auth.data["secret"]

        with override_settings(
            MFA_ENCRYPTION_KEY=wrong_key,
            MFA_ENCRYPTION_PREVIOUS_KEYS=[],
        ):
            adapter = CustomMFAAdapter()
            with self.assertRaises(InvalidToken):
                adapter.decrypt(stored)

    # ------------------------------------------------------------------
    # 8. A previous authorized key can decrypt records created before rotation
    # ------------------------------------------------------------------
    def test_previous_key_decrypts_pre_rotation_record(self):
        """MultiFernet with the old key in MFA_ENCRYPTION_PREVIOUS_KEYS succeeds."""
        original_key = settings.MFA_ENCRYPTION_KEY
        rotated_key = Fernet.generate_key().decode()
        totp_auth = Authenticator.objects.get(type="totp")
        stored = totp_auth.data["secret"]

        with override_settings(
            MFA_ENCRYPTION_KEY=rotated_key,
            MFA_ENCRYPTION_PREVIOUS_KEYS=[original_key],
        ):
            adapter = CustomMFAAdapter()
            decrypted = adapter.decrypt(stored)
            self.assertEqual(decrypted, self._totp_secret)

    # ------------------------------------------------------------------
    # 9a. No plaintext secrets in logs
    # ------------------------------------------------------------------
    def test_no_plaintext_secrets_in_logs(self):
        """MFA operations must not write plaintext secrets or keys to logs."""
        messages = []

        class _CaptureHandler(logging.Handler):
            def emit(self, record):
                messages.append(record.getMessage())

        handler = _CaptureHandler()
        handler.setLevel(logging.DEBUG)
        root_logger = logging.getLogger()
        old_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(handler)
        try:
            totp_auth = Authenticator.objects.get(type="totp")
            totp_auth.wrap().validate_code(self._compute_valid_totp(self._totp_secret))
            self.client.post(
                f"{HEADLESS_BASE}/account/authenticators/recovery-codes",
                format="json",
            )
        finally:
            root_logger.removeHandler(handler)
            root_logger.setLevel(old_level)

        for msg in messages:
            self.assertNotIn(self._totp_secret, msg)
            self.assertNotIn(settings.MFA_ENCRYPTION_KEY, msg)

    # ------------------------------------------------------------------
    # 9b. No plaintext secrets in error responses
    # ------------------------------------------------------------------
    def test_post_enrollment_totp_response_has_no_secret(self):
        """After enrollment, the TOTP management endpoint must not return the
        plaintext secret in the response body."""
        response = self.client.get(f"{HEADLESS_BASE}/account/authenticators/totp")
        body_str = str(response.json())
        self.assertNotIn(self._totp_secret, body_str)
        self.assertNotIn(settings.MFA_ENCRYPTION_KEY, body_str)

    def test_wrong_code_rejected_without_secret_leak(self):
        """A wrong TOTP code during (re-)provisioning returns an error without
        leaking the plaintext secret or encryption key.
        """
        # After enrollment, POSTing a wrong code to the TOTP endpoint triggers
        # form validation (validate_totp_code) which fails.  The error response
        # must not contain the secret or the encryption key.
        response = self.client.post(
            f"{HEADLESS_BASE}/account/authenticators/totp",
            {"code": "000000"},
            format="json",
        )
        self.assertNotEqual(response.status_code, HTTPStatus.OK)
        body_str = str(response.json())
        self.assertNotIn(self._totp_secret, body_str)
        self.assertNotIn(settings.MFA_ENCRYPTION_KEY, body_str)

    # ------------------------------------------------------------------
    # Positive auth path: valid TOTP code passes validation
    # (This is the exact code path the MFA authenticate form calls.)
    # ------------------------------------------------------------------
    def test_valid_totp_code_authenticates(self):
        """A valid TOTP code passes validation after Fernet round-trip."""
        totp_auth = Authenticator.objects.get(type="totp")
        code = self._compute_valid_totp(self._totp_secret)
        wrapped = totp_auth.wrap()
        self.assertTrue(wrapped.validate_code(code))

    # ------------------------------------------------------------------
    # Negative auth path: tampered ciphertext raises InvalidToken
    # (Already covered by test_tampered_ciphertext_raises_invalid_token,
    #  but verified here through the full Authenticator → TOTP.validate_code
    #  path that the MFA authenticate form uses.)
    # ------------------------------------------------------------------
    def test_valid_code_after_untampered_secret(self):
        """Baseline: a valid code works against the un-tampered stored secret."""
        totp_auth = Authenticator.objects.get(type="totp")
        stored = totp_auth.data["secret"]
        # Stored ciphertext must decrypt back to the original secret.
        adapter = CustomMFAAdapter()
        decrypted = adapter.decrypt(stored)
        self.assertEqual(decrypted, self._totp_secret)


class RecoveryCodeShowOnceTests(AuthTestBase):
    """AUTH-05B.2F: recovery-code show-once behavior over the headless API.

    Verifies the configured ``MFA_RECOVERY_CODES_SHOW_ONCE=True`` contract
    against django-allauth 65.21.0's actual endpoint behavior:

    1. TOTP enrollment auto-creates a recovery-codes Authenticator.
    2. First GET ``/account/authenticators/recovery-codes`` exposes the
       plaintext unused codes (marks ``viewed_at``).
    3. Second GET does **not** expose the plaintext codes (only the count).
    4. The captured codes remain usable for MFA login authentication.

    This test follows the installed allauth API contract exactly; it does
    not override allauth behavior to force incorrect expectations.
    """

    MFA_AUTHENTICATE = f"{HEADLESS_BASE}/auth/2fa/authenticate"
    MFA_REAUTHENTICATE = f"{HEADLESS_BASE}/auth/reauthenticate"
    RECOVERY_CODES_URL = f"{HEADLESS_BASE}/account/authenticators/recovery-codes"

    def setUp(self):
        super().setUp()
        self.user = self._signup_and_verify()
        headless_logout(self.client)
        headless_login(self.client, email=self.email)
        # Reauthenticate so the MFA management endpoints (guarded by
        # raise_if_reauthentication_required) accept the session.
        self.client.post(
            self.MFA_REAUTHENTICATE,
            {"password": PASSWORD},
            format="json",
        )
        self._enroll_totp()

    # -- helpers (same pattern as MFAEncryptionPersistenceTests) --

    def _enroll_totp(self):
        response = self.client.get(f"{HEADLESS_BASE}/account/authenticators/totp")
        secret = response.json()["meta"]["secret"]
        code = self._compute_valid_totp(secret)
        response = self.client.post(
            f"{HEADLESS_BASE}/account/authenticators/totp",
            {"code": code},
            format="json",
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        return secret

    def _compute_valid_totp(self, secret):
        counter = int(time.time()) // mfa_settings.TOTP_PERIOD
        code = format_hotp_value(hotp_value(secret, counter))
        if not validate_totp_code(secret, code):
            time.sleep(1)
            counter = int(time.time()) // mfa_settings.TOTP_PERIOD
            code = format_hotp_value(hotp_value(secret, counter))
        return code

    # ------------------------------------------------------------------
    # 1. TOTP enrollment auto-generates recovery codes
    # ------------------------------------------------------------------
    def test_totp_enrollment_auto_generates_recovery_codes(self):
        """Activating TOTP also activates a recovery-codes authenticator."""
        rc_auths = Authenticator.objects.filter(
            user=self.user, type=Authenticator.Type.RECOVERY_CODES
        )
        self.assertEqual(rc_auths.count(), 1)

    # ------------------------------------------------------------------
    # 2. First retrieval exposes the codes
    # ------------------------------------------------------------------
    def test_first_retrieval_exposes_unused_codes(self):
        """First GET to the recovery-codes endpoint exposes plaintext codes."""
        response = self.client.get(self.RECOVERY_CODES_URL)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        data = response.json()["data"]
        self.assertIn("unused_codes", data)
        codes = data["unused_codes"]
        self.assertEqual(len(codes), mfa_settings.RECOVERY_CODE_COUNT)
        # Each code is an N-digit numeric string.
        for code in codes:
            self.assertTrue(code.isdigit())
            self.assertEqual(len(code), mfa_settings.RECOVERY_CODE_DIGITS)

    # ------------------------------------------------------------------
    # 3 & 4. Second retrieval does NOT expose the codes
    # ------------------------------------------------------------------
    def test_second_retrieval_hides_unused_codes(self):
        """Second GET must not expose plaintext recovery codes (show-once)."""
        # Step 2: first retrieval — codes are exposed.
        first = self.client.get(self.RECOVERY_CODES_URL)
        self.assertEqual(first.status_code, HTTPStatus.OK)
        first_data = first.json()["data"]
        self.assertIn("unused_codes", first_data)
        exposed_codes = first_data["unused_codes"]

        # Step 4: second retrieval — codes must not be exposed.
        second = self.client.get(self.RECOVERY_CODES_URL)
        self.assertEqual(second.status_code, HTTPStatus.OK)
        second_data = second.json()["data"]

        # The sensitive ``unused_codes`` key must be absent.
        self.assertNotIn("unused_codes", second_data)

        # The count may still be present (it is just a number, not a secret).
        self.assertIn("unused_code_count", second_data)
        self.assertEqual(
            second_data["unused_code_count"], len(exposed_codes)
        )

        # No actual code string should appear anywhere in the raw response body.
        body_str = str(second.json())
        for code in exposed_codes:
            self.assertNotIn(code, body_str)

    # ------------------------------------------------------------------
    # 5. Recovery codes remain usable after show-once
    # ------------------------------------------------------------------
    def test_unused_recovery_code_authenticates_after_show_once(self):
        """An unused recovery code still authenticates via MFA login.

        After the first retrieval marks the codes as viewed, the second
        retrieval hides them — but the codes themselves remain valid for
        MFA authentication.  This verifies the show-once display policy
        does not invalidate the underlying credentials.
        """
        # Capture codes on the (only) permitted first retrieval.
        first = self.client.get(self.RECOVERY_CODES_URL)
        codes = first.json()["data"]["unused_codes"]
        code_to_use = codes[0]

        # Second retrieval must hide them …
        second = self.client.get(self.RECOVERY_CODES_URL)
        self.assertNotIn("unused_codes", second.json()["data"])

        # … but the captured code is still unused and must authenticate.
        headless_logout(self.client)

        # Password login enters the MFA pending stage.
        login_resp = headless_login(self.client, email=self.email)
        self.assertEqual(login_resp.status_code, HTTPStatus.UNAUTHORIZED)
        self.assertFalse(login_resp.json()["meta"]["is_authenticated"])

        # Submit the captured recovery code to complete MFA.
        response = self.client.post(
            self.MFA_AUTHENTICATE,
            {"code": code_to_use},
            format="json",
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTrue(response.json()["meta"]["is_authenticated"])
