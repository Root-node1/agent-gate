"""Payouts API request shape and response extraction."""

from dataclasses import dataclass

from apps.common.money import to_major
from apps.payees.models import DestinationType
from apps.spend.models import SpendRequest

from .client import PayPalClient
from .exceptions import PayPalAmbiguousResponse, PayPalConfigurationError

RECIPIENT_TYPES = {
    DestinationType.PAYPAL_EMAIL: "EMAIL",
    DestinationType.PAYPAL_ID: "PAYPAL_ID",
    DestinationType.PHONE: "PHONE",
}
PAYOUTS_PATH = "/v1/payments/payouts"
TEXT_LIMIT = 255


@dataclass(frozen=True)
class PayoutResult:
    """The provider reference and status for an accepted payout batch."""

    reference: str
    status: str


def payout_payload(spend_request: SpendRequest) -> dict:
    """Build the Payouts request body for one spend request."""
    recipient_type = RECIPIENT_TYPES.get(spend_request.destination_type)
    if recipient_type is None:
        raise PayPalConfigurationError(
            "This destination type cannot receive a PayPal payout."
        )
    if not spend_request.destination_value:
        raise PayPalConfigurationError("The payout destination is empty.")

    note = (spend_request.purpose or "").strip()[:TEXT_LIMIT]
    amount = str(
        to_major(spend_request.amount_minor, spend_request.currency)
    )
    item = {
        "recipient_type": recipient_type,
        "amount": {"value": amount, "currency": spend_request.currency},
        "receiver": spend_request.destination_value,
        "sender_item_id": str(spend_request.id),
    }
    if note:
        item["note"] = note

    return {
        "sender_batch_header": {
            "sender_batch_id": str(spend_request.id),
            "email_subject": "AgentGate payment",
            "email_message": note or "A payment was sent to you by AgentGate.",
        },
        "items": [item],
    }


def create_payout(
    client: PayPalClient, spend_request: SpendRequest
) -> PayoutResult:
    """Submit one payout batch and return its provider reference."""
    payload = payout_payload(spend_request)
    response = client.post_json(
        PAYOUTS_PATH,
        body=payload,
        request_id=f"agentgate-{spend_request.id}",
    )
    batch = response.get("batch_header")
    if not isinstance(batch, dict):
        raise PayPalAmbiguousResponse(
            "PayPal accepted the payout without a batch header."
        )
    reference = batch.get("payout_batch_id")
    if not reference:
        raise PayPalAmbiguousResponse(
            "PayPal accepted the payout without a batch id."
        )
    status = str(batch.get("batch_status") or "PENDING")
    return PayoutResult(reference=str(reference), status=status)
