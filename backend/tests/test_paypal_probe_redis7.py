"""Integration and concurrency tests running rate limits and circuit breaker against real Redis 7 container."""

import concurrent.futures
import os

import redis
from django.test import SimpleTestCase, override_settings

from apps.payments.paypal.probe_coordination import (
    CoordinationError,
    check_and_increment_probe_limits,
    record_probe_circuit_outcome,
)
from apps.payments.paypal.probe_types import ProbeFailureReason

# Defaults to the port the CI service container publishes. Override with
# TEST_REDIS_URL when running Redis elsewhere (for example a local container
# mapped to a different host port).
REAL_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REAL_REDIS_URL,
        }
    }
)
class RealRedis7CoordinationTests(SimpleTestCase):
    """Verify Lua script execution, rate limits, and circuit breaker against live Redis 7."""

    def setUp(self):
        # Flush DB 1 before each test
        r = redis.from_url(REAL_REDIS_URL)
        r.flushdb()

    def test_live_redis_org_limit_enforced_by_lua(self):
        org_id = "real-redis-org-1"
        for i in range(5):
            status = check_and_increment_probe_limits(org_id)
            self.assertTrue(status.allowed, f"Attempt {i+1} should be allowed on Redis 7")

        # 6th attempt must be rejected by Lua script in Redis
        status = check_and_increment_probe_limits(org_id)
        self.assertFalse(status.allowed)
        self.assertEqual(status.rejection_reason, ProbeFailureReason.RATE_LIMITED)

    def test_live_redis_concurrent_requests_cannot_exceed_limits(self):
        """Simulate concurrent worker processes hitting Redis 7 simultaneously."""
        org_id = "concurrent-redis-org"
        allowed = 0
        rejected = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_and_increment_probe_limits, org_id) for _ in range(25)]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res.allowed:
                    allowed += 1
                else:
                    rejected += 1

        self.assertEqual(allowed, 5)
        self.assertEqual(rejected, 20)

    def test_live_redis_platform_limit_enforced_by_lua(self):
        for i in range(20):
            status = check_and_increment_probe_limits(f"redis-org-{i}")
            self.assertTrue(status.allowed)

        # 21st attempt across platform must be rejected
        status = check_and_increment_probe_limits("redis-org-overflow")
        self.assertFalse(status.allowed)
        self.assertEqual(status.rejection_reason, ProbeFailureReason.RATE_LIMITED)

    def test_live_redis_circuit_breaker_lua_script(self):
        org_id = "circuit-org-redis"
        record_probe_circuit_outcome(success=False)
        record_probe_circuit_outcome(success=False)

        # Still allowed on 2 failures
        status = check_and_increment_probe_limits(org_id)
        self.assertTrue(status.allowed)

        # 3rd failure trips the circuit in Redis
        record_probe_circuit_outcome(success=False)
        status = check_and_increment_probe_limits(org_id)
        self.assertFalse(status.allowed)
        self.assertEqual(status.rejection_reason, ProbeFailureReason.CIRCUIT_OPEN)
        self.assertGreater(status.retry_after, 0)

    def test_production_fails_closed_when_redis_unavailable(self):
        import os
        old_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        try:
            os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
            # Point to unreachable port or locmem in prod settings simulation
            with override_settings(
                CACHES={
                    "default": {
                        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                        "LOCATION": "unsupported",
                    }
                }
            ):
                with self.assertRaises(CoordinationError):
                    check_and_increment_probe_limits("any-org")
        finally:
            os.environ["DJANGO_SETTINGS_MODULE"] = old_module
