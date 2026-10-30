"""Sandbox-only PayPal OAuth HTTP client (INT-13F).

Transport infrastructure only: OAuth 2.0 client-credentials token retrieval,
bounded HTTP GET/POST against the PayPal sandbox, structured error handling,
and an injectable HTTP session for offline testing.

Security posture
----------------
- Sandbox origin only (``api.sandbox.paypal.com``). Production hosts
  (``api.paypal.com`` / ``api-m.paypal.com`` / ``paypal.com``) are rejected.
- API paths are relative; absolute URLs and parent-directory traversal are refused.
- Redirects are never followed; redirect responses raise.
- Client secrets and access tokens are never logged or embedded in errors.
- No network access at import time or Django startup; tokens are fetched lazily.
- Financial POSTs are never auto-retried and surface an uncertain outcome on
  timeouts or 5xx without claiming success or failure.

Verified against PayPal's official REST API documentation:
- Token endpoint: ``POST https://api-m.sandbox.paypal.com/v1/oauth2/token``
  (the codebase contract pins the ``api.sandbox.paypal.com`` host; see
  ``apps.payments.paypal.config.SANDBOX_API_BASE_URL``).
- Authentication: HTTP Basic ``Base64(client_id:client_secret)``.
- Body: ``grant_type=client_credentials`` (form-urlencoded).
- Response: ``access_token``, ``token_type`` ("Bearer"), ``expires_in`` (seconds).
- Idempotency: caller-supplied ``PayPal-Request-Id`` header (retained for the
  v2 window; this client never generates keys nor auto-retries financial POSTs).
- Errors: structured ``{name, message, debug_id, details}``; 400/401/403/409/
  429/5xx mapped to typed exceptions. 5xx/timeout on financial POSTs are ambiguous.
- Rate limits (429) return ``Retry-After``; safe operations retry with backoff.
"""

import base64
import logging
import threading
import time
from urllib.parse import urljoin, urlparse

import requests

from apps.payments.paypal.config import (
    SANDBOX_API_BASE_URL,
    PayPalConfigError,
    get_paypal_config,
)

logger = logging.getLogger(__name__)

# --- OAuth2 constants ------------------------------------------------------
# Client-credentials token endpoint, appended to the sandbox base URL.
_TOKEN_PATH = "/v1/oauth2/token"
_TOKEN_GRANT_TYPE = "client_credentials"

# Refresh access tokens this many seconds before they expire.
_TOKEN_REFRESH_SKEW_SECONDS = 60

# --- Transport defaults ----------------------------------------------------
# Explicit, bounded connect / read timeouts (seconds).
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 30.0

# Bounded retry ceiling for safe operations (token refresh, idempotent GETs).
DEFAULT_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 0.5

# HTTP redirect status codes: PayPal may return these and are rejected here.
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})

# Production PayPal hosts that must never be contacted by the sandbox client.
_PRODUCTION_HOSTS = frozenset(
    {
        "api.paypal.com",
        "api-m.paypal.com",
        "paypal.com",
        "www.paypal.com",
        # Web-login host (sandbox) is out of scope for the REST client.
        "www.sandbox.paypal.com",
    }
)

_SANDBOX_HOST = urlparse(SANDBOX_API_BASE_URL).hostname


def _is_retryable_status(status_code):
    """Retryable HTTP statuses for safe operations (429 or 5xx)."""
    return status_code == 429 or status_code >= 500


def _redirect_error(response):
    """Build a redirect error without echoing the (possibly query-laden) URL."""
    location = response.headers.get("Location", "")
    host = urlparse(location).hostname
    return PayPalRedirectError(
        "PayPal responded with an HTTP redirect to host "
        f"{host!r}; redirects are never followed."
    )


# --- Exceptions ------------------------------------------------------------
class PayPalClientError(Exception):
    """Base class for all PayPal client errors."""


class PayPalTransportError(PayPalClientError):
    """Low-level transport failure (timeout, connection, or redirect)."""


