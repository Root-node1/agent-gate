"""PayPal webhook signature headers, verification, and Payouts event parsing."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from .client import PayPalClient
from .exceptions import PayPalConfigurationError

VERIFY_PATH = "/v1/notifications/verify-webhook-signature"
HEADER_NAMES = {
    "transmission_id": "PAYPAL-TRANSMISSION-ID",
    "transmission_time": "PAYPAL-TRANSMISSION-TIME",
    "cert_url": "PAYPAL-CERT-URL",
    "auth_algo": "PAYPAL-AUTH-ALGO",
    "transmission_sig": "PAYPAL-TRANSMISSION-SIG",
}

OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_FAILED = "failed"
OUTCOME_REVERSED = "reversed"

EVENT_OUTCOMES = {
    "PAYMENT.PAYOUTS-ITEM.SUCCEEDED": (OUTCOME_SUCCEEDED, "SUCCESS"),
    "PAYMENT.PAYOUTS-ITEM.FAILED": (OUTCOME_FAILED, "FAILED"),
    "PAYMENT.PAYOUTS-ITEM.BLOCKED": (OUTCOME_FAILED, "BLOCKED"),
    "PAYMENT.PAYOUTS-ITEM.RETURNED": (OUTCOME_FAILED, "RETURNED"),
    "PAYMENT.PAYOUTS-ITEM.CANCELED": (OUTCOME_FAILED, "CANCELED"),
    "PAYMENT.PAYOUTS-ITEM.CANCELLED": (OUTCOME_FAILED, "CANCELLED"),
    "PAYMENT.PAYOUTS-ITEM.DENIED": (OUTCOME_FAILED, "DENIED"),
    "PAYMENT.PAYOUTS-ITEM.REFUNDED": (OUTCOME_REVERSED, "REFUNDED"),
    "PAYMENT.PAYOUTS-ITEM.REVERSED": (OUTCOME_REVERSED, "REVERSED"),
    "PAYMENT.PAYOUTSBATCH.SUCCESS": (OUTCOME_SUCCEEDED, "SUCCESS"),
    "PAYMENT.PAYOUTSBATCH.DENIED": (OUTCOME_FAILED, "DENIED"),
}


@dataclass(frozen=True)
class WebhookSignature:
    """The transmission headers PayPal signs each webhook with."""

    transmission_id: str
    transmission_time: str
    cert_url: str
    auth_algo: str
    transmission_sig: str


@dataclass(frozen=True)
class PayoutEvent:
    """The fields AgentGate needs from a Payouts webhook event."""

    spend_request_id: str | None
    reference: str | None
    provider_status: str
    outcome: str | None


def read_signature(headers: Mapping[str, str]) -> WebhookSignature | None:
    """Read the signature headers, or return None if any are missing."""
    values = {
        field: (headers.get(header) or "").strip()
        for field, header in HEADER_NAMES.items()
    }
    if not all(values.values()):
        return None
    return WebhookSignature(**values)


def verify_webhook_signature(
    client: PayPalClient,
    webhook_id: str,
    signature: WebhookSignature,
    event: dict,
) -> bool:
    """Verify one event through PayPal. Returns True only for SUCCESS."""
    if not webhook_id:
        raise PayPalConfigurationError("PAYPAL_WEBHOOK_ID is not configured.")

    response = client.post_json(
        VERIFY_PATH,
        body={
            "auth_algo": signature.auth_algo,
            "cert_url": signature.cert_url,
            "transmission_id": signature.transmission_id,
            "transmission_sig": signature.transmission_sig,
            "transmission_time": signature.transmission_time,
            "webhook_id": webhook_id,
            "webhook_event": event,
        },
        request_id=f"verify-{signature.transmission_id}",
    )
    return str(response.get("verification_status", "")).upper() == "SUCCESS"


def parse_payout_event(event: dict) -> PayoutEvent:
    """Extract the spend request, batch reference, and outcome from an event."""
    event_type = str(event.get("event_type") or "")
    outcome, provider_status = EVENT_OUTCOMES.get(event_type, (None, ""))
    resource = event.get("resource")
    if not isinstance(resource, dict):
        resource = {}

    return PayoutEvent(
        spend_request_id=_spend_request_id(resource),
        reference=_reference(resource),
        provider_status=provider_status,
        outcome=outcome,
    )


def _spend_request_id(resource: dict) -> str | None:
    item = resource.get("payout_item")
    batch = resource.get("batch_header")
    candidates = []
    if isinstance(item, dict):
        candidates.append(item.get("sender_item_id"))
    if isinstance(batch, dict):
        candidates.append(batch.get("sender_batch_id"))
    candidates.append(resource.get("sender_batch_id"))

    for value in candidates:
        if not value:
            continue
        try:
            return str(uuid.UUID(str(value)))
        except (AttributeError, TypeError, ValueError):
            continue
    return None


def _reference(resource: dict) -> str | None:
    batch = resource.get("batch_header")
    if isinstance(batch, dict) and batch.get("payout_batch_id"):
        return str(batch["payout_batch_id"])[:100]
    if resource.get("payout_batch_id"):
        return str(resource["payout_batch_id"])[:100]
    return None
