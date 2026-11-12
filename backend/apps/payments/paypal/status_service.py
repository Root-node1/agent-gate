"""State store and resolver for platform-wide PayPal integration status.

Manages:
- Platform-wide state determination (not_configured, configured, successfully_tested, failed).
- 24-hour expiry of successfully_tested status back to configured.
- Preserves exact last attempt timestamp and sanitized failure error.
- Zero fabricated timestamps or states.
"""

from __future__ import annotations

import time
from typing import TypedDict

from django.conf import settings
from django.core.cache import caches

from .config import get_paypal_config
from .probe_types import ProbeConnectionState

KEY_PLATFORM_PROBE_STATE = "agentgate:paypal:platform_probe_state"
CACHE_ALIAS = "default"
SUCCESS_EXPIRY_SECONDS = 86400  # 24 hours


class PlatformStatusDict(TypedDict):
    state: str
    mode: str
    live_payments_enabled: bool
    client_id_preview: str | None
    webhook_configured: bool
    webhook_id_preview: str | None
    checkout_enabled: bool
    payouts_enabled: bool
    last_attempt_at: float | None
    last_successful_at: float | None
    last_attempt_error: str | None


def _get_cache():
    return caches[CACHE_ALIAS]


def _mask_id(identifier: str | None, prefix_len: int = 3, suffix_len: int = 3) -> str | None:
    if not identifier:
        return None
    s = str(identifier).strip()
    if len(s) <= prefix_len + suffix_len:
        return s[:2] + "..." if len(s) > 2 else "..."
    return f"{s[:prefix_len]}...{s[-suffix_len:]}"


def update_platform_probe_outcome(
    success: bool,
    *,
    tested_at: float,
    error_code: str | None = None,
) -> None:
    """Record an actual upstream probe attempt in the platform state store."""
    cache = _get_cache()
    try:
        current = cache.get(KEY_PLATFORM_PROBE_STATE) or {}
        if not isinstance(current, dict):
            current = {}

        current["last_attempt_at"] = tested_at
        current["last_attempt_status"] = "success" if success else "failed"
        current["last_attempt_error"] = None if success else error_code

        if success:
            current["last_successful_at"] = tested_at

        # Persist across days
        cache.set(KEY_PLATFORM_PROBE_STATE, current, timeout=7 * 86400)
    except Exception:
        pass


def get_platform_integration_status() -> PlatformStatusDict:
    """Compute current platform status against settings and cache."""
    try:
        config = get_paypal_config(settings)
    except Exception:
        config = None

    is_configured = bool(config and config.client_id and config.client_secret)
    now = time.time()

    cache = _get_cache()
    state_data: dict = {}
    try:
        data = cache.get(KEY_PLATFORM_PROBE_STATE)
        if isinstance(data, dict):
            state_data = data
    except Exception:
        pass

    last_attempt_at = state_data.get("last_attempt_at")
    last_attempt_status = state_data.get("last_attempt_status")
    last_attempt_error = state_data.get("last_attempt_error")
    last_successful_at = state_data.get("last_successful_at")

    if not is_configured:
        connection_state = ProbeConnectionState.NOT_CONFIGURED
    elif last_attempt_status == "failed":
        connection_state = ProbeConnectionState.FAILED
    elif last_successful_at and (now - float(last_successful_at) < SUCCESS_EXPIRY_SECONDS):
        connection_state = ProbeConnectionState.SUCCESSFULLY_TESTED
    else:
        # Either no probe has run, or the latest success expired past 24h
        connection_state = ProbeConnectionState.CONFIGURED

    client_id_preview = _mask_id(config.client_id) if config else None
    webhook_id_preview = _mask_id(config.webhook_id) if (config and config.webhook_id) else None
    webhook_configured = bool(config and config.webhook_id)

    return {
        "state": connection_state,
        "mode": "sandbox",
        "live_payments_enabled": False,
        "client_id_preview": client_id_preview,
        "webhook_configured": webhook_configured,
        "webhook_id_preview": webhook_id_preview,
        "checkout_enabled": bool(config and config.checkout_enabled),
        "payouts_enabled": bool(config and config.payouts_enabled),
        "last_attempt_at": float(last_attempt_at) if last_attempt_at else None,
        "last_successful_at": float(last_successful_at) if last_successful_at else None,
        "last_attempt_error": str(last_attempt_error) if last_attempt_error else None,
    }