class PayPalTimeoutError(PayPalTransportError):
    """A request to PayPal did not complete within the timeout window."""


class PayPalConnectionError(PayPalTransportError):
    """A connection to PayPal could not be established."""


class PayPalRedirectError(PayPalTransportError):
    """PayPal returned a redirect, which this sandbox client never follows."""


class PayPalTokenError(PayPalClientError):
    """OAuth token retrieval or parsing failed."""


class PayPalAPIError(PayPalClientError):
    """A non-success PayPal API response (4xx/5xx)."""


class PayPalUnauthorizedError(PayPalAPIError):
    """HTTP 401 — invalid or expired credentials."""


class PayPalForbiddenError(PayPalAPIError):
    """HTTP 403 — insufficient permissions."""


class PayPalNotFoundError(PayPalAPIError):
    """HTTP 404 — resource not found."""


class PayPalConflictError(PayPalAPIError):
    """HTTP 409 — conflict (e.g. a duplicate idempotency key)."""


class PayPalRateLimitError(PayPalAPIError):
    """HTTP 429 — rate limited."""


class PayPalUncertainOutcomeError(PayPalClientError):
    """A financial POST ended ambiguously (timeout or 5xx); outcome unknown."""


class PayPalServerError(PayPalAPIError):
    """HTTP 5xx — PayPal server error."""


