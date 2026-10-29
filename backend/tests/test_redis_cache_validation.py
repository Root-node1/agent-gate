"""AUTH-05B.4B.2: Redis cache connection validation tests.

Tests the Redis startup validation check in ``apps/accounts/checks.py``.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase


class RedisCacheValidationTestCase(TestCase):
    """Test Redis cache connection validation."""

    @patch("django.conf.settings", new=SimpleNamespace(DEBUG=False))
    @patch("django.core.cache.caches")
    def test_successful_cache_validation(self, mock_caches):
        """Test successful cache validation when Redis is available and functional."""
        from apps.accounts.checks import check_redis_cache_connection

        mock_cache = Mock()
        mock_caches.__getitem__.return_value = mock_cache

        # cache.add() must return a bool (False here since the key already
        # exists after cache.set() in the atomicity sub-test).
        mock_cache.add.return_value = False
        mock_cache.get.return_value = "updated-value"

        errors = check_redis_cache_connection(None)

        self.assertEqual(len(errors), 0)
        mock_cache.add.assert_called()
        mock_cache.set.assert_called()
        mock_cache.get.assert_called_once()
        mock_cache.delete.assert_called()

    @patch("django.conf.settings", new=SimpleNamespace(DEBUG=True))
    def test_development_mode_skips_redis_validation(self):
        """Test that Redis validation is skipped in development mode."""
        from apps.accounts.checks import check_redis_cache_connection

        errors = check_redis_cache_connection(None)

        self.assertEqual(len(errors), 0)

    @patch("django.conf.settings", new=SimpleNamespace(DEBUG=False))
    @patch("django.core.cache.caches")
    def test_cache_connection_failure(self, mock_caches):
        """Test Redis connection failure scenario."""
        from apps.accounts.checks import check_redis_cache_connection

        mock_cache = Mock()
        mock_caches.__getitem__.return_value = mock_cache

        mock_cache.add.side_effect = Exception("Connection refused")

        errors = check_redis_cache_connection(None)

        self.assertEqual(len(errors), 1)
        self.assertIn("accounts.E002", str(errors[0]))
        # Production code includes only the exception type name, not the
        # message, to prevent information leakage.
        self.assertIn("Exception", str(errors[0]))
        self.assertNotIn("Connection refused", str(errors[0]))

    @patch("django.conf.settings", new=SimpleNamespace(DEBUG=False))
    @patch("django.core.cache.caches")
    def test_cache_operations_failure(self, mock_caches):
        """Test cache operations failure scenario."""
        from apps.accounts.checks import check_redis_cache_connection

        mock_cache = Mock()
        mock_caches.__getitem__.return_value = mock_cache

        mock_cache.add.return_value = None
        mock_cache.set.side_effect = Exception("Write failed")

        errors = check_redis_cache_connection(None)

        self.assertEqual(len(errors), 1)
        self.assertIn("accounts.E003", str(errors[0]))

    @patch("django.conf.settings", new=SimpleNamespace(DEBUG=False))
    @patch("django.core.cache.caches")
    def test_cache_add_atomicity_failure(self, mock_caches):
        """Test cache.add() atomicity failure (key overwritten)."""
        from apps.accounts.checks import check_redis_cache_connection

        mock_cache = Mock()
        mock_caches.__getitem__.return_value = mock_cache

        # cache.add() returning True when the key already exists signals
        # a non-atomic, overwriting cache backend — a security issue.
        mock_cache.add.return_value = True
        mock_cache.get.return_value = "updated-value"

        errors = check_redis_cache_connection(None)

        self.assertEqual(len(errors), 1)
        self.assertIn("accounts.E004", str(errors[0]))
        self.assertIn("not atomic", str(errors[0]))

    @patch("django.conf.settings", new=SimpleNamespace(DEBUG=False))
    @patch("django.core.cache.caches")
    def test_cache_atomicity_phase_exception(self, mock_caches):
        """Test E005 when an exception occurs during the atomicity validation phase.

        Phases 1 (connectivity) and 2 (operations) succeed, but phase 3
        (atomicity) raises — e.g. cache.set fails on the pre-seed call.
        """
        from apps.accounts.checks import check_redis_cache_connection

        mock_cache = Mock()
        mock_caches.__getitem__.return_value = mock_cache

        # Phase 1 (connectivity): cache.add succeeds (returns a bool).
        mock_cache.add.return_value = False
        # Phase 2 (operations): first cache.set succeeds; cache.get returns
        # the expected value so phase 2 completes without error.
        # Phase 3 (atomicity): the second cache.set raises, producing E005.
        mock_cache.set.side_effect = [None, Exception("Atomicity phase failure")]
        mock_cache.get.return_value = "updated-value"

        errors = check_redis_cache_connection(None)

        self.assertEqual(len(errors), 1)
        self.assertIn("accounts.E005", str(errors[0]))
        # The error message must not expose credentials or sensitive detail.
        error_msg = str(errors[0])
        self.assertNotIn("password", error_msg.lower())
        self.assertNotIn("user", error_msg.lower())
        self.assertNotIn("secret", error_msg.lower())
        self.assertNotIn("credential", error_msg.lower())
        # Only the exception type name is included, not the message.
        self.assertNotIn("Atomicity phase failure", error_msg)

    @patch("django.conf.settings", new=SimpleNamespace(DEBUG=False))
    @patch("django.core.cache.caches")
    def test_error_message_no_credentials(self, mock_caches):
        """Test that error messages do not contain credentials."""
        from apps.accounts.checks import check_redis_cache_connection

        mock_cache = Mock()
        mock_caches.__getitem__.return_value = mock_cache

        mock_cache.add.side_effect = Exception("Database connection failed")

        errors = check_redis_cache_connection(None)

        self.assertEqual(len(errors), 1)
        error_msg = str(errors[0])
        self.assertNotIn("password", error_msg.lower())
        self.assertNotIn("user", error_msg.lower())
        self.assertNotIn("secret", error_msg.lower())
        self.assertNotIn("credential", error_msg.lower())
