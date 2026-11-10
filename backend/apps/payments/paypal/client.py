"""Minimal PayPal REST client for Payouts.

The client owns OAuth token caching, timeouts, bounded retries, and the
``PayPal-Request-Id`` idempotency header. It deliberately exposes only the
operations the payment executor needs.
"""

from __future__ import annotations

import base64

import threading
import time
from collections.abc import Callable

import httpx

from .config import get_paypal_config
from .exceptions import (
    PayPalAmbiguousResponse,
    PayPalError,
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

# Offline-test compatibility constants (requests-style timeouts).
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 30.0

# Production PayPal hosts that must never be contacted by the sandbox client.
_PRODUCTION_HOSTS = frozenset(
    {
        "api.paypal.com",
        "api-m.paypal.com",
        "paypal.com",
        "www.paypal.com",
        "www.sandbox.paypal.com",
    }
)
_SANDBOX_HOST = "api-m.sandbox.paypal.com"


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
        session: object = None,
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
        self._allow_live = allow_live
        self._mode = mode
        self._base_url = (
            base_url or (LIVE_BASE_URL if mode == "live" else SANDBOX_BASE_URL)
        ).rstrip("/")
        self._validate_base_url()
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._clock = clock
        self._sleep = sleep
        self._session = session
        if session is not None:
            self._http = None
            self._owns_http = False
        else:
            self._http = http_client or httpx.Client(timeout=timeout)
            self._owns_http = http_client is None
        self._token_lock = threading.Lock()
        self._access_token = None
        self._token_expires_at = 0.0

    def _validate_base_url(self):
        """Reject production PayPal hosts and non-sandbox origins."""
        from urllib.parse import urlparse

        parsed = urlparse(self._base_url)
        if parsed.scheme != "https":
            raise PayPalConfigurationError("PayPal base URL must use HTTPS.")
        host = parsed.hostname
        if self._allow_live and self._mode == "live" and host == "api-m.paypal.com":
            return
        if host in _PRODUCTION_HOSTS:
            raise PayPalConfigurationError(
                f"Production PayPal host {host!r} is forbidden; the sandbox "
                "client never contacts production."
            )
        if host != _SANDBOX_HOST:
            raise PayPalConfigurationError(
                f"Only the PayPal sandbox host {_SANDBOX_HOST!r} is permitted, "
                f"got {host!r}."
            )

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
            "Authorization": f"Bearer {self.get_token()}",
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
            "Authorization": f"Bearer {self.get_token()}",
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

    def _fetch_token(self) -> str:
        """Fetch a fresh access token from the sandbox OAuth endpoint."""
        with self._token_lock:
            if self._access_token and self._clock() < self._token_expires_at:
                return self._access_token

            try:
                basic = base64.b64encode(
                    f"{self._client_id}:{self._client_secret}".encode("utf-8")
                ).decode("ascii")
                response = self._send(
                    "POST",
                    "/v1/oauth2/token",
                    data={"grant_type": "client_credentials"},
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Basic {basic}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
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
            self._access_token = token
            self._token_expires_at = self._clock() + max(
                0, expires_in - TOKEN_EXPIRY_MARGIN_SECONDS
            )
            return token

    def get_token(self) -> str:
        """Public accessor for the cached OAuth access token."""
        return self._fetch_token()

    def _build_url(self, path: str) -> str:
        """Build and validate a request URL from a relative API path."""
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise PayPalConfigurationError("PayPal request path must be a relative path.")
        if "://" in path or "\\" in path:
            raise PayPalConfigurationError("PayPal request path must be a relative path.")
        for segment in path.split("?")[0].split("#")[0].split("/"):
            if segment in {"", ".", ".."} and segment != "":
                # allow empty segments from leading slash; reject dot segments
                if segment in {".", ".."}:
                    raise PayPalConfigurationError("PayPal request path must not traverse.")
        # explicit traversal check
        if any(seg in {".", ".."} for seg in path.split("?")[0].split("#")[0].split("/")):
            raise PayPalConfigurationError("PayPal request path must not traverse.")
        return f"{self._base_url}{path}"

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
        url = self._build_url(path)
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            response = None
            try:
                if self._session is not None:
                    # Offline-test path: injected session (requests-compatible).
                    response = self._session.request(
                        method,
                        url,
                        headers=headers,
                        json=json,
                        data=data,
                        auth=auth,
                        timeout=(DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT),
                        allow_redirects=False,
                    )
                else:
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
    def from_settings(cls, settings, *, http_client=None, session=None):
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
            session=session,
            allow_live=config.allow_live,
        )

    def __repr__(self):
        has_token = self._access_token is not None
        return (
            f"<PayPalClient base_url={self._base_url!r} "
            f"token={'set' if has_token else 'unset'}>"
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

# Additional aliases expected by offline test suite.
PayPalConfigError = PayPalConfigurationError
PayPalForbiddenError = PayPalResponseError
PayPalRedirectError = PayPalTransientError
PayPalTokenError = PayPalAuthenticationError
PayPalUnauthorizedError = PayPalResponseError


# Simple exception used by webhook ingestion tests that mock provider failures.
class PayPalAPIError(Exception):
    """Simple error raised when the PayPal API returns a non-success response."""

    def __init__(self, message: str = "PayPal API error"):
        super().__init__(message)
