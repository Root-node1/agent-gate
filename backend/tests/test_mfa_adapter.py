"""AUTH-05B.2: Fernet-backed MFA adapter encryption tests.

Focused tests for ``CustomMFAAdapter.encrypt`` / ``decrypt`` and the
``mfa_crypto`` key ring.  Uses deterministic TEST-ONLY Fernet keys that must
never appear in production configuration.

Each test maps to a requirement from the AUTH-05B.2 specification:
    1. Encryption differs from plaintext.
    2. Encryption/decryption round trip.
    3. Tampered ciphertext rejected.
    4. Missing primary key rejected.
    5. Invalid primary key rejected.
    6. New ciphertext uses primary key.
    7. Previous-key ciphertext decrypts.
    8. Rotation retains access to existing ciphertext.
    9. Removing an old key prevents decryption of old ciphertext.
   10. Changing DJANGO_SECRET_KEY does not affect MFA decryption.
   11. Plaintext input cannot be accepted as ciphertext.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.accounts.adapters import CustomMFAAdapter
from apps.accounts.checks import check_mfa_bypass_code, check_mfa_encryption_key

# Deterministic TEST-ONLY Fernet keys (44-char urlsafe base64 of 32 bytes).
# Generated via Fernet.generate_key() — never use in production.
TEST_KEY_PRIMARY = "QG92N9nkDu9c2Nh3TjwTBLTpPFozP20BQl2dwhAmsNM="
TEST_KEY_PREVIOUS = "UFhG3R_rB7uupzdJl7RA4xpVRHs7vl9luwLZqELP1Y0="
TEST_KEY_ROTATED = "Hsj_6TY7mP5V3Xt_d9zGhIyoPLJmXFZPRFSHipwjdoM="


@override_settings(
    MFA_ENCRYPTION_KEY=TEST_KEY_PRIMARY,
    MFA_ENCRYPTION_PREVIOUS_KEYS=[],
)
class MFAAdapterBasicTests(SimpleTestCase):
    """Tests 1-3, 6, 10, 11: core encrypt/decrypt with the default test key."""

    def setUp(self):
        self.adapter = CustomMFAAdapter()

    # --- 1. Encryption differs from plaintext ---
    def test_encryption_differs_from_plaintext(self):
        plaintext = "JBSWY3DPEHPK3PXP"
        ciphertext = self.adapter.encrypt(plaintext)
        self.assertNotEqual(ciphertext, plaintext)
        self.assertNotEqual(ciphertext, plaintext.encode())

    # --- 2. Encryption/decryption round trip ---
    def test_round_trip(self):
        plaintext = "my-totp-secret-123"
        ciphertext = self.adapter.encrypt(plaintext)
        self.assertEqual(self.adapter.decrypt(ciphertext), plaintext)

    # --- 3. Tampered ciphertext rejected ---
    def test_tampered_ciphertext_rejected(self):
        ciphertext = self.adapter.encrypt("secret")
        idx = 10
        replacement = "A" if ciphertext[idx] != "A" else "B"
        tampered = ciphertext[:idx] + replacement + ciphertext[idx + 1 :]
        with self.assertRaises(InvalidToken):
            self.adapter.decrypt(tampered)

    # --- 6. New ciphertext uses primary key ---
    def test_new_ciphertext_uses_primary_key(self):
        plaintext = "secret-to-protect"
        ciphertext = self.adapter.encrypt(plaintext)
        primary_fernet = Fernet(TEST_KEY_PRIMARY)
        self.assertEqual(
            primary_fernet.decrypt(ciphertext.encode()).decode(), plaintext
        )

    # --- 10. Changing DJANGO_SECRET_KEY does not affect MFA decryption ---
    def test_django_secret_key_independence(self):
        from django.conf import settings

        self.assertNotEqual(settings.MFA_ENCRYPTION_KEY, settings.SECRET_KEY)
        ciphertext = self.adapter.encrypt("totp-secret-value")
        with override_settings(DJANGO_SECRET_KEY="a-completely-different-secret-key"):
            self.assertEqual(self.adapter.decrypt(ciphertext), "totp-secret-value")

    # --- 11. Plaintext input cannot be accepted as ciphertext ---
    def test_plaintext_rejected_as_ciphertext(self):
        plaintext = "JBSWY3DPEHPK3PXP"
        with self.assertRaises(InvalidToken):
            self.adapter.decrypt(plaintext)


@override_settings(
    MFA_ENCRYPTION_KEY=TEST_KEY_PRIMARY,
    MFA_ENCRYPTION_PREVIOUS_KEYS=[TEST_KEY_PREVIOUS],
)
class MFAKeyRotationTests(SimpleTestCase):
    """Tests 4-5, 7-9: key configuration, missing/invalid keys, rotation."""

    def setUp(self):
        self.adapter = CustomMFAAdapter()

    # --- 4. Missing primary key rejected ---
    @override_settings(MFA_ENCRYPTION_KEY="", MFA_ENCRYPTION_PREVIOUS_KEYS=[])
    def test_missing_primary_key_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            self.adapter.encrypt("secret")
        with self.assertRaises(ImproperlyConfigured):
            self.adapter.decrypt("some-ciphertext")

    # --- 5. Invalid primary key rejected ---
    @override_settings(
        MFA_ENCRYPTION_KEY="not-a-valid-fernet-key",
        MFA_ENCRYPTION_PREVIOUS_KEYS=[],
    )
    def test_invalid_primary_key_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            self.adapter.encrypt("secret")

    # --- 7. Previous-key ciphertext decrypts ---
    def test_previous_key_ciphertext_decrypts(self):
        plaintext = "recovery-seed"
        prev_fernet = Fernet(TEST_KEY_PREVIOUS)
        ciphertext = prev_fernet.encrypt(plaintext.encode()).decode()
        self.assertEqual(self.adapter.decrypt(ciphertext), plaintext)

    # --- 8. Rotation retains access to existing ciphertext ---
    def test_rotation_retains_access(self):
        plaintext = "existing-secret"
        ciphertext = self.adapter.encrypt(plaintext)
        with override_settings(
            MFA_ENCRYPTION_KEY=TEST_KEY_ROTATED,
            MFA_ENCRYPTION_PREVIOUS_KEYS=[TEST_KEY_PRIMARY],
        ):
            self.assertEqual(self.adapter.decrypt(ciphertext), plaintext)

    # --- 9. Removing an old key prevents decryption of old ciphertext ---
    def test_removing_old_key_prevents_decryption(self):
        plaintext = "old-key-secret"
        prev_fernet = Fernet(TEST_KEY_PREVIOUS)
        ciphertext = prev_fernet.encrypt(plaintext.encode()).decode()
        with override_settings(
            MFA_ENCRYPTION_KEY=TEST_KEY_PRIMARY,
            MFA_ENCRYPTION_PREVIOUS_KEYS=[],
        ):
             with self.assertRaises(InvalidToken):
                 self.adapter.decrypt(ciphertext)
        self.assertEqual(self.adapter.decrypt(ciphertext), plaintext)


@override_settings(
    MFA_ENCRYPTION_KEY=TEST_KEY_PRIMARY,
    MFA_ENCRYPTION_PREVIOUS_KEYS=[],
)
class MFAConfigCheckTests(SimpleTestCase):
    """AUTH-05B.2D: system check validates MFA_ENCRYPTION_KEY at startup.

    Production (DEBUG=False) rejects missing or malformed keys with a blocking
    Error; development/test (DEBUG=True) emits a non-blocking Warning.  Test
    settings supply a deterministic valid key so the check is silent under the
    normal test runner.
    """

    def _run_check(self, **overrides):
        with override_settings(**overrides):
            return check_mfa_encryption_key(None)

    # --- Valid configuration: no issues ---
    def test_valid_key_no_issues(self):
        self.assertEqual(self._run_check(), [])

    def test_valid_primary_and_previous_keys_no_issues(self):
        self.assertEqual(
            self._run_check(MFA_ENCRYPTION_PREVIOUS_KEYS=[TEST_KEY_PREVIOUS]),
            [],
        )

    # --- Missing primary key ---
    def test_missing_key_warning_in_debug(self):
        result = self._run_check(MFA_ENCRYPTION_KEY="", DEBUG=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.W001")

    def test_missing_key_error_in_production(self):
        result = self._run_check(MFA_ENCRYPTION_KEY="", DEBUG=False)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.E001")

    # --- Invalid primary key ---
    def test_invalid_key_warning_in_debug(self):
        result = self._run_check(
            MFA_ENCRYPTION_KEY="not-a-valid-fernet-key", DEBUG=True
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.W001")

    def test_invalid_key_error_in_production(self):
        result = self._run_check(
            MFA_ENCRYPTION_KEY="not-a-valid-fernet-key", DEBUG=False
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.E001")

    # --- Previous keys are also validated ---
    def test_invalid_previous_key_error_in_production(self):
        result = self._run_check(
            MFA_ENCRYPTION_PREVIOUS_KEYS=["malformed-previous-key"],
            DEBUG=False,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.E001")

    def test_invalid_previous_key_warning_in_debug(self):
        result = self._run_check(
            MFA_ENCRYPTION_PREVIOUS_KEYS=["malformed-previous-key"],
            DEBUG=True,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.W001")

    # --- No key material in error messages ---
    def test_error_message_does_not_leak_key_value(self):
        leak = "super-secret-key-value-1234567890"
        result = self._run_check(MFA_ENCRYPTION_KEY=leak, DEBUG=False)
        self.assertEqual(len(result), 1)
        self.assertNotIn(leak, str(result[0].msg))


@override_settings(
    MFA_ENCRYPTION_KEY=TEST_KEY_PRIMARY,
    MFA_ENCRYPTION_PREVIOUS_KEYS=[],
    MFA_TOTP_INSECURE_BYPASS_CODE=None,
)
class MFABypassCodeCheckTests(SimpleTestCase):
    """AUTH-05B.6: system check rejects MFA_TOTP_INSECURE_BYPASS_CODE in production.

    Production (DEBUG=False) blocks the bypass code with a blocking Error
    (accounts.E006); development/test (DEBUG=True) emits a non-blocking
    Warning (accounts.W002).  No bypass-code value is leaked in messages.
    """

    def _run_check(self, **overrides):
        with override_settings(**overrides):
            return check_mfa_bypass_code(None)

    # --- Bypass code absent: check passes in all environments ---
    def test_bypass_code_absent_passes_in_production(self):
        self.assertEqual(self._run_check(DEBUG=False), [])

    def test_bypass_code_absent_passes_in_development(self):
        self.assertEqual(self._run_check(DEBUG=True), [])

    # --- Bypass code configured: blocked in production ---
    def test_bypass_code_error_in_production(self):
        result = self._run_check(
            MFA_TOTP_INSECURE_BYPASS_CODE="123456", DEBUG=False
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.E006")

    # --- Bypass code configured: warning in development ---
    def test_bypass_code_warning_in_development(self):
        result = self._run_check(
            MFA_TOTP_INSECURE_BYPASS_CODE="123456", DEBUG=True
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.W002")

    # --- Empty string bypass code is treated as absent ---
    def test_empty_bypass_code_is_absent_in_production(self):
        result = self._run_check(
            MFA_TOTP_INSECURE_BYPASS_CODE="", DEBUG=False
        )
        self.assertEqual(result, [])

    # --- No bypass code value leaked in error messages ---
    def test_error_message_does_not_leak_bypass_code_value(self):
        leak = "super-secret-bypass-code-98765"
        result = self._run_check(
            MFA_TOTP_INSECURE_BYPASS_CODE=leak, DEBUG=False
        )
        self.assertEqual(len(result), 1)
        self.assertNotIn(leak, str(result[0].msg))

    # --- Falsey non-None/non-empty-string values are also rejected ---
    # Do not rely solely on truthiness: 0, False, etc. are configured values.
    def test_integer_zero_bypass_code_rejected_in_production(self):
        result = self._run_check(MFA_TOTP_INSECURE_BYPASS_CODE=0, DEBUG=False)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.E006")

    def test_boolean_false_bypass_code_rejected_in_production(self):
        result = self._run_check(
            MFA_TOTP_INSECURE_BYPASS_CODE=False, DEBUG=False
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.E006")

    def test_integer_zero_bypass_code_warning_in_development(self):
        result = self._run_check(MFA_TOTP_INSECURE_BYPASS_CODE=0, DEBUG=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "accounts.W002")
