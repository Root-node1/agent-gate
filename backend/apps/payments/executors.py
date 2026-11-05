"""Payment execution boundary. The pipeline depends on this protocol, never on PayPal directly."""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from django.conf import settings

from apps.spend.models import SpendRequest


@dataclass(frozen=True)
class ExecutionResult:
    """The outcome of asking a payment provider to move money."""

    reference: str
    status: str
    raw: dict = field(default_factory=dict)


class PaymentNotSent(Exception):
    """The provider definitely did not accept the payment."""


class PaymentAmbiguous(Exception):
    """The provider may have accepted the payment; do not retry blindly."""


class PaymentExecutor(Protocol):
    """Anything that can execute an approved spend request."""

    def execute(self, spend_request: SpendRequest) -> ExecutionResult: ...


class FakeExecutor:
    """Deterministic executor for tests, local work, and the demo pipeline."""

    MODES = ("succeed", "fail", "timeout", "held")

    def __init__(self, mode: str = "succeed"):
        if mode not in self.MODES:
            raise ValueError(f"Unknown fake executor mode: {mode}")
        self.mode = mode

    def execute(self, spend_request: SpendRequest) -> ExecutionResult:
        if self.mode == "succeed":
            return ExecutionResult(reference=f"FAKE-{uuid.uuid4()}", status="COMPLETED")
        if self.mode == "fail":
            return ExecutionResult(reference=f"FAKE-{uuid.uuid4()}", status="FAILED")
        if self.mode == "held":
            return ExecutionResult(reference=f"FAKE-{uuid.uuid4()}", status="HELD")
        raise TimeoutError("The payment provider did not respond.")


class PayPalExecutor:
    """Payouts executor backed by the sandbox-only PayPal REST client."""

    def __init__(self, client=None):
        if client is None:
            client = build_paypal_client()
        self._client = client

    def execute(self, spend_request: SpendRequest) -> ExecutionResult:
        from .paypal import (
            PayPalAmbiguousResponse,
            PayPalAuthenticationError,
            PayPalConfigurationError,
            PayPalResponseError,
            PayPalTimeoutError,
            PayPalTransientError,
            create_payout,
        )

        try:
            result = create_payout(self._client, spend_request)
        except (
            PayPalConfigurationError,
            PayPalAuthenticationError,
            PayPalResponseError,
        ) as exc:
            raise PaymentNotSent(str(exc)) from exc
        except (
            PayPalTimeoutError,
            PayPalTransientError,
            PayPalAmbiguousResponse,
        ) as exc:
            raise PaymentAmbiguous(str(exc)) from exc

        return ExecutionResult(reference=result.reference, status=result.status)


def build_paypal_client():
    """Construct the client from settings without exposing credentials elsewhere."""
    from .paypal import PayPalClient

    return PayPalClient(
        settings.PAYPAL_CLIENT_ID,
        settings.PAYPAL_CLIENT_SECRET,
        mode=settings.PAYPAL_MODE,
        base_url=settings.PAYPAL_BASE_URL,
        timeout=float(settings.PAYPAL_TIMEOUT_SECONDS),
        max_retries=settings.PAYPAL_MAX_RETRIES,
        allow_live=settings.PAYPAL_ALLOW_LIVE,
    )


def get_executor() -> PaymentExecutor:
    """Return the configured executor, failing closed on an unknown value."""
    name = getattr(settings, "PAYMENT_EXECUTOR", "fake")
    if name == "paypal":
        return PayPalExecutor()
    if name == "fake":
        return FakeExecutor(getattr(settings, "FAKE_EXECUTOR_MODE", "succeed"))
    raise PaymentNotSent(f"Unknown PAYMENT_EXECUTOR: {name!r}.")
