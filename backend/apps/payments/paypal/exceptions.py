"""PayPal boundary errors. Messages never carry credentials or full payloads."""


class PayPalError(Exception):
    """Base class for PayPal client failures."""


class PayPalConfigurationError(PayPalError):
    """The client cannot run with the supplied configuration."""


class PayPalAuthenticationError(PayPalError):
    """A token could not be obtained, so no payment request was sent."""


class PayPalResponseError(PayPalError):
    """PayPal rejected a request. No money should have moved."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str = "",
        body: dict | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.body = body


class PayPalTransientError(PayPalError):
    """A retryable response or transport failure exhausted its retries."""


class PayPalTimeoutError(PayPalError):
    """The provider did not answer in time, so the outcome is unknown."""


class PayPalAmbiguousResponse(PayPalError):
    """The provider answered successfully but the body was not usable."""