class PayPalClient:
    """Sandbox-only PayPal REST client with OAuth 2.0 client-credentials auth.

    All network activity is lazy: construction validates configuration and
    performs **no** network I/O.  Tokens are fetched on demand by
    :meth:`get_token` and cached in memory until they near expiry.

    Inject a custom ``session`` (a :class:`requests.Session` or duck-typed
    equivalent) to drive offline tests without touching the network.
    """

    def __init__(
        self,
        client_id,
        client_secret,
        *,
        session=None,
        base_url=None,
        connect_timeout=DEFAULT_CONNECT_TIMEOUT,
        read_timeout=DEFAULT_READ_TIMEOUT,
        max_retries=DEFAULT_MAX_RETRIES,
        token_refresh_skew=_TOKEN_REFRESH_SKEW_SECONDS,
    ):
        if not client_id or not client_secret:
            raise PayPalConfigError(
                "PayPal client credentials (client_id and client_secret) are required."
            )
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = (base_url or SANDBOX_API_BASE_URL).rstrip("/")
        self._validate_base_url()
        self._session = session if session is not None else requests.Session()
        self._timeout = (connect_timeout, read_timeout)
        self._max_retries = max_retries
        self._token_skew = token_refresh_skew
        self._access_token = None
        self._expires_at = 0.0
        self._token_lock = threading.Lock()

    # -- construction helpers ------------------------------------------------
    @classmethod
    def from_settings(cls, settings, *, session=None):
        """Build a client from Django settings, validating configuration first.

        Performs no network I/O. Raises :class:`PayPalConfigError` when PayPal
        is not enabled or the environment / credentials are invalid.
        """
        config = get_paypal_config(settings)
        if not config.checkout_enabled and not config.payouts_enabled:
            raise PayPalConfigError(
                "PayPal is disabled: enable PAYPAL_CHECKOUT_ENABLED or "
                "PAYPAL_PAYOUTS_ENABLED and provide credentials."
            )
        return cls(
            config.client_id,
            config.client_secret,
            session=session,
        )

    def _validate_base_url(self):
        parsed = urlparse(self._base_url)
        if parsed.scheme != "https":
            raise PayPalConfigError("PayPal base URL must use HTTPS.")
        host = parsed.hostname
        if host in _PRODUCTION_HOSTS:
            raise PayPalConfigError(
                f"Production PayPal host {host!r} is forbidden; the sandbox "
                "client never contacts production."
            )
        if host != _SANDBOX_HOST:
            raise PayPalConfigError(
                f"Only the PayPal sandbox host {_SANDBOX_HOST!r} is permitted, "
                f"got {host!r}."
            )

    # -- public API ----------------------------------------------------------
    def get_token(self):
        """Return a valid sandbox access token, fetching and caching as needed."""
        token = self._access_token
        if token is not None and time.monotonic() < self._expires_at:
            return token
        with self._token_lock:
            token = self._access_token
            if token is not None and time.monotonic() < self._expires_at:
                return token
            return self._fetch_token()

    def get(self, path, *, params=None):
        """Perform an authenticated, retryable GET against the sandbox API."""
        return self._request("GET", path, params=params, retryable=True)

    def post(self, path, *, json=None, request_id=None):
        """Perform an authenticated, non-retryable POST against the sandbox API.

        ``request_id`` is forwarded as the ``PayPal-Request-Id`` header when
        supplied by the caller; the client never generates idempotency keys and
        never auto-retries financial POSTs.
        """
        return self._request(
            "POST", path, json_body=json, request_id=request_id, retryable=False
        )

    # -- auth helpers --------------------------------------------------------
    def _token_headers(self):
        """Headers for the OAuth token request (HTTP Basic + form encoding)."""
        return {
            "Authorization": self._basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

    def _basic_auth_header(self):
        credentials = f"{self._client_id}:{self._client_secret}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"

    # -- token retrieval -----------------------------------------------------
    def _fetch_token(self):
        """Retrieve a fresh access token from the sandbox OAuth endpoint.

        Safe to retry: token refresh is idempotent and creates no money-moving
        state, so 429/5xx/timeouts are retried with bounded backoff.
        """
        url = self._build_url(_TOKEN_PATH)
        headers = self._token_headers()
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._send(
                    "POST", url, headers=headers, data={"grant_type": _TOKEN_GRANT_TYPE}
                )
            except (PayPalTimeoutError, PayPalConnectionError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    self._backoff(attempt)
                    continue
                break
            token, expires_in = self._parse_token_response(response)
            self._cache_token(token, expires_in)
            return token
        raise PayPalTokenError(
            "Failed to obtain PayPal access token after retries."
        ) from last_error

    def _parse_token_response(self, response):
        if response.status_code in _REDIRECT_STATUS_CODES:
            raise _redirect_error(response)
        if response.status_code >= 400:
            raise self._error_from_response(response, "POST")
        try:
            body = response.json()
        except ValueError as exc:
            raise PayPalTokenError("PayPal token response was not valid JSON.") from exc
        if not isinstance(body, dict) or "access_token" not in body:
            raise PayPalTokenError("Access token missing from PayPal token response.")
        token = body["access_token"]
        expires_in = body.get("expires_in")
        try:
            expires_in = int(expires_in)
        except (TypeError, ValueError):
            expires_in = 0
        return token, expires_in

    def _cache_token(self, token, expires_in):
        self._access_token = token
        self._expires_at = time.monotonic() + max(expires_in, 0) - self._token_skew

    # -- request lifecycle ---------------------------------------------------
    def _build_url(self, path):
        if not isinstance(path, str) or not path:
            raise PayPalConfigError("PayPal API path must be a non-empty string.")
        if "://" in path or "\n" in path or "\r" in path:
            raise PayPalConfigError(
                "Absolute URLs are not permitted for PayPal API requests; "
                "pass a relative path."
            )
        if path.startswith("//"):
            raise PayPalConfigError("Protocol-relative API paths are not permitted.")
        if any(segment == ".." for segment in path.split("/")):
            raise PayPalConfigError(
                "Parent-directory references are not permitted in PayPal API paths."
            )
        if not path.startswith("/"):
            path = "/" + path
        url = urljoin(self._base_url + "/", path)
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise PayPalConfigError("Only HTTPS is permitted for PayPal API requests.")
        host = parsed.hostname
        if host in _PRODUCTION_HOSTS:
            raise PayPalConfigError(
                "Production PayPal endpoints are forbidden; the sandbox client "
                "only contacts the sandbox."
            )
        if host != _SANDBOX_HOST:
            raise PayPalRedirectError(f"Request escapes the sandbox origin (host {host!r}).")
        return url

    def _request(self, method, path, *, params=None, json_body=None,
                 request_id=None, retryable=False):
        url = self._build_url(path)
        token = self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        if request_id is not None:
            headers["PayPal-Request-Id"] = request_id
        attempt = 0
        while True:
            try:
                response = self._send(
                    method, url, headers=headers, params=params, json=json_body
                )
            except (PayPalTimeoutError, PayPalConnectionError) as exc:
                if retryable:
                    if attempt < self._max_retries:
                        self._backoff(attempt)
                        attempt += 1
                        continue
                    raise
                raise PayPalUncertainOutcomeError(
                    "POST request to PayPal did not receive a response; the "
                    "operation may have succeeded. Retry with the same "
                    "PayPal-Request-Id to reconcile the outcome."
                ) from exc
            logger.debug("paypal %s -> HTTP %d", method, response.status_code)
            if response.status_code in _REDIRECT_STATUS_CODES:
                raise _redirect_error(response)
            if response.status_code >= 400:
                if (
                    retryable
                    and _is_retryable_status(response.status_code)
                    and attempt < self._max_retries
                ):
                    self._backoff(attempt)
                    attempt += 1
                    continue
                if (
                    not retryable
                    and method == "POST"
                    and response.status_code >= 500
                ):
                    raise PayPalUncertainOutcomeError(
                        "POST request to PayPal returned a server error "
                        "(HTTP %d); the operation may have succeeded. "
                        "Retry with the same PayPal-Request-Id to reconcile "
                        "the outcome." % response.status_code
                    )
                raise self._error_from_response(response, method)
            try:
                return response.json()
            except ValueError as exc:
                raise PayPalAPIError(
                    "Invalid JSON response from PayPal (HTTP %d)." % response.status_code
                ) from exc

    def _send(self, method, url, **kwargs):
        """Issue a single HTTP request, mapping transport faults to typed errors."""
        try:
            return self._session.request(
                method,
                url,
                allow_redirects=False,
                timeout=self._timeout,
                **kwargs,
            )
        except requests.exceptions.Timeout as exc:
            raise PayPalTimeoutError("Request to PayPal timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise PayPalConnectionError("Connection to PayPal failed.") from exc
        except requests.exceptions.TooManyRedirects as exc:
            raise PayPalRedirectError("Exceeded the maximum number of redirects.") from exc
        except requests.exceptions.RequestException as exc:
            raise PayPalTransportError("Request to PayPal failed.") from exc

    def _error_from_response(self, response, method):
        """Map a non-success response to a structured exception (no secrets)."""
        status = response.status_code
        detail = response.reason or "unknown error"
        debug_id = None
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            name = body.get("name")
            message = body.get("message")
            debug_id = body.get("debug_id")
            if message:
                detail = str(message)
            elif name:
                detail = str(name)
        if debug_id:
            detail = f"{detail} (debug_id={debug_id})"
        if status == 401:
            error_cls = PayPalUnauthorizedError
        elif status == 403:
            error_cls = PayPalForbiddenError
        elif status == 404:
            error_cls = PayPalNotFoundError
        elif status == 409:
            error_cls = PayPalConflictError
        elif status == 429:
            error_cls = PayPalRateLimitError
        elif status >= 500:
            error_cls = PayPalServerError
        else:
            error_cls = PayPalAPIError
        return error_cls("PayPal API returned HTTP %d: %s" % (status, detail))

    # -- misc ----------------------------------------------------------------
    def _backoff(self, attempt):
        delay = _BACKOFF_BASE_SECONDS * (2 ** attempt)
        logger.debug("paypal backoff: sleeping %.2fs before retry %d", delay, attempt + 1)
        time.sleep(delay)

    def __repr__(self):
        has_token = self._access_token is not None
        return (
            f"<PayPalClient base_url={self._base_url!r} "
            f"token={'set' if has_token else 'unset'}>"
        )
