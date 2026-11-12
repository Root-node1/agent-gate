"""Tests for the PayPal Sandbox OAuth probe, distributed coordination, and platform status.

Covers:
- Sandbox-only invariant (production hosts and live mode fail closed).
- Wall-clock 8.0-second overall deadline enforcement with zero retries.
- Sanitized failure codes (invalid_credentials, rate_limited, upstream_unavailable, timeout, circuit_open).
- Redis Lua script atomic coordination & concurrent requests testing.
- Circuit breaker transitions and fail-closed behavior on coordination failure.
- Platform-wide state determination and 24-hour expiry of successfully_tested state.
- Separation of local rejections from upstream probe health.
"""

import concurrent.futures
import time
from unittest.mock import MagicMock, patch

import httpx
from django.test import SimpleTestCase, override_settings

from apps.payments.paypal.exceptions import PayPalConfigurationError
from apps.payments.paypal.probe_coordination import (
    CoordinationError,
    check_and_increment_probe_limits,
    record_probe_circuit_outcome,
)
from apps.payments.paypal.probe_service import (
    PROBE_OVERALL_DEADLINE_SECONDS,
    _validate_sandbox_url,
    execute_sandbox_oauth_probe,
)
from apps.payments.paypal.probe_types import (
    ProbeConnectionState,
    ProbeFailureReason,
)
from apps.payments.paypal.status_service import (
    get_platform_integration_status,
    update_platform_probe_outcome,
)


class SandboxInvariantTests(SimpleTestCase):
    """Test strict sandbox invariant enforcement."""

    def test_production_hosts_rejected_by_host_validator(self):
        prod_urls = [
            "https://api.paypal.com/v1/oauth2/token",
            "https://api-m.paypal.com/v1/oauth2/token",
            "https://paypal.com/v1/oauth2/token",
            "https://www.paypal.com/v1/oauth2/token",
            "http://api-m.sandbox.paypal.com/v1/oauth2/token",  # non-https
        ]
        for url in prod_urls:
            with self.subTest(url=url):
                with self.assertRaises(PayPalConfigurationError):
                    _validate_sandbox_url(url)

    def test_sandbox_host_accepted(self):
        # Should not raise
        _validate_sandbox_url("https://api-m.sandbox.paypal.com/v1/oauth2/token")

    @override_settings(PAYPAL_ENV="sandbox", PAYPAL_ALLOW_LIVE=True)
    def test_live_allow_override_fails_closed(self):
        with self.assertRaises(PayPalConfigurationError):
            execute_sandbox_oauth_probe(client_id="test-cid", client_secret="test-sec")

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="test-cid",
        PAYPAL_CLIENT_SECRET="test-sec",
    )
    def test_redirect_to_production_host_is_intercepted_and_fails_closed(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 302
        mock_response.headers = {"Location": "https://api.paypal.com/v1/oauth2/token"}
        mock_client.post.return_value = mock_response

        with self.assertRaises(PayPalConfigurationError):
            execute_sandbox_oauth_probe(http_client=mock_client)


class ProbeTimeoutAndDeadlineTests(SimpleTestCase):
    """Test wall-clock 8.0-second total deadline and zero retries."""

    def test_probe_timeout_constant_is_eight_seconds(self):
        self.assertEqual(PROBE_OVERALL_DEADLINE_SECONDS, 8.0)

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="test-cid",
        PAYPAL_CLIENT_SECRET="test-sec",
        PAYPAL_CHECKOUT_ENABLED="false",
        PAYPAL_PAYOUTS_ENABLED="false",
    )
    def test_probe_timeout_maps_to_timeout_failure_code(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = httpx.TimeoutException("Read timed out")

        res = execute_sandbox_oauth_probe(http_client=mock_client)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, ProbeFailureReason.TIMEOUT)
        self.assertEqual(mock_client.post.call_count, 1)  # Zero retries

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="test-cid",
        PAYPAL_CLIENT_SECRET="test-sec",
        PAYPAL_CHECKOUT_ENABLED="false",
        PAYPAL_PAYOUTS_ENABLED="false",
    )
    def test_overall_wall_clock_deadline_enforced_when_stalled(self):
        """Test that an operation exceeding the overall deadline aborts with timeout and cancels cleanly."""
        mock_async_client = MagicMock(spec=httpx.AsyncClient)

        async def slow_async_post(*args, **kwargs):
            import anyio
            await anyio.sleep(1.0)
            mock_res = MagicMock(spec=httpx.Response)
            mock_res.status_code = 200
            return mock_res

        mock_async_client.post.side_effect = slow_async_post

        # Run with a short deadline (0.15s) to deterministically test the wall-clock abort
        start = time.monotonic()
        res = execute_sandbox_oauth_probe(async_client=mock_async_client, overall_deadline=0.15)
        elapsed = time.monotonic() - start

        self.assertFalse(res.success)
        self.assertEqual(res.error_code, ProbeFailureReason.TIMEOUT)
        self.assertLess(elapsed, 0.5)  # Cancelled immediately at 0.15s without waiting for 1.0s sleep

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="test-cid",
        PAYPAL_CLIENT_SECRET="test-sec",
        PAYPAL_CHECKOUT_ENABLED="false",
        PAYPAL_PAYOUTS_ENABLED="false",
    )
    def test_probe_auth_failure_maps_to_invalid_credentials(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_client.post.return_value = mock_response

        res = execute_sandbox_oauth_probe(http_client=mock_client)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, ProbeFailureReason.INVALID_CREDENTIALS)

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="test-cid",
        PAYPAL_CLIENT_SECRET="test-sec",
        PAYPAL_CHECKOUT_ENABLED="false",
        PAYPAL_PAYOUTS_ENABLED="false",
    )
    def test_probe_upstream_rate_limit_maps_to_rate_limited(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        res = execute_sandbox_oauth_probe(http_client=mock_client)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, ProbeFailureReason.RATE_LIMITED)

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="test-cid",
        PAYPAL_CLIENT_SECRET="test-sec",
        PAYPAL_CHECKOUT_ENABLED="false",
        PAYPAL_PAYOUTS_ENABLED="false",
    )
    def test_probe_upstream_500_maps_to_upstream_unavailable(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 502
        mock_client.post.return_value = mock_response

        res = execute_sandbox_oauth_probe(http_client=mock_client)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, ProbeFailureReason.UPSTREAM_UNAVAILABLE)

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="test-cid",
        PAYPAL_CLIENT_SECRET="test-sec",
        PAYPAL_CHECKOUT_ENABLED="false",
        PAYPAL_PAYOUTS_ENABLED="false",
    )
    def test_probe_success_returns_success_without_token(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "SUPER_SECRET_TOKEN", "token_type": "Bearer"}
        mock_client.post.return_value = mock_response

        res = execute_sandbox_oauth_probe(http_client=mock_client)
        self.assertTrue(res.success)
        self.assertIsNone(res.error_code)
        self.assertFalse(hasattr(res, "access_token"))
        self.assertFalse(hasattr(res, "token"))


