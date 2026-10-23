"""Payment execution boundary. The pipeline depends on this protocol, never on PayPal directly."""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from apps.spend.models import SpendRequest


@dataclass(frozen=True)
class ExecutionResult:
    """The outcome of asking a payment provider to move money."""

    reference: str
    status: str
    raw: dict = field(default_factory=dict)


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
