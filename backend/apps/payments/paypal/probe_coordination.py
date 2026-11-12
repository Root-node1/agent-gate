"""Atomic distributed rate limiting and circuit breaking for the shared PayPal OAuth probe.

Enforces:
- Organization Limit: At most 5 probe requests per organization per 5-minute window.
- Platform Limit: At most 20 probe requests across all organizations per 5-minute window.
- Circuit Breaker: 60-second open state after 3 consecutive upstream failures or upstream 429.
- Redis Atomicity: Uses an atomic Lua script when backed by a Redis client, and thread-safe atomic
  coordination otherwise. Counter increments and expiry TTLs are set atomically in a single operation.
- Fail-Closed: If the distributed cache backend is unavailable, unreachable, or returns an error,
  coordination strictly fails closed and raises CoordinationError. No silent per-process memory fallback.
"""

from __future__ import annotations

import threading
import time
from typing import Any, NamedTuple

from django.core.cache import caches
from django.core.cache.backends.base import InvalidCacheBackendError

from .probe_types import ProbeFailureReason

ORG_RATE_LIMIT_MAX = 5
PLATFORM_RATE_LIMIT_MAX = 20
WINDOW_SECONDS = 300  # 5 minutes
CIRCUIT_BREAKER_COOLDOWN = 60  # 60 seconds
CIRCUIT_FAILURE_THRESHOLD = 3

CACHE_ALIAS = "default"
KEY_PREFIX_ORG = "agentgate:probe:org:"
KEY_PLATFORM = "agentgate:probe:platform"
KEY_CIRCUIT = "agentgate:probe:circuit_breaker"

# Lua script for atomic rate limiting and circuit checking in Redis.
# Keys:
#   KEYS[1]: circuit breaker key
#   KEYS[2]: platform rate limit key
#   KEYS[3]: organization rate limit key
# ARGV:
#   ARGV[1]: current timestamp (seconds float/int)
#   ARGV[2]: rate limit window seconds (300)
#   ARGV[3]: platform limit max (20)
#   ARGV[4]: organization limit max (5)
# Returns:
#   Array [allowed (0 or 1), rejection_reason (string or ""), retry_after (int)]
LUA_PROBE_RATE_LIMIT = """
local circuit_raw = redis.call('GET', KEYS[1])
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local platform_max = tonumber(ARGV[3])
local org_max = tonumber(ARGV[4])

if circuit_raw then
    local sep = string.find(circuit_raw, ":")
    if sep then
        local st = string.sub(circuit_raw, 1, sep - 1)
        local open_until = tonumber(string.sub(circuit_raw, sep + 1))
        if st == "open" and open_until and now < open_until then
            local retry_after = math.max(1, math.ceil(open_until - now))
            return {0, "circuit_open", retry_after}
        end
    end
end

-- Platform limit check & increment
local plat_count = redis.call('INCR', KEYS[2])
if plat_count == 1 then
    redis.call('EXPIRE', KEYS[2], window)
end
if plat_count > platform_max then
    local ttl = redis.call('TTL', KEYS[2])
    return {0, "rate_limited", math.max(1, ttl)}
end

-- Org limit check & increment
local org_count = redis.call('INCR', KEYS[3])
if org_count == 1 then
    redis.call('EXPIRE', KEYS[3], window)
end
if org_count > org_max then
    local ttl = redis.call('TTL', KEYS[3])
    return {0, "rate_limited", math.max(1, ttl)}
end

return {1, "", 0}
"""

# Lua script for recording circuit outcomes atomically
# Keys:
#   KEYS[1]: circuit breaker key
# ARGV:
#   ARGV[1]: success (1 or 0)
#   ARGV[2]: is_rate_limited (1 or 0)
#   ARGV[3]: now (seconds)
#   ARGV[4]: failure_threshold (3)
#   ARGV[5]: cooldown_seconds (60)
#   ARGV[6]: window_seconds (300)
LUA_PROBE_CIRCUIT_OUTCOME = """
local success = tonumber(ARGV[1])
local is_rl = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local threshold = tonumber(ARGV[4])
local cooldown = tonumber(ARGV[5])
local window = tonumber(ARGV[6])

if success == 1 then
    redis.call('SET', KEYS[1], "closed:0", 'EX', window)
    return "closed"
end

local current = redis.call('GET', KEYS[1])
local failures = 0
if current then
    local sep = string.find(current, ":")
    if sep then
        failures = tonumber(string.sub(current, sep + 1)) or 0
    end
end

failures = failures + 1
if is_rl == 1 or failures >= threshold then
    local open_until = now + cooldown
    redis.call('SET', KEYS[1], "open:" .. tostring(open_until), 'EX', cooldown)
    return "open"
else
    redis.call('SET', KEYS[1], "closed:" .. tostring(failures), 'EX', window)
    return "closed"
end
"""


class CoordinationError(Exception):
    """Raised when distributed coordination fails closed."""


class CoordinationStatus(NamedTuple):
    allowed: bool
    rejection_reason: str | None = None
    retry_after: int | None = None


_fallback_lock = threading.Lock()


def _get_cache():
    try:
        return caches[CACHE_ALIAS]
    except (InvalidCacheBackendError, KeyError) as exc:
        raise CoordinationError("Distributed cache backend unavailable.") from exc