class DistributedCoordinationTests(SimpleTestCase):
    """Test distributed coordination rate limits, concurrency, and circuit breaker."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_organization_rate_limit_exceeded(self):
        org_id = "test-org-123"
        for i in range(5):
            status = check_and_increment_probe_limits(org_id)
            self.assertTrue(status.allowed, f"Attempt {i+1} should be allowed")

        # 6th attempt must be rejected
        status = check_and_increment_probe_limits(org_id)
        self.assertFalse(status.allowed)
        self.assertEqual(status.rejection_reason, ProbeFailureReason.RATE_LIMITED)

    def test_platform_rate_limit_exceeded(self):
        for i in range(20):
            status = check_and_increment_probe_limits(f"org-{i}")
            self.assertTrue(status.allowed)

        # 21st must be rejected by platform limit
        status = check_and_increment_probe_limits("org-overflow")
        self.assertFalse(status.allowed)
        self.assertEqual(status.rejection_reason, ProbeFailureReason.RATE_LIMITED)

    def test_concurrent_requests_cannot_exceed_limits(self):
        """Prove simultaneous requests cannot exceed the configured limits."""
        org_id = "concurrent-org"
        allowed_count = 0
        rejected_count = 0

        # Launch 25 concurrent threads attempting to probe simultaneously
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(check_and_increment_probe_limits, org_id)
                for _ in range(25)
            ]
            for f in concurrent.futures.as_completed(futures):
                status = f.result()
                if status.allowed:
                    allowed_count += 1
                else:
                    rejected_count += 1

        # Must never allow more than ORG_RATE_LIMIT_MAX (5)
        self.assertEqual(allowed_count, 5)
        self.assertEqual(rejected_count, 20)

    def test_circuit_breaker_trips_after_three_failures(self):
        org_id = "circuit-test-org"
        record_probe_circuit_outcome(success=False)
        record_probe_circuit_outcome(success=False)
        # Still not open
        status = check_and_increment_probe_limits(org_id)
        self.assertTrue(status.allowed)

        # 3rd failure trips the circuit
        record_probe_circuit_outcome(success=False)
        status = check_and_increment_probe_limits(org_id)
        self.assertFalse(status.allowed)
        self.assertEqual(status.rejection_reason, ProbeFailureReason.CIRCUIT_OPEN)

    def test_coordination_fails_closed_when_cache_raises(self):
        with patch("apps.payments.paypal.probe_coordination._get_cache") as mock_cache:
            mock_cache.side_effect = Exception("Redis connection refused")
            with self.assertRaises(CoordinationError):
                check_and_increment_probe_limits("org-err")

    def test_lua_script_evaluation_when_redis_client_present(self):
        """Verify Lua script eval invocation when backed by a Redis connection."""
        mock_cache = MagicMock()
        mock_redis = MagicMock()
        # [allowed=1, reason="", retry_after=0]
        mock_redis.eval.return_value = [1, "", 0]

        with patch("apps.payments.paypal.probe_coordination._get_cache", return_value=mock_cache):
            with patch("apps.payments.paypal.probe_coordination._get_raw_redis_client", return_value=mock_redis):
                status = check_and_increment_probe_limits("redis-org")
                self.assertTrue(status.allowed)
                self.assertEqual(mock_redis.eval.call_count, 1)


class PlatformIntegrationStatusTests(SimpleTestCase):
    """Test platform status calculations, 24-hour expiry, and failure preservation."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="",
        PAYPAL_CLIENT_SECRET="",
    )
    def test_not_configured_state(self):
        status = get_platform_integration_status()
        self.assertEqual(status["state"], ProbeConnectionState.NOT_CONFIGURED)
        self.assertFalse(status["live_payments_enabled"])

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="AX1234567899Z",
        PAYPAL_CLIENT_SECRET="secret123",
        PAYPAL_WEBHOOK_ID="WH-9876543210",
        PAYPAL_CHECKOUT_ENABLED="true",
        PAYPAL_PAYOUTS_ENABLED="false",
    )
    def test_configured_state_before_probe(self):
        status = get_platform_integration_status()
        self.assertEqual(status["state"], ProbeConnectionState.CONFIGURED)
        self.assertEqual(status["client_id_preview"], "AX1...99Z")
        self.assertEqual(status["webhook_id_preview"], "WH-...210")
        self.assertTrue(status["webhook_configured"])
        self.assertTrue(status["checkout_enabled"])
        self.assertFalse(status["payouts_enabled"])
        self.assertFalse(status["live_payments_enabled"])

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="AX1234567899Z",
        PAYPAL_CLIENT_SECRET="secret123",
    )
    def test_successfully_tested_state_and_24h_expiry(self):
        now = time.time()
        # Record recent success (1 hour ago)
        update_platform_probe_outcome(True, tested_at=now - 3600)

        status = get_platform_integration_status()
        self.assertEqual(status["state"], ProbeConnectionState.SUCCESSFULLY_TESTED)
        self.assertEqual(status["last_attempt_at"], now - 3600)
        self.assertEqual(status["last_successful_at"], now - 3600)
        self.assertIsNone(status["last_attempt_error"])

        # Record success older than 24 hours (25 hours ago)
        update_platform_probe_outcome(True, tested_at=now - (25 * 3600))
        status_expired = get_platform_integration_status()
        self.assertEqual(status_expired["state"], ProbeConnectionState.CONFIGURED)

    @override_settings(
        PAYPAL_ENV="sandbox",
        PAYPAL_CLIENT_ID="AX1234567899Z",
        PAYPAL_CLIENT_SECRET="secret123",
    )
    def test_failed_probe_preserves_error_code(self):
        now = time.time()
        update_platform_probe_outcome(
            False,
            tested_at=now,
            error_code=ProbeFailureReason.INVALID_CREDENTIALS,
        )

        status = get_platform_integration_status()
        self.assertEqual(status["state"], ProbeConnectionState.FAILED)
        self.assertEqual(status["last_attempt_error"], ProbeFailureReason.INVALID_CREDENTIALS)
        self.assertEqual(status["last_attempt_at"], now)
