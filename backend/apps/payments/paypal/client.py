"""Minimal PayPal REST client for Payouts.

The client owns OAuth token caching, timeouts, bounded retries, and the
``PayPal-Request-Id`` idempotency header. It deliberately exposes only the
operations the payment executor needs.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import httpx

from .config import get_paypal_config
from .exceptions import (
    PayPalAmbiguousResponse,
    PayPalAuthenticationError,
    PayPalConfigurationError,
    PayPalResponseError,
    PayPalTimeoutError,
    PayPalTransientError,
)

SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"
LIVE_BASE_URL = "https://api-m.paypal.com"
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_BACKOFF_SECONDS = 8.0
TOKEN_EXPIRY_MARGIN_SECONDS = 30


class PayPalClient:
    """Small synchronous client that is safe to reuse inside one worker process."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        mode: str = "sandbox",
        base_url: str = "",
        timeout: float = 10.0,
        max_retries: int = 2,
        allow_live: bool = False,
        http_client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not client_id or not client_secret:
            raise PayPalConfigurationError(
                "PayPal client id and secret are required."
            )
        if mode not in {"sandbox", "live"}:
            raise PayPalConfigurationError(
                f"Unsupported PayPal mode: {mode!r}."
            )
        if mode == "live" and not allow_live:
            raise PayPalConfigurationError(
                "Live PayPal mode is disabled; set PAYPAL_ALLOW_LIVE=1 only "
                "when live movement is intentional."
            )

        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = (
            base_url or (LIVE_BASE_URL if mode == "live" else SANDBOX_BASE_URL)
        ).rstrip("/")
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._clock = clock
        self._sleep = sleep
        self._http = http_client or httpx.Client(timeout=timeout)
        self._owns_http = http_client is None
        self._token_lock = threading.Lock()
        self._token = ""
        self._token_expires_at = 0.0

    def __enter__(self) -> PayPalClient:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def post_json(
        self,
        path: str,
        *,
        body: dict,
        request_id: str,
    ) -> dict:
        """POST JSON with a bearer token and a caller-supplied idempotency id."""
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "PayPal-Request-Id": request_id,
        }
        response = self._send("POST", path, headers=headers, json=body)
        return self._decode_json(response)

    def post(self, path: str, *, json: dict | None = None, request_id: str = "") -> dict:
        """Compatibility wrapper: POST JSON body to a PayPal API path."""
        return self.post_json(path, body=json or {}, request_id=request_id)

    def get_json(self, path: str) -> dict:
        """GET JSON with a bearer token."""
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "Accept": "application/json",
        }
        response = self._send("GET", path, headers=headers)
        return self._decode_json(response)

    def get(self, path: str) -> dict:
        """Compatibility wrapper: GET JSON from a PayPal API path."""
        return self.get_json(path)

    def _decode_json(self, response: httpx.Response) -> dict:
        if response.status_code >= 400:
            code = self._error_code(response)
            raise PayPalResponseError(
                f"PayPal rejected the request ({response.status_code}: "
                f"{code or 'error'}).",
                status_code=response.status_code,
                code=code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise PayPalAmbiguousResponse(
                "PayPal returned an unreadable success response."
            ) from exc
        if not isinstance(payload, dict):
            raise PayPalAmbiguousResponse(
                "PayPal returned an unexpected success response."
            )
        return payload

    def _access_token(self) -> str:
        with self._token_lock:
            if self._token and self._clock() < self._token_expires_at:
                return self._token

            try:
                response = self._send(
                    "POST",
                    "/v1/oauth2/token",
                    auth=httpx.BasicAuth(self._client_id, self._client_secret),
                    data={"grant_type": "client_credentials"},
                    headers={"Accept": "application/json"},
                )
            except (PayPalTimeoutError, PayPalTransientError) as exc:
                raise PayPalAuthenticationError(
                    "PayPal authentication did not complete."
                ) from exc

            if response.status_code >= 400:
                raise PayPalAuthenticationError(
                    f"PayPal authentication failed ({response.status_code})."
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise PayPalAuthenticationError(
                    "PayPal returned an unreadable token response."
                ) from exc

            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not token:
                raise PayPalAuthenticationError(
                    "PayPal did not return an access token."
                )
            try:
                expires_in = int(payload.get("expires_in", 0))
            except (TypeError, ValueError):
                expires_in = 0
            self._token = token
            self._token_expires_at = self._clock() + max(
                0, expires_in - TOKEN_EXPIRY_MARGIN_SECONDS
            )
            return token

    def _send(
        self,
        method: str,
        path: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
        data: dict | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            response = None
            try:
                response = self._http.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    data=data,
                    auth=auth,
                )
            except httpx.TimeoutException as exc:
                last_error = PayPalTimeoutError(
                    "PayPal did not respond before the timeout."
                )
                last_error.__cause__ = exc
            except httpx.TransportError as exc:
                last_error = PayPalTransientError(
                    "PayPal could not be reached."
                )
                last_error.__cause__ = exc
            else:
                if response.status_code not in RETRYABLE_STATUSES:
                    return response
                last_error = PayPalTransientError(
                    f"PayPal returned a retryable status ({response.status_code})."
                )

            if attempt < self._max_retries:
                self._sleep(self._backoff(attempt, response))

        assert last_error is not None
        raise last_error

    def _backoff(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After", "")
            try:
                return min(float(retry_after), MAX_BACKOFF_SECONDS)
            except ValueError:
                pass
        return min(2.0**attempt, MAX_BACKOFF_SECONDS)

    @staticmethod
    def _error_code(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("name") or payload.get("error") or "")[:100]

    @classmethod
    def from_settings(cls, settings, *, http_client=None):
        """Build a client from Django settings, validating configuration first.

        Performs no network I/O. Raises :class:`PayPalConfigurationError`
        when PayPal is not enabled or the environment / credentials are invalid.
        """
        config = get_paypal_config(settings)
        if not config.checkout_enabled and not config.payouts_enabled:
            raise PayPalConfigurationError(
                "PayPal is disabled: enable PAYPAL_CHECKOUT_ENABLED or "
                "PAYPAL_PAYOUTS_ENABLED and provide credentials."
            )
        return cls(
            config.client_id,
            config.client_secret,
            mode=config.mode,
            http_client=http_client,
            allow_live=config.allow_live,
        )


# Backwards-compatible aliases for exception names used by checkout/payouts services.
PayPalConnectionError = PayPalTransientError
PayPalNotFoundError = PayPalResponseError
PayPalRateLimitError = PayPalTransientError
PayPalServerError = PayPalResponseError
PayPalUncertainOutcomeError = PayPalTransientError
PayPalClientError = PayPalConfigurationError
PayPalConflictError = PayPalResponseError
PayPalTransportError = PayPalTransientError


# Simple exception used by webhook ingestion tests that mock provider failures.
class PayPalAPIError(Exception):
    """Simple error raised when the PayPal API returns a non-success response."""

    def __init__(self, message: str = "PayPal API error"):
        super().__init__(message)
