"""Probe failure reason constants and sanitized mappings.

Sanitized failure codes:
- invalid_credentials: Upstream PayPal OAuth returned HTTP 401.
- upstream_unavailable: Upstream PayPal OAuth returned HTTP 500, 502, 503, 504.
- rate_limited: Upstream returned 429, or local rate limit was exceeded.
- timeout: The total deadline (8.0s) was exceeded.
- circuit_open: Circuit breaker engaged due to recent consecutive failures / throttling.
"""

from __future__ import annotations


class ProbeFailureReason:
    INVALID_CREDENTIALS = "invalid_credentials"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    CIRCUIT_OPEN = "circuit_open"
    COORDINATION_UNAVAILABLE = "coordination_unavailable"

    ALL = frozenset(
        {
            INVALID_CREDENTIALS,
            UPSTREAM_UNAVAILABLE,
            RATE_LIMITED,
            TIMEOUT,
            CIRCUIT_OPEN,
            COORDINATION_UNAVAILABLE,
        }
    )


class ProbeConnectionState:
    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    SUCCESSFULLY_TESTED = "successfully_tested"
    FAILED = "failed"

    ALL = frozenset(
        {
            NOT_CONFIGURED,
            CONFIGURED,
            SUCCESSFULLY_TESTED,
            FAILED,
        }
    )