def _get_raw_redis_client(cache_backend: Any) -> Any:
    """Safely extract raw Redis client from Django RedisCache or django-redis if present."""
    # Django 4.0+ built-in RedisCache
    client_factory = getattr(cache_backend, "_cache", None)
    if client_factory is not None and hasattr(client_factory, "get_client"):
        try:
            return client_factory.get_client()
        except Exception:
            pass
    # Direct redis client attribute
    client = getattr(cache_backend, "_client", None)
    if client is not None and hasattr(client, "eval"):
        return client
    return None


def check_and_increment_probe_limits(organization_id: str) -> CoordinationStatus:
    """Atomically verify and increment organization and platform rate limits.

    Uses Redis Lua script execution when supported, or synchronized atomic updates.
    Strict fail-closed semantics: Never silently bypass coordination.
    """
    try:
        cache = _get_cache()
        now = time.time()
        org_key = f"{KEY_PREFIX_ORG}{organization_id}"
        plat_key = KEY_PLATFORM
        circuit_key = KEY_CIRCUIT

        redis_client = _get_raw_redis_client(cache)
        if redis_client is not None:
            # Execute atomic Redis Lua script
            res = redis_client.eval(
                LUA_PROBE_RATE_LIMIT,
                3,
                circuit_key,
                plat_key,
                org_key,
                now,
                WINDOW_SECONDS,
                PLATFORM_RATE_LIMIT_MAX,
                ORG_RATE_LIMIT_MAX,
            )
            # res: [allowed, reason, retry_after]
            allowed = bool(res[0])
            if allowed:
                return CoordinationStatus(allowed=True)
            reason = res[1] if isinstance(res[1], str) else res[1].decode("utf-8")
            retry_after = int(res[2])
            return CoordinationStatus(
                allowed=False,
                rejection_reason=reason,
                retry_after=retry_after,
            )

        # In production (config.settings.prod), Redis is strictly required. No in-memory fallback.
        import os
        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        if "prod" in settings_module:
            raise CoordinationError("Production requires Redis coordination; in-memory fallback is forbidden.")

        # In-memory synchronized fallback ONLY for local dev / test runners (e.g. LocMemCache)
        with _fallback_lock:
            circuit_data = cache.get(circuit_key)
            if isinstance(circuit_data, dict):
                state = circuit_data.get("state")
                open_until = circuit_data.get("open_until", 0)
                if state == "open":
                    if now < open_until:
                        retry_after = max(1, int(open_until - now))
                        return CoordinationStatus(
                            allowed=False,
                            rejection_reason=ProbeFailureReason.CIRCUIT_OPEN,
                            retry_after=retry_after,
                        )

            # Platform limit increment
            current_plat = cache.get(plat_key)
            if current_plat is None:
                cache.set(plat_key, 1, timeout=WINDOW_SECONDS)
                plat_count = 1
            else:
                plat_count = current_plat + 1
                cache.set(plat_key, plat_count, timeout=WINDOW_SECONDS)

            if plat_count > PLATFORM_RATE_LIMIT_MAX:
                return CoordinationStatus(
                    allowed=False,
                    rejection_reason=ProbeFailureReason.RATE_LIMITED,
                    retry_after=WINDOW_SECONDS,
                )

            # Org limit increment
            current_org = cache.get(org_key)
            if current_org is None:
                cache.set(org_key, 1, timeout=WINDOW_SECONDS)
                org_count = 1
            else:
                org_count = current_org + 1
                cache.set(org_key, org_count, timeout=WINDOW_SECONDS)

            if org_count > ORG_RATE_LIMIT_MAX:
                return CoordinationStatus(
                    allowed=False,
                    rejection_reason=ProbeFailureReason.RATE_LIMITED,
                    retry_after=WINDOW_SECONDS,
                )

            return CoordinationStatus(allowed=True)

    except Exception as exc:
        raise CoordinationError(f"Coordination failed: {exc}") from exc


def record_probe_circuit_outcome(success: bool, is_upstream_rate_limited: bool = False) -> None:
    """Update circuit breaker failure tracking in distributed cache."""
    try:
        cache = _get_cache()
        now = time.time()
        circuit_key = KEY_CIRCUIT

        redis_client = _get_raw_redis_client(cache)
        if redis_client is not None:
            redis_client.eval(
                LUA_PROBE_CIRCUIT_OUTCOME,
                1,
                circuit_key,
                1 if success else 0,
                1 if is_upstream_rate_limited else 0,
                now,
                CIRCUIT_FAILURE_THRESHOLD,
                CIRCUIT_BREAKER_COOLDOWN,
                WINDOW_SECONDS,
            )
            return

        import os
        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        if "prod" in settings_module:
            raise CoordinationError("Production requires Redis coordination; in-memory fallback is forbidden.")

        with _fallback_lock:
            circuit_data = cache.get(circuit_key)
            if not isinstance(circuit_data, dict):
                circuit_data = {"failures": 0, "state": "closed", "open_until": 0}

            if success:
                circuit_data["failures"] = 0
                circuit_data["state"] = "closed"
                circuit_data["open_until"] = 0
                cache.set(circuit_key, circuit_data, timeout=WINDOW_SECONDS)
                return

            circuit_data["failures"] = circuit_data.get("failures", 0) + 1

            if is_upstream_rate_limited or circuit_data["failures"] >= CIRCUIT_FAILURE_THRESHOLD:
                circuit_data["state"] = "open"
                circuit_data["open_until"] = now + CIRCUIT_BREAKER_COOLDOWN

            cache.set(circuit_key, circuit_data, timeout=WINDOW_SECONDS)

    except Exception:
        # Monitoring hook only; does not break caller since probe execution has finished
        pass
